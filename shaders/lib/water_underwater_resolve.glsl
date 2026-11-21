#ifndef AURORA_WATER_UNDERWATER_RESOLVE_INCLUDED
#define AURORA_WATER_UNDERWATER_RESOLVE_INCLUDED
#include "/lib/water_underwater_settings.glsl"
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
#include "/lib/water_interface_scatter.glsl"
// An observed finite top exit, never a guessed infinite water plane. Byte alpha
// identifies the exit while the independent red counter still rejects overlap.
bool waterExitRecord(ivec2 pixel,ivec2 size,out vec3 position,out vec3 normal,out vec2 lights) {
    position=vec3(0);normal=vec3(0);lights=vec2(0);
    if(any(lessThan(pixel,ivec2(0)))||any(greaterThanEqual(pixel,size)))return false;
    vec4 owner=texelFetch(colortex8,pixel,0),surface=texelFetch(colortex7,pixel,0);
    float depth=texelFetch(depthtex0,pixel,0).r;
    if(!waterTraceFinite4(owner)||!waterTraceFinite4(surface)||!waterMediumFinite(depth)
       ||abs(owner.r*255.0-1.0)>.002||abs(owner.a*255.0-1.0)>.002
       ||any(lessThan(owner.gb,vec2(0)))||any(greaterThan(owner.gb,vec2(1)))
       ||abs(dot(surface.xyz,surface.xyz)-1.0)>.001||surface.a<0.0||surface.a>=1.0
       ||depth<0.0||depth>=1.0||abs(depth-surface.a)>1.0/16777215.0)return false;
    if(!waterTraceUnproject(pixel,surface.a,size,position))return false;
    normal=surface.xyz;lights=owner.gb;return true;
}
// Screen-sample certificate: the vertical projection of a reflected segment must
// stay within the captured finite exit footprint. Check every crossed pixel, not
// just endpoints. This cannot infer off-screen pool walls or unseen water volumes.
bool waterExitFootprint(vec3 start,vec3 finish,vec3 up,ivec2 size) {
    vec3 planeEnd=finish+up*dot(start-finish,up),q;vec2 a,b;float k;
    if(!waterTraceProject(start,size,a,q,k)||!waterTraceProject(planeEnd,size,b,q,k)
       ||any(lessThan(a,vec2(0)))||any(greaterThanEqual(a,vec2(size)))
       ||any(lessThan(b,vec2(0)))||any(greaterThanEqual(b,vec2(size))))return false;
    vec2 delta=b-a;ivec2 cell=ivec2(floor(a)),stepDirection=ivec2(sign(delta));
    for(int axis=0;axis<2;++axis)if(delta[axis]<0.0&&a[axis]==floor(a[axis]))cell[axis]-=1;
    float enter=0.0;
    for(int index=0;index<128;++index){
        vec2 crossing=vec2(1.0);
        for(int axis=0;axis<2;++axis)if(stepDirection[axis]!=0){
            float boundary=float(cell[axis]+(stepDirection[axis]>0?1:0));
            crossing[axis]=(boundary-a[axis])/delta[axis];
        }
        float leave=min(1.0,min(crossing.x,crossing.y));
        if(leave<=enter)return false;
        vec3 recorded,normal;vec2 lights;
        if(!waterExitRecord(cell,size,recorded,normal,lights)||dot(normal,up)<.65
           ||abs(dot(recorded-start,up))>.015)return false;
        if(leave>=1.0)return true;
        for(int axis=0;axis<2;++axis)if(crossing[axis]<=leave)cell[axis]+=stepDirection[axis];
        enter=leave;
    }
    return false;
}
bool waterUnderwaterTrace(vec3 origin,vec3 direction,vec3 surface,vec3 up,bool inWater,
                          ivec2 sourcePixel,ivec2 size,out vec3 radiance,out float path,
                          out float share,out float confidence) {
    radiance=vec3(0);path=0.0;share=0.0;confidence=0.0;
#if WATER_SCREEN_REFLECTIONS == 0
    return false;
#endif
    ivec2 hitPixel;vec3 hitView,hitRGB;float hitDistance,hitConfidence;int steps,outcome;
    bool hit=traceWaterSceneClassified(origin,direction,hitPixel,hitView,hitRGB,
                                      hitDistance,hitConfidence,steps,outcome);
    // A ray collinear with the camera has no screen-space traversal. Accept only
    // its exact paired source pixel with a tightly bounded line-distance test.
    if(!hit&&outcome==WATER_TRACE_UNRESOLVED){
        vec3 candidateRGB,candidate;
        if(waterResolveSnapshot(sourcePixel,size,candidateRGB,candidate)){
            vec3 offset=candidate-origin;float along=dot(offset,direction);
            if(along>.05&&along<64.0&&length(offset-direction*along)<.0001){
                hit=true;hitPixel=sourcePixel;hitView=candidate;hitRGB=candidateRGB;hitConfidence=1.0;
            }
        }
    }
    if(!hit)return false;
    vec4 owner=texelFetch(colortex8,hitPixel,0);
    if(!waterTraceFinite4(owner))return false;
    bool empty=all(equal(owner,vec4(0)));
    bool exit=abs(owner.r*255.0-1.0)<=.002&&abs(owner.a*255.0-1.0)<=.002
              &&all(greaterThanEqual(owner.gb,vec2(0)))&&all(lessThanEqual(owner.gb,vec2(1)));
    if(!empty&&!exit)return false;
    share=texelFetch(colortex9,hitPixel,0).r;
    if(!waterMediumFinite(share)||share<0.0||share>1.0)return false;
    float height=dot(hitView-surface,up);
    if(inWater ? height>=-.01 : height<=.01)return false;
    if(inWater&&!waterExitFootprint(surface,hitView,up,size))return false;
    path=length(hitView-surface)*waterParams().worldBlockMeters;
    if(!waterMediumFinite(path)||path<=.01||path>=64.0)return false;
    radiance=waterFilteredReflectionRadiance(hitPixel,hitView,hitRGB);
    confidence=hitConfidence;return true;
}
vec3 resolveWaterUnderwater(vec3 nativeScene,ivec2 pixel,ivec2 size) {
    if(!waterMediumFinite(blindness)||!waterMediumFinite(darknessFactor)
       ||blindness>0.0||darknessFactor>0.0)return nativeScene;
    if(isEyeInWater!=1||!hasSkylight||hasCeiling||any(lessThanEqual(size,ivec2(0)))
       ||any(notEqual(size,textureSize(colortex5,0)))||any(notEqual(size,textureSize(colortex6,0)))
       ||any(notEqual(size,textureSize(colortex7,0)))||any(notEqual(size,textureSize(colortex8,0)))
       ||any(notEqual(size,textureSize(colortex9,0)))||any(notEqual(size,textureSize(depthtex0,0)))
       ||any(notEqual(size,textureSize(depthtex1,0)))||!waterTraceFinite3(upPosition)
       ||max(max(abs(upPosition.x),abs(upPosition.y)),abs(upPosition.z))<=1e-6)return nativeScene;
    vec3 surface,normal;vec2 lights;
    if(!waterExitRecord(pixel,size,surface,normal,lights))return nativeScene;
    vec3 up=celestialUnit(upPosition),incident=celestialUnit(surface);
    float cameraMeters=length(surface)*waterParams().worldBlockMeters;
    if(dot(normal,up)<.65||dot(incident,up)<=.03||cameraMeters<=.01||cameraMeters>=64.0)return nativeScene;
    WaterParams params=waterParams();
    WaterInterfaceScatter scatter=scatterWaterInterface(incident,-normal,params.refractiveIndex,1.0);
    if(!scatter.valid)return nativeScene;
    float strength=clamp(WATER_REFLECTION_STRENGTH,0.0,1.0);
    // TIR has no permitted air ray, even when the artistic reflection slider is zero.
    if(scatter.totalInternalReflection&&strength==0.0)return nativeScene;
    vec3 transmitted=nativeScene,reflected=nativeScene,source;float path,share,confidence;
    bool transmittedHit=false,reflectedHit=false;float transmissionConfidence=0.0,reflectionConfidence=0.0;
    if(!scatter.totalInternalReflection){
        transmittedHit=waterUnderwaterTrace(surface+up*.01,scatter.transmitted,surface,up,false,pixel,size,
                                            source,path,share,confidence);
        if(transmittedHit){
            // Air is not tinted with the underwater camera's fogColor. Unmodeled
            // air-path atmosphere is left absent; the proven water camera leg is fresh.
            transmitted=waterTransportRadiance(source*scatter.radianceScale,0.0,cameraMeters,0.0,
                                                lights.x,lights.y,vec3(0));
            transmissionConfidence=confidence;
        }
    }
    if(strength>0.0){
        reflectedHit=waterUnderwaterTrace(surface-up*.01,scatter.reflected,surface,up,true,pixel,size,
                                          source,path,share,confidence);
        if(reflectedHit){
            // No unknown light-entry leg is invented for a below-water receiver.
            reflected=waterTransportRadiance(source,0.0,cameraMeters+path,0.0,lights.x,lights.y,vec3(0));
            reflectionConfidence=confidence;
        }
    }
    if(scatter.totalInternalReflection){
        if(!reflectedHit)return nativeScene;
        // A proven TIR ray has F=1. Nonzero artistic strength cannot create
        // a forbidden air-transmission term; only missing data blends fallback.
        return mix(nativeScene,reflected,reflectionConfidence);
    }
    if(!transmittedHit)return nativeScene;
    float weight=scatter.fresnel*strength;
    vec3 result=mix(transmitted,mix(nativeScene,reflected,reflectionConfidence),weight);
    if(!waterTraceFinite3(result)||any(lessThan(result,vec3(0)))||any(greaterThan(result,vec3(65504))))return nativeScene;
    return mix(nativeScene,result,transmissionConfidence);
}
#endif
#endif
