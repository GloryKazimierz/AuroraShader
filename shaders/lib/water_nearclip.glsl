#ifndef AURORA_WATER_NEARCLIP_INCLUDED
#define AURORA_WATER_NEARCLIP_INCLUDED
#include "/lib/water_nearclip_settings.glsl"
#ifdef AURORA_WATER_NEARCLIP_ACTIVE
#include "/lib/water_caustics.glsl"
// Geometry comes from raw matched depth; packed wave normals never move the interface.
struct WaterNearPatch { vec3 p[4]; vec3 normal; float bedTop; float bedBottom; ivec2 key; };
struct WaterNearResult { int medium; float waterLength; vec3 crossing; vec3 normal; bool crossed; bool integralValid; int reason; };
bool nearClipPatch(vec3 query,out WaterNearPatch result) {
    ivec2 size=textureSize(shadowcolor0,0);
    if(any(lessThan(size,ivec2(4)))||any(notEqual(size,textureSize(shadowtex0,0)))
       ||any(notEqual(size,textureSize(shadowtex1,0))))return false;
    vec3 uv;if(!causticProject(query,uv))return false;
    ivec2 first=ivec2(floor(uv.xy*vec2(size)-.5));result.key=first;
    if(any(lessThan(first,ivec2(1)))||any(greaterThanEqual(first+1,size-1)))return false;
    float waterMin=1e20,waterMax=-1e20,bedMin=1e20,bedMax=-1e20;
    for(int i=0;i<4;++i){
        ivec2 p=first+ivec2(i%2,i/2);
        float front=texelFetch(shadowtex0,p,0).r,back=texelFetch(shadowtex1,p,0).r;
        vec3 opticalNormal,bed;
        if(!decodeWaterCaustic(texelFetch(shadowcolor0,p,0),front,opticalNormal)
           ||!causticFinite(back)||back<=front+1.0/16777215.0||back>=1.0
           ||!causticUnproject((vec2(p)+.5)/vec2(size),front,result.p[i])
           ||!causticUnproject((vec2(p)+.5)/vec2(size),back,bed))return false;
        waterMin=min(waterMin,result.p[i].y);waterMax=max(waterMax,result.p[i].y);
        bedMin=min(bedMin,bed.y);bedMax=max(bedMax,bed.y);
    }
    vec3 n=cross(result.p[1]-result.p[0],result.p[2]-result.p[0]);
    if(!causticFinite3(n)||dot(n,n)<=1e-14)return false;
    n=normalize(n);if(n.y<0.0)n=-n;
    if(n.y<.995||abs(dot(n,result.p[3]-result.p[0]))>.002)return false;
    if(length(result.p[1]-result.p[0])>.5||length(result.p[2]-result.p[0])>.5
       ||length(result.p[3]-result.p[1])>.5||length(result.p[3]-result.p[2])>.5
       ||waterMax-waterMin>.004||bedMax-bedMin>.025||waterMin-bedMax<.08)return false;
    result.normal=n;result.bedTop=bedMax;result.bedBottom=bedMin;return true;
}
vec3 nearClipBarycentric(vec3 p,vec3 a,vec3 v0,vec3 v1,float d00,float d01,float d11,float denominator){
    vec3 d=p-a;float d20=dot(d,v0),d21=dot(d,v1);
    float y=(d11*d20-d01*d21)/denominator,z=(d00*d21-d01*d20)/denominator;
    return vec3(1.0-y-z,y,z);
}
bool nearClipTriangleInterval(vec3 start,vec3 finish,vec3 a,vec3 b,vec3 c,out vec2 interval){
    vec3 v0=b-a,v1=c-a;
    float d00=dot(v0,v0),d01=dot(v0,v1),d11=dot(v1,v1),denominator=d00*d11-d01*d01;
    interval=vec2(0,1);if(denominator<=1e-14)return false;
    vec3 first=nearClipBarycentric(start,a,v0,v1,d00,d01,d11,denominator);
    vec3 last=nearClipBarycentric(finish,a,v0,v1,d00,d01,d11,denominator);
    for(int i=0;i<3;++i){
        float delta=last[i]-first[i];
        if(abs(delta)<1e-12){if(first[i]<0.0)return false;}
        else if(delta>0.0)interval.x=max(interval.x,-first[i]/delta);
        else interval.y=min(interval.y,-first[i]/delta);
    }
    return interval.y>=interval.x;
}
bool nearClipCovered(vec3 start,vec3 finish,WaterNearPatch a,WaterNearPatch b){
    vec2 intervals[4];
    for(int i=0;i<4;++i)intervals[i]=vec2(2,-1);
    vec2 value;
    if(nearClipTriangleInterval(start,finish,a.p[0],a.p[1],a.p[2],value))intervals[0]=value;
    if(nearClipTriangleInterval(start,finish,a.p[3],a.p[2],a.p[1],value))intervals[1]=value;
    if(nearClipTriangleInterval(start,finish,b.p[0],b.p[1],b.p[2],value))intervals[2]=value;
    if(nearClipTriangleInterval(start,finish,b.p[3],b.p[2],b.p[1],value))intervals[3]=value;
    float covered=0.0;
    for(int step=0;step<4;++step)for(int i=0;i<4;++i)
        if(intervals[i].x<=covered+1e-6)covered=max(covered,intervals[i].y);
    return covered>=1.0-1e-6;
}
float nearClipWaterFraction(float eyeHeight,float nearHeight) {
    if(eyeHeight<0.0 && nearHeight<0.0)return 1.0;
    if(eyeHeight>=0.0 && nearHeight>=0.0)return 0.0;
    float t=eyeHeight/(eyeHeight-nearHeight);
    return eyeHeight<0.0?t:1.0-t;
}
// Caller passes current native ownership and paired depth. UNKNOWN means no color replacement.
WaterNearResult classifyWaterNearClip(vec3 eye,vec3 nearPoint,vec3 towardLight,
                                      vec4 nativeOwner,float currentDepth,float opaqueDepth,float share){
    WaterNearResult result=WaterNearResult(0,0.0,vec3(0),vec3(0),false,false,1);
    if(!causticFinite3(eye)||!causticFinite3(nearPoint)||!causticFinite3(towardLight)
       ||dot(towardLight,towardLight)<=1e-12||normalize(towardLight).y<.15
       ||any(isnan(nativeOwner))||any(isinf(nativeOwner))||any(notEqual(nativeOwner,vec4(0)))
       ||!causticFinite(currentDepth)||!causticFinite(opaqueDepth)
       ||currentDepth<0.0||currentDepth>=1.0||opaqueDepth<0.0||opaqueDepth>=1.0
       ||abs(currentDepth-opaqueDepth)>1.0/16777215.0||!causticFinite(share)||share<0.0||share>1.0)return result;
    WaterNearPatch initial,a,b;result.reason=2;
    if(!nearClipPatch(eye,initial))return result;
    vec3 n=initial.normal,anchor=initial.p[0];
    float se=dot(n,eye-anchor),sn=dot(n,nearPoint-anchor);
    result.reason=3;if(abs(se)>.05)return result;
    vec3 footEye=eye-n*se,footNear=nearPoint-n*sn;
    result.reason=4;
    if(!nearClipPatch(footEye,a)||!nearClipPatch(footNear,b))return result;
    result.reason=5;
    if(dot(n,a.normal)<.99999||dot(n,b.normal)<.99999)return result;
    for(int i=0;i<4;++i)
        if(abs(dot(n,a.p[i]-anchor))>.002||abs(dot(n,b.p[i]-anchor))>.002)return result;
    result.reason=6;if(!nearClipCovered(footEye,footNear,a,b))return result;
    result.reason=7;
    // A conservative engineering uncertainty band for depth storage, raster depth
    // interpolation and rigid inverse transforms. The factor is intentionally
    // larger than D24 quantization alone; it is not an arbitrary-world proof.
    vec3 depthStart,depthEnd;
    if(!causticUnproject(vec2(.5),0.0,depthStart)
       ||!causticUnproject(vec2(.5),.999999,depthEnd))return result;
    float uncertainty=max(.0001,16.0*1.1920928955078125e-7*length(depthEnd-depthStart));
    if(abs(sn)<=uncertainty||nearPoint.y<=max(a.bedTop,b.bedTop)+.01)return result;
    float distance=length(nearPoint-eye);
    if(!causticFinite(distance)||distance<=0.0)return result;
    if(se*sn<0.0){
        float t=se/(se-sn);result.crossing=mix(eye,nearPoint,t);
        result.waterLength=distance*(se<0.0?t:1.0-t);result.crossed=true;
    }else result.waterLength=sn<0.0?distance:0.0;
    result.medium=sn<0.0?2:1;result.normal=n;
    // Classification can be valid while an almost tangent crossing has an
    // unstable integral. Keep these contracts separate; color must require both.
    float lo=distance*nearClipWaterFraction(se+uncertainty,sn+uncertainty);
    float hi=distance*nearClipWaterFraction(se-uncertainty,sn-uncertainty);
    result.integralValid=max(result.waterLength-lo,hi-result.waterLength)<=.00025;
    result.reason=result.integralValid?0:8;
    if(!result.integralValid){result.waterLength=0.0;result.crossed=false;}
    return result;
}
#endif
#endif
