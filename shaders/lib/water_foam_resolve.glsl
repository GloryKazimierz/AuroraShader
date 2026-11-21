#ifndef AURORA_WATER_FOAM_RESOLVE_INCLUDED
#define AURORA_WATER_FOAM_RESOLVE_INCLUDED
#include "/lib/water_foam_settings.glsl"
#ifdef AURORA_WATER_FOAM_ACTIVE
#include "/lib/water_foam_model.glsl"
#include "/lib/water_foam_history.glsl"
#include "/lib/water_interface_lighting.glsl"

float waterFoamShoreDistance(vec3 waterView, ivec2 size, vec2 worldDx, vec2 worldDy) {
    // Evidence from four known visible land points around a 0.45-block ring.
    // This is NOT a world shoreline SDF and never uses the water-to-bottom gap.
    if(max(length(worldDx),length(worldDy))>0.35)return -1.0;
    float nearest=1e10;
    mat3 worldToView=inverse(mat3(gbufferModelViewInverse));
    const vec2 offsets[4]=vec2[4](vec2(-.45,0),vec2(.45,0),vec2(0,-.45),vec2(0,.45));
    for(int tap=0;tap<4;++tap){
        vec3 sampleView=waterView+worldToView*vec3(offsets[tap].x,0,offsets[tap].y);
        vec2 screen;vec3 q;float reciprocal;
        if(!waterTraceProject(sampleView,size,screen,q,reciprocal))continue;
        ivec2 p=ivec2(floor(screen));
        if(any(lessThan(p,ivec2(0)))||any(greaterThanEqual(p,size)))continue;
        vec4 owner=texelFetch(colortex8,p,0);
        if(!waterTraceFinite4(owner)||owner!=vec4(0.0))continue;
        float raw=texelFetch(depthtex0,p,0).r;
        if(!waterFoamFinite(raw)||raw!=texelFetch(depthtex1,p,0).r)continue;
        float share=texelFetch(colortex9,p,0).r;
        if(!waterFoamFinite(share)||share<0.0||share>1.0)continue;
        vec3 radiance,landView;
        if(!waterResolveSnapshot(p,size,radiance,landView))continue;
        vec3 delta=mat3(gbufferModelViewInverse)*(landView-waterView);
        if(!waterFoamFinite3(delta)||abs(delta.y)>0.12)continue;
        nearest=min(nearest,length(delta.xz));
    }
    return nearest<=0.65?nearest:-1.0;
}
vec3 resolveWaterFoam(vec3 resolvedScene, ivec2 pixel, ivec2 size, out vec4 historyState, out vec2 historyMetadata) {
    historyState=vec4(0.0);historyMetadata=vec2(0.0);
    if(any(lessThanEqual(size,ivec2(0)))||any(lessThan(pixel,ivec2(0)))||any(greaterThanEqual(pixel,size))
       ||any(notEqual(size,textureSize(colortex5,0)))||any(notEqual(size,textureSize(colortex6,0)))
       ||any(notEqual(size,textureSize(colortex7,0)))||any(notEqual(size,textureSize(colortex8,0)))
       ||any(notEqual(size,textureSize(colortex9,0)))||any(notEqual(size,textureSize(depthtex0,0)))
       ||any(notEqual(size,textureSize(depthtex1,0))))return resolvedScene;
    float environment=celestialEnvironmentWeight();
    if(!waterFoamFinite(environment)||environment<=0.0||!waterFoamFinite3(upPosition)
       ||!waterFoamFinite3(shadowLightPosition)||!waterFoamFinite3(fogColor)
       ||max(max(abs(upPosition.x),abs(upPosition.y)),abs(upPosition.z))<=1e-6
       ||max(max(abs(shadowLightPosition.x),abs(shadowLightPosition.y)),abs(shadowLightPosition.z))<=1e-6)return resolvedScene;
    vec4 surface=texelFetch(colortex7,pixel,0),owner=texelFetch(colortex8,pixel,0);
    float depth=texelFetch(depthtex0,pixel,0).r;
    if(!waterTraceFinite4(surface)||!waterTraceFinite4(owner)||!waterFoamFinite(depth)
       ||abs(owner.r*255.0-1.0)>.002||owner.a!=0.0
       ||any(lessThan(owner.gb,vec2(0)))||any(greaterThan(owner.gb,vec2(1)))
       ||abs(dot(surface.xyz,surface.xyz)-1.0)>.001||surface.a<0.0||surface.a>=1.0
       ||depth<0.0||depth>=1.0||abs(depth-surface.a)>1.0/16777215.0)return resolvedScene;
    vec3 point;
    if(!waterTraceUnproject(pixel,depth,size,point))return resolvedScene;
    vec3 up=celestialUnit(upPosition),normal=normalize(surface.xyz);
    if(dot(normal,up)<=.65||dot(celestialUnit(-point),up)<=.03)return resolvedScene;
    vec3 playerPoint=viewToPlayerPosition(point);
    vec2 dx,dy;
    if(!waterFoamFinite3(playerPoint)||!waterInterfaceFootprint(pixel,size,playerPoint,dx,dy)
       ||!waterFoamFinite2(cameraPositionFract.xz))return resolvedScene;
    vec2 anchor=vec2(uvec2(cameraPositionInt.xz)&uvec2(127u));
    vec2 position=mod(anchor+cameraPositionFract.xz+playerPoint.xz,128.0);
    float strength=0.0;
#if WATER_WAVES != 0
    strength=clamp(WATER_WAVE_STRENGTH,0.0,1.0);
#endif
    vec2 material;WaterFoamFlow flow;
    if(!waterFoamMaterialPoint(position,frameTimeCounter,strength,float(WATER_WAVE_SPEED),dx,dy,material,flow))return resolvedScene;
    float shore=waterFoamShoreDistance(point,size,dx,dy);
    float grain=.5+.25*sin(6.28318530718*fract(dot(material,vec2(37,17))/128.0))*waterWavePixelFilter(vec2(37,17),dx,dy)
                  +.25*sin(6.28318530718*fract(dot(material,vec2(23,-41))/128.0))*waterWavePixelFilter(vec2(23,-41),dx,dy);
    float coverage=waterFoamEvidence(flow.areaRatio,shore,grain,float(WATER_WAVE_SPEED));
#ifdef AURORA_WATER_FOAM_HISTORY
    vec3 worldNormal=normalize(transpose(inverse(mat3(gbufferModelViewInverse)))*normal);
    vec2 previous=vec2(0.0);
    bool accepted=waterFoamFinite3(worldNormal)&&waterFoamPrevious(playerPoint,worldNormal,material,flow,strength,dx,dy,size,previous);
    float age;
    coverage=waterFoamEvolve(previous.x,previous.y,coverage,frameTime,accepted,age);
    if(frameCounter>=0&&frameCounter<=720719&&waterFoamFinite3(worldNormal)){
        historyState=vec4(coverage,age,waterFoamOctEncode(worldNormal));
        historyMetadata=vec2(depth,float(frameCounter+1));
    }
#endif
    if(coverage<=0.0)return resolvedScene;
    vec3 light=celestialUnit(shadowLightPosition);
    float visibility=waterInterfaceVisibility(point,normal,light);
    vec3 sky=max(fogColor,vec3(0))*.35*3.14159265359;
#if SKY_STYLE != 0
    sky=auroraSkyLinear(up,fogColor)*3.14159265359*.6;
#endif
    vec3 direct=mix(vec3(.08,.11,.2),vec3(3.5,3.2,2.7),celestialPhases().x);
    vec3 radiance=waterFoamDiffuse(sky,direct,vec3(3.2,1.7,.65),owner.b,owner.g,
                                  max(dot(normal,light),0.0),visibility);
    radiance=applyAtmosphericFog(radiance,point);
    if(!waterFoamFinite3(radiance))return resolvedScene;
    // Both colors already have the identical surface-to-camera fog operation.
    // Mixing them preserves one camera segment and preserves native alpha.
    return mix(resolvedScene,radiance,coverage*environment);
}
#endif
#endif
