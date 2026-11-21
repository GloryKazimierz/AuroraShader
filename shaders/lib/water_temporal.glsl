#ifndef AURORA_WATER_TEMPORAL_INCLUDED
#define AURORA_WATER_TEMPORAL_INCLUDED
#include "/lib/water_temporal_settings.glsl"
#ifdef AURORA_WATER_TEMPORAL_ACTIVE
#include "/lib/position.glsl"
#include "/lib/celestial.glsl"
/*
const int colortex12Format = RGBA32F;
const bool colortex12Clear = false;
const vec4 colortex12ClearColor = vec4(0.0);
*/
uniform sampler2D colortex7,colortex8,colortex12,depthtex0;
uniform mat4 gbufferProjection,gbufferPreviousProjection,gbufferPreviousModelView;
uniform ivec3 cameraPositionInt,previousCameraPositionInt;
uniform vec3 cameraPositionFract,previousCameraPositionFract;
uniform int frameCounter;
uniform float frameTime,frameTimeCounter;
uniform ivec3 currentDate,currentTime;

bool waterTemporalFinite(float x){return !isnan(x)&&!isinf(x);}
bool waterTemporalFinite3(vec3 x){return !any(isnan(x))&&!any(isinf(x));}
bool waterTemporalFinite4(vec4 x){return !any(isnan(x))&&!any(isinf(x));}
bool waterTemporalMatrix(mat4 m){
    for(int i=0;i<4;++i)if(!waterTemporalFinite4(m[i]))return false;
    return abs(determinant(m))>1e-8;
}
bool waterTemporalReserved(ivec2 pixel){return pixel.y==0&&pixel.x<2;}
float waterTemporalMedium(){return float((hasSkylight?1:0)+(hasCeiling?2:0)+4*isEyeInWater);}
float waterTemporalDate(){return float(currentDate.x*372+currentDate.y*31+currentDate.z);}
float waterTemporalSecond(){return float(currentTime.x*3600+currentTime.y*60+currentTime.z);}
bool waterTemporalClock(){
    return frameCounter>=0&&frameCounter<=720719&&waterTemporalFinite(frameTimeCounter)
        &&frameTimeCounter>=0.0&&frameTimeCounter<3600.0
        &&currentDate.x>=2000&&currentDate.x<=9999&&currentDate.y>=1&&currentDate.y<=12
        &&currentDate.z>=1&&currentDate.z<=31
        &&all(greaterThanEqual(currentTime,ivec3(0)))&&all(lessThan(currentTime,ivec3(24,60,60)))
        &&isEyeInWater>=0&&isEyeInWater<=3;
}
bool waterTemporalSurface(ivec2 pixel,ivec2 size,out vec3 playerPoint,out float packedDepth){
    playerPoint=vec3(0);packedDepth=2.0;
    if(any(lessThan(pixel,ivec2(0)))||any(greaterThanEqual(pixel,size))||waterTemporalReserved(pixel))return false;
    vec4 surface=texelFetch(colortex7,pixel,0),owner=texelFetch(colortex8,pixel,0);
    float depth=texelFetch(depthtex0,pixel,0).r;
    if(!waterTemporalFinite4(surface)||!waterTemporalFinite4(owner)||!waterTemporalFinite(depth)
       ||abs(owner.r*255.0-1.0)>.002||any(lessThan(owner.gb,vec2(0)))||any(greaterThan(owner.gb,vec2(1)))
       ||abs(dot(surface.xyz,surface.xyz)-1.0)>.001||depth<=0.0||depth>=1.0
       ||surface.a<=0.0||surface.a>=1.0||abs(depth-surface.a)>1.0/16777215.0)return false;
    bool exit=abs(owner.a*255.0-1.0)<=.002;
    if(!(owner.a==0.0||exit)||exit!=(isEyeInWater==1))return false;
    if(!waterTemporalFinite3(upPosition)||dot(upPosition,upPosition)<=1e-8
       ||dot(surface.xyz,normalize(upPosition))<.65)return false;
    vec2 uv=(vec2(pixel)+.5)/vec2(size);
    vec4 view=gbufferProjectionInverse*vec4(uv*2.0-1.0,depth*2.0-1.0,1.0);
    if(!waterTemporalFinite4(view)||view.w<=1e-6)return false;
    playerPoint=(gbufferModelViewInverse*vec4(view.xyz/view.w,1)).xyz;
    if(!waterTemporalFinite3(playerPoint))return false;
    // Sign carries the proven interface side without losing one bit of raw depth.
    packedDepth=exit?-depth:depth;return true;
}
bool waterTemporalHeader(ivec2 size){
    if(!waterTemporalClock()||!waterTemporalFinite(frameTime)||frameTime<=0.0||frameTime>.1
       ||frameTimeCounter<2.1)return false;
    vec4 a=texelFetch(colortex12,ivec2(0,0),0),b=texelFetch(colortex12,ivec2(1,0),0);
    float expectedFrame=frameCounter==0?720720.0:float(frameCounter);
    if(!waterTemporalFinite4(a)||!waterTemporalFinite4(b)||a.x!=expectedFrame
       ||any(notEqual(a.yz,vec2(size)))||a.w!=waterTemporalMedium()
       ||b.x<0.0||b.x>=3600.0||b.z!=waterTemporalDate()||b.w!=1.0)return false;
    float secondsAge=waterTemporalSecond()-b.y;
    if(secondsAge<0.0||secondsAge>1.0)return false;
    float expectedTimer=b.x+frameTime;
    if(expectedTimer>=3600.0)expectedTimer=0.0;
    // Cached dimension pipelines retain images, while new pipelines reset global
    // counters. Consecutive timer+frame, <=1s wall age and 2.1s reset warm-up jointly
    // reject a cached old history whose numerical frame happens to recur.
    return abs(expectedTimer-frameTimeCounter)<=.001;
}
bool waterTemporalPrevious(vec3 point,float packedDepth,ivec2 size,out vec3 history){
    history=vec3(0);
    if(!waterTemporalHeader(size)||!waterTemporalMatrix(gbufferPreviousProjection)
       ||!waterTemporalMatrix(gbufferPreviousModelView)||!waterTemporalMatrix(gbufferModelViewInverse)
       ||!waterTemporalFinite3(cameraPositionFract)||!waterTemporalFinite3(previousCameraPositionFract))return false;
    if(any(greaterThan(abs(vec3(cameraPositionInt)-vec3(previousCameraPositionInt)),vec3(16))))return false;
    vec3 delta=vec3(cameraPositionInt-previousCameraPositionInt)+cameraPositionFract-previousCameraPositionFract;
    if(length(delta)>4.0)return false;
    mat4 oldInverse=inverse(gbufferPreviousModelView),oldProjectionInverse=inverse(gbufferPreviousProjection);
    vec3 oldForward=normalize(mat3(oldInverse)*vec3(0,0,-1));
    vec3 newForward=normalize(mat3(gbufferModelViewInverse)*vec3(0,0,-1));
    if(dot(oldForward,newForward)<.9)return false;
    for(int i=0;i<4;++i)if(any(greaterThan(abs(gbufferPreviousProjection[i]-gbufferProjection[i]),vec4(1e-4))))return false;
    vec3 oldPoint=point+delta;
    vec4 clip=gbufferPreviousProjection*gbufferPreviousModelView*vec4(oldPoint,1);
    if(!waterTemporalFinite4(clip)||clip.w<=1e-6)return false;
    vec2 uv=clip.xy/clip.w*.5+.5;
    if(any(lessThan(uv,vec2(0)))||any(greaterThanEqual(uv,vec2(1))))return false;
    ivec2 pixel=ivec2(uv*vec2(size));
    if(waterTemporalReserved(pixel))return false;
    vec4 stored=texelFetch(colortex12,pixel,0);
    if(!waterTemporalFinite4(stored)||abs(stored.a)<=0.0||abs(stored.a)>=1.0
       ||(stored.a<0.0)!=(packedDepth<0.0)||any(lessThan(stored.rgb,vec3(0)))
       ||any(greaterThan(stored.rgb,vec3(65504))))return false;
    // Compare like ray centers: intersect this old pixel's center ray with the
    // CURRENT physical horizontal plane, then compare full FP32 raw depths.
    vec2 center=(vec2(pixel)+.5)/vec2(size);
    vec4 rayH=oldProjectionInverse*vec4(center*2.0-1.0,0,1);
    if(!waterTemporalFinite4(rayH)||rayH.w<=1e-6)return false;
    vec3 ray=mat3(oldInverse)*(rayH.xyz/rayH.w),origin=oldInverse[3].xyz;
    if(!waterTemporalFinite3(ray)||abs(ray.y)<=1e-5)return false;
    float distance=(oldPoint.y-origin.y)/ray.y;
    if(!waterTemporalFinite(distance)||distance<=0.0)return false;
    vec4 plane=gbufferPreviousProjection*gbufferPreviousModelView*vec4(origin+distance*ray,1);
    if(!waterTemporalFinite4(plane)||plane.w<=1e-6)return false;
    float expectedDepth=plane.z/plane.w*.5+.5;
    if(abs(expectedDepth-abs(stored.a))>4.0/16777215.0)return false;
    history=stored.rgb;return true;
}
vec3 resolveWaterTemporal(sampler2D currentScene,vec3 current,ivec2 pixel,ivec2 size,out vec4 nextHistory){
    nextHistory=vec4(0,0,0,2);
    if(any(lessThan(size,ivec2(2,1)))||any(notEqual(size,textureSize(colortex12,0))))return current;
    if(waterTemporalReserved(pixel)){
        if(waterTemporalClock())nextHistory=pixel.x==0?vec4(float(frameCounter+1),vec2(size),waterTemporalMedium())
            :vec4(frameTimeCounter,waterTemporalSecond(),waterTemporalDate(),1);
        else nextHistory=vec4(0);
        return current;
    }
    if(!hasSkylight||hasCeiling||isEyeInWater>1||!waterTemporalFinite(blindness)||!waterTemporalFinite(darknessFactor)
       ||blindness>0.0||darknessFactor>0.0||!waterTemporalFinite3(current)
       ||any(lessThan(current,vec3(0)))||any(greaterThan(current,vec3(65504)))
       ||any(notEqual(size,textureSize(colortex7,0)))||any(notEqual(size,textureSize(colortex8,0)))
       ||any(notEqual(size,textureSize(depthtex0,0))))return current;
    vec3 point;float packedDepth;
    if(!waterTemporalSurface(pixel,size,point,packedDepth))return current;
    vec3 history;
    if(!waterTemporalPrevious(point,packedDepth,size,history)){nextHistory=vec4(current,packedDepth);return current;}
    vec3 low=current,high=current;
    const ivec2 offsets[4]=ivec2[4](ivec2(1,0),ivec2(-1,0),ivec2(0,1),ivec2(0,-1));
    for(int i=0;i<4;++i){
        ivec2 neighbor=pixel+offsets[i];vec3 neighborPoint;float neighborDepth;
        if(!waterTemporalSurface(neighbor,size,neighborPoint,neighborDepth)
           ||(neighborDepth<0.0)!=(packedDepth<0.0)||abs(neighborPoint.y-point.y)>.03)continue;
        vec3 value=texelFetch(currentScene,neighbor,0).rgb;
        if(!waterTemporalFinite3(value)||any(lessThan(value,vec3(0)))||any(greaterThan(value,vec3(65504))))continue;
        low=min(low,value);high=max(high,value);
    }
    history=clamp(history,low,high);
    vec3 difference=abs(history-current)/max(max(history,current),vec3(.05));
    float reactive=smoothstep(.10,.30,max(max(difference.x,difference.y),difference.z));
    float weight=min(.9,exp(-frameTime/.08))*(1.0-reactive);
    vec3 filtered=mix(current,history,weight);
    nextHistory=vec4(filtered,packedDepth);
    return filtered;
}
#endif
#endif
