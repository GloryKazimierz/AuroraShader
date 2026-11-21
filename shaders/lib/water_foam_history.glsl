#ifndef AURORA_WATER_FOAM_HISTORY_INCLUDED
#define AURORA_WATER_FOAM_HISTORY_INCLUDED
#ifdef AURORA_WATER_FOAM_HISTORY
/*
const int colortex13Format = RGBA16F;
const int colortex14Format = RG32F;
const bool colortex13Clear = false;
const bool colortex14Clear = false;
const vec4 colortex13ClearColor = vec4(0.0);
const vec4 colortex14ClearColor = vec4(0.0);
*/
// Persistent quality only. Iris full-clears BOTH sides on allocation/resize even
// with per-frame clearing disabled. Zero frame+1 is always an invalid record.
uniform sampler2D colortex13;
uniform sampler2D colortex14;
uniform int frameCounter;
uniform float frameTime;
uniform ivec3 previousCameraPositionInt;
uniform vec3 previousCameraPositionFract;
uniform mat4 gbufferPreviousModelView;
uniform mat4 gbufferPreviousProjection;

bool waterFoamMatrix(mat4 matrix) {
    for(int col=0;col<4;++col)if(!waterTraceFinite4(matrix[col]))return false;
    return abs(determinant(matrix))>1e-8;
}
vec2 waterFoamOctEncode(vec3 normal) {
    normal/=abs(normal.x)+abs(normal.y)+abs(normal.z);
    vec2 encoded=normal.xy;
    if(normal.z<0.0)encoded=(1.0-abs(encoded.yx))*vec2(encoded.x<0.0?-1.0:1.0,encoded.y<0.0?-1.0:1.0);
    return encoded;
}
vec3 waterFoamOctDecode(vec2 encoded) {
    vec3 normal=vec3(encoded,1.0-abs(encoded.x)-abs(encoded.y));
    if(normal.z<0.0)normal.xy=(1.0-abs(normal.yx))*vec2(normal.x<0.0?-1.0:1.0,normal.y<0.0?-1.0:1.0);
    return normalize(normal);
}
bool waterFoamPrevious(vec3 playerPoint, vec3 worldNormal, vec2 material,
                        WaterFoamFlow currentFlow, float strength, vec2 dx, vec2 dy,
                        ivec2 size, out vec2 coverageAge) {
    coverageAge=vec2(0.0);
    if(frameCounter<0||frameCounter>720719||!waterFoamFinite(frameTime)||frameTime<=0.0||frameTime>0.1
       ||any(notEqual(size,textureSize(colortex13,0)))||any(notEqual(size,textureSize(colortex14,0)))
       ||!waterFoamFinite3(previousCameraPositionFract)||!waterFoamFinite3(cameraPositionFract)
       ||!waterFoamMatrix(gbufferPreviousModelView)||!waterFoamMatrix(gbufferPreviousProjection)
       ||!waterFoamMatrix(gbufferModelViewInverse))return false;
    // Float precheck rejects enormous integer differences before integer subtraction.
    if(any(greaterThan(abs(vec3(cameraPositionInt)-vec3(previousCameraPositionInt)),vec3(16.0))))return false;
    vec3 cameraDelta=vec3(cameraPositionInt-previousCameraPositionInt)+cameraPositionFract-previousCameraPositionFract;
    if(length(cameraDelta)>8.0)return false;
    mat4 previousInverseView=inverse(gbufferPreviousModelView);
    mat4 previousInverseProjection=inverse(gbufferPreviousProjection);
    vec3 oldForward=normalize(mat3(previousInverseView)*vec3(0,0,-1));
    vec3 newForward=normalize(mat3(gbufferModelViewInverse)*vec3(0,0,-1));
    if(dot(oldForward,newForward)<0.70710678)return false;
    for(int col=0;col<4;++col)
        if(any(greaterThan(abs(gbufferPreviousProjection[col]-gbufferProjection[col]),vec4(1e-4))))return false;
    // frameTime is Iris's previous-frame duration: variable-cadence advection is
    // an approximation, constrained by the geometry checks below, not exact flow.
    float previousTime=mod(frameTimeCounter-frameTime+3600.0,3600.0);
    WaterFoamFlow oldFlow=waterFoamFlowAt(material,previousTime,strength,float(WATER_WAVE_SPEED),dx,dy);
    if(!oldFlow.valid)return false;
    vec2 displacement=oldFlow.displacement-currentFlow.displacement;
    vec3 previousPoint=playerPoint+cameraDelta+vec3(displacement.x,0,displacement.y);
    vec4 clip=gbufferPreviousProjection*gbufferPreviousModelView*vec4(previousPoint,1);
    if(!waterTraceFinite4(clip)||clip.w<=1e-6)return false;
    vec2 uv=clip.xy/clip.w*.5+.5;
    if(any(lessThan(uv,vec2(0)))||any(greaterThanEqual(uv,vec2(1))))return false;
    ivec2 p=ivec2(uv*vec2(size));
    vec4 state=texelFetch(colortex13,p,0);
    vec2 metadata=texelFetch(colortex14,p,0).rg;
    float expectedFrame=frameCounter==0?720720.0:float(frameCounter);
    if(!waterTraceFinite4(state)||!waterFoamFinite2(metadata)||metadata.y!=expectedFrame
       ||metadata.x<0.0||metadata.x>=1.0||state.x<0.0||state.x>0.6005||state.y<0.0||state.y>2.5
       ||any(greaterThan(abs(state.zw),vec2(1))))return false;
    vec3 oldNormal=waterFoamOctDecode(state.zw);
    if(dot(oldNormal,worldNormal)<0.98)return false;
    // Compare FULL-FLOAT historical depth against the current horizontal water
    // plane at that old pixel's center, rather than comparing different ray centers.
    vec2 center=(vec2(p)+.5)/vec2(size);
    vec4 rayH=previousInverseProjection*vec4(center*2.0-1.0,0,1);
    if(!waterTraceFinite4(rayH)||rayH.w<=1e-6)return false;
    vec3 origin=(previousInverseView*vec4(0,0,0,1)).xyz;
    vec3 ray=mat3(previousInverseView)*(rayH.xyz/rayH.w);
    if(!waterFoamFinite3(ray)||ray.y>=-1e-5)return false;
    float distance=(previousPoint.y-origin.y)/ray.y;
    if(!waterFoamFinite(distance)||distance<=0.0)return false;
    vec3 planePoint=origin+distance*ray;
    vec4 planeClip=gbufferPreviousProjection*gbufferPreviousModelView*vec4(planePoint,1);
    if(!waterTraceFinite4(planeClip)||planeClip.w<=1e-6)return false;
    float planeDepth=planeClip.z/planeClip.w*.5+.5;
    if(abs(planeDepth-metadata.x)>4.0/16777215.0)return false;
    coverageAge=vec2(min(state.x,0.6),state.y);
    return true;
}
#endif
#endif
