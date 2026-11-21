#version 330 compatibility
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_refraction_settings.glsl"
uniform sampler2D colortex1, colortex5, colortex6, colortex7, colortex8, colortex9;
uniform sampler2D depthtex0, depthtex1;
uniform mat4 gbufferProjectionInverse;
uniform vec3 upPosition;
layout(location=0) out vec4 planarBounds;
#if defined(AURORA_WATER_OPTICS_ACTIVE) && WATER_REFRACTION > 0
/* RENDERTARGETS: 11 */
/*
const int colortex11Format = RGBA32F;
*/
const bool colortex11Clear = false;
#else
/* RENDERTARGETS: 0 */
#endif
bool finite4(vec4 v){return !any(isnan(v))&&!any(isinf(v));}
bool pointAt(ivec2 pixel,float depth,ivec2 size,out vec3 point){
    vec4 h=gbufferProjectionInverse*vec4((vec2(pixel)+.5)/vec2(size)*2.0-1.0,depth*2.0-1.0,1.0);
    if(!finite4(h)||h.w<=1e-6)return false;
    point=h.xyz/h.w;return !any(isnan(point))&&!any(isinf(point));
}
void main(){
    // Invalid interval has min > max. Every scheduled output texel is written.
    planarBounds=vec4(1e20,-1e20,1e20,-1e20);
#if defined(AURORA_WATER_OPTICS_ACTIVE) && WATER_REFRACTION > 0
    ivec2 size=textureSize(colortex7,0),origin=ivec2(gl_FragCoord.xy)*8;
    if(any(lessThan(size,ivec2(10)))||any(lessThan(origin,ivec2(1)))||any(greaterThanEqual(origin+8,size)))return;
    if(any(notEqual(size,textureSize(colortex1,0)))||any(notEqual(size,textureSize(colortex5,0)))
       ||any(notEqual(size,textureSize(colortex6,0)))||any(notEqual(size,textureSize(colortex8,0)))
       ||any(notEqual(size,textureSize(colortex9,0)))||any(notEqual(size,textureSize(depthtex0,0)))
       ||any(notEqual(size,textureSize(depthtex1,0))))return;
    if(any(isnan(upPosition))||any(isinf(upPosition))||dot(upPosition,upPosition)<=1e-12)return;
    vec3 up=normalize(upPosition);
    vec4 interval=vec4(1e20,-1e20,1e20,-1e20);
    // One-pixel halo includes every final 3x3 footprint centered in this tile.
    for(int y=-1;y<=8;++y)for(int x=-1;x<=8;++x){
        ivec2 pixel=origin+ivec2(x,y);
        vec4 scene=texelFetch(colortex5,pixel,0);
        vec4 record=texelFetch(colortex7,pixel,0);
        vec4 owner=texelFetch(colortex8,pixel,0);
        vec4 bedNormal=texelFetch(colortex1,pixel,0);
        float bedDepth=texelFetch(colortex6,pixel,0).r;
        float opaque=texelFetch(depthtex1,pixel,0).r;
        float finalDepth=texelFetch(depthtex0,pixel,0).r;
        float q=texelFetch(colortex9,pixel,0).r;
        if(!finite4(scene)||scene.a!=1.0||any(lessThan(scene.rgb,vec3(0)))||any(greaterThan(scene.rgb,vec3(65504)))
           ||!finite4(record)||record.a<0.0||record.a>=1.0||abs(dot(record.xyz,record.xyz)-1.0)>.001
           ||dot(record.xyz,up)<=.65||!finite4(owner)||abs(owner.r*255.0-1.0)>.002||owner.a!=0.0
           ||any(lessThan(owner.gb,vec2(0)))||any(greaterThan(owner.gb,vec2(1)))
           ||isnan(q)||isinf(q)||q<0.0||q>1.0
           ||isnan(bedDepth)||isinf(bedDepth)||bedDepth<0.0||bedDepth>=1.0||bedDepth!=opaque||bedDepth<=record.a
           ||isnan(finalDepth)||isinf(finalDepth)||abs(record.a-finalDepth)>1.0/16777215.0
           ||!finite4(bedNormal)||bedNormal.a<.5)return;
        vec3 n=bedNormal.xyz*2.0-1.0;
        if(abs(dot(n,n)-1.0)>.003||dot(normalize(n),up)<.99999)return;
        vec3 waterPoint,bedPoint;
        if(!pointAt(pixel,record.a,size,waterPoint)||!pointAt(pixel,bedDepth,size,bedPoint))return;
        float waterHeight=dot(up,waterPoint),bedHeight=dot(up,bedPoint);
        if(waterHeight-bedHeight<=.001)return;
        interval.x=min(interval.x,waterHeight);interval.y=max(interval.y,waterHeight);
        interval.z=min(interval.z,bedHeight);interval.w=max(interval.w,bedHeight);
        // Restrict the fast route to nearly constant *geometric* heights.
        // Filtered shading waves do not affect these reconstructed positions.
        if(interval.y-interval.x>.004||interval.w-interval.z>.004)return;
    }
    planarBounds=interval;
#endif
}
