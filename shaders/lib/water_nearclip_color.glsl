#ifndef AURORA_WATER_NEARCLIP_COLOR_INCLUDED
#define AURORA_WATER_NEARCLIP_COLOR_INCLUDED
#include "/lib/water_nearclip.glsl"
#ifdef AURORA_WATER_NEARCLIP_ACTIVE
// Experimental and default off: a wholly submerged camera-to-shallow-bed segment.
// Crossing-interface/air/unknown pixels remain exactly the existing native result.
bool nearClipColumnCoverage(vec3 start,vec3 finish,WaterNearPatch reference) {
    vec3 a,b;if(!causticProject(start,a)||!causticProject(finish,b))return false;
    vec2 size=vec2(textureSize(shadowcolor0,0));
    vec2 first=a.xy*size-.5,last=b.xy*size-.5,delta=last-first;
    ivec2 cell=ivec2(floor(first)),direction=ivec2(sign(delta));
    for(int axis=0;axis<2;++axis)if(delta[axis]<0.0&&first[axis]==floor(first[axis]))cell[axis]-=1;
    float enter=0.0;
    for(int step=0;step<32;++step){
        vec2 boundary=vec2(1.0);
        for(int axis=0;axis<2;++axis)if(direction[axis]!=0)
            boundary[axis]=(float(cell[axis]+(direction[axis]>0?1:0))-first[axis])/delta[axis];
        float leave=min(1.0,min(boundary.x,boundary.y));
        if(leave<=enter)return false;
        vec3 p=mix(start,finish,(enter+leave)*.5);
        WaterNearPatch current;
        if(!nearClipPatch(p,current)||any(notEqual(current.key,cell))
           ||dot(current.normal,reference.normal)<.99999
           ||current.bedTop-current.bedBottom>.002
           ||abs(current.bedTop-reference.bedTop)>.002)return false;
        for(int i=0;i<4;++i)
            if(abs(dot(reference.normal,current.p[i]-reference.p[0]))>.0001)return false;
        // The fetched quad projects exactly to [cell,cell+1]. Check this
        // interval in that same light-space domain; a second world-space
        // barycentric projection onto independently quantized planes created
        // false gaps at every shared edge. No cell or unknown sample is skipped.
        vec2 firstPart=first+delta*enter,lastPart=first+delta*leave;
        float roundoff=max(.0001,4.76837158203125e-7*max(size.x,size.y));
        if(any(lessThan(min(firstPart,lastPart),vec2(cell)-roundoff))
           ||any(greaterThan(max(firstPart,lastPart),vec2(cell)+1.0+roundoff)))return false;
        if(leave>=1.0)return true;
        for(int axis=0;axis<2;++axis)if(boundary[axis]<=leave)cell[axis]+=direction[axis];
        enter=leave;
    }
    return false;
}
vec3 resolveWaterNearClipColor(vec3 nativeScene,ivec2 pixel,ivec2 size) {
    if(isEyeInWater!=1||!hasSkylight||hasCeiling||blindness>0.0||darknessFactor>0.0
       ||!waterResolveScalar(blindness)||!waterResolveScalar(darknessFactor)
       ||any(lessThan(pixel,ivec2(0)))||any(greaterThanEqual(pixel,size)))return nativeScene;
    if(any(notEqual(size,textureSize(colortex1,0)))||any(notEqual(size,textureSize(colortex5,0)))
       ||any(notEqual(size,textureSize(colortex6,0)))||any(notEqual(size,textureSize(colortex7,0)))
       ||any(notEqual(size,textureSize(colortex8,0)))||any(notEqual(size,textureSize(colortex9,0)))
       ||any(notEqual(size,textureSize(depthtex0,0)))||any(notEqual(size,textureSize(depthtex1,0))))return nativeScene;
    vec4 owner=texelFetch(colortex8,pixel,0),surface=texelFetch(colortex7,pixel,0);
    if(any(notEqual(surface,vec4(0))))return nativeScene;
    float depth=texelFetch(depthtex0,pixel,0).r,opaque=texelFetch(depthtex1,pixel,0).r;
    float share=texelFetch(colortex9,pixel,0).r;
    vec4 nearView=gbufferProjectionInverse*vec4((vec2(pixel)+.5)/vec2(size)*2.0-1.0,-1.0,1.0);
    if(any(isnan(nearView))||any(isinf(nearView))||nearView.w<=0.0)return nativeScene;
    vec3 nearPoint=viewToPlayerPosition(nearView.xyz/nearView.w);
    vec3 eye=viewToPlayerPosition(vec3(0));
    float lightLengthSquared=dot(shadowLightPosition,shadowLightPosition);
    if(!causticFinite3(shadowLightPosition)||!waterResolveScalar(lightLengthSquared)||lightLengthSquared<=1e-12)return nativeScene;
    vec3 light=mat3(gbufferModelViewInverse)*celestialUnit(shadowLightPosition);
    WaterNearResult classified=classifyWaterNearClip(eye,nearPoint,light,owner,depth,opaque,share);
    if(classified.medium!=2||!classified.integralValid||classified.crossed)return nativeScene;
    WaterNearPatch localSurface;if(!nearClipPatch(eye,localSurface)||localSurface.normal.y<.99999
       ||localSurface.bedTop-localSurface.bedBottom>.002)return nativeScene;
    vec3 n=localSurface.normal,anchor=localSurface.p[0];
    float eyeHeight=dot(n,eye-anchor);
    if(eyeHeight>=-.0002)return nativeScene;
    vec3 source,bottomView;
    if(!waterResolveSnapshot(pixel,size,source,bottomView))return nativeScene;
    vec3 bottom=viewToPlayerPosition(bottomView);
    vec4 normalRecord=texelFetch(colortex1,pixel,0);
    vec3 bedNormal=mat3(gbufferModelViewInverse)*(normalRecord.xyz*2.0-1.0);
    if(!waterTraceFinite4(normalRecord)||normalRecord.a!=1.0||!causticFinite3(bedNormal)
       ||dot(bedNormal,bedNormal)<=1e-12||normalize(bedNormal).y<.99999
       ||abs(bottom.y-localSurface.bedTop)>.002)return nativeScene;
    float drop=dot(n,anchor-bottom),distance=length(bottom-eye);
    if(drop<.08||drop>.5||distance<=length(nearPoint-eye)||distance>1.5)return nativeScene;
    vec3 topEye=eye-n*eyeHeight,topBed=bottom+n*drop;
    if(!nearClipColumnCoverage(topEye,topBed,localSurface))return nativeScene;
    WaterParams params=waterParams();
    float cosine=clamp(dot(normalize(light),n),0.0,1.0);
    float waterCosine=sqrt(max(1.0-(1.0-cosine*cosine)/(params.refractiveIndex*params.refractiveIndex),0.0));
    vec3 incident=-normalize(light),refracted=refract(incident,n,1.0/params.refractiveIndex);
    if(!causticFinite3(refracted)||dot(refracted,n)>=-.1)return nativeScene;
    float incoming=drop/max(waterCosine,.001);
    vec3 entry=bottom-refracted*incoming;
    if(!nearClipColumnCoverage(topBed,entry,localSurface))return nativeScene;
    // No view interface is crossed, so no additional Fresnel or air fog here.
    // No unseen lightmap is invented: use only paired radiance with the existing
    // bounded residual-scatter approximation, zero extra sky/block source.
    return waterTransportRadiance(source,share,distance*params.worldBlockMeters,
                                   incoming*params.worldBlockMeters,0.0,0.0,vec3(0));
}
#endif
#endif
