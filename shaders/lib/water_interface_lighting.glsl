#ifndef AURORA_WATER_INTERFACE_LIGHTING_INCLUDED
#define AURORA_WATER_INTERFACE_LIGHTING_INCLUDED
#include "/lib/water_screen_reflection.glsl"
#include "/lib/water_filtered_waves.glsl"
#include "/lib/water_shadow_bindings.glsl"
// Reusable finite horizontal-interface footprint and receiver visibility.
// Consumers include this only inside their optical-feature active path.
bool waterInterfaceScalar(float value) { return !isnan(value) && !isinf(value); }
bool waterInterfaceFootprint(ivec2 pixel, ivec2 size, vec3 playerPoint,
                            out vec2 worldDx, out vec2 worldDy) {
    worldDx=vec2(0.0);worldDy=vec2(0.0);
    vec3 origin=(gbufferModelViewInverse*vec4(0,0,0,1)).xyz;
    for(int axis=0;axis<2;++axis){
        vec2 uv=(vec2(pixel)+vec2(0.5)+vec2(axis==0?1.0:0.0,axis==1?1.0:0.0))/vec2(size);
        vec4 h=gbufferProjectionInverse*vec4(uv*2.0-1.0,0,1);
        if(!waterInterfaceScalar(h.w)||h.w<=1e-6)return false;
        vec3 direction=mat3(gbufferModelViewInverse)*(h.xyz/h.w);
        if(!waterTraceFinite3(direction)||direction.y>=-1e-5)return false;
        float distance=(playerPoint.y-origin.y)/direction.y;
        vec3 adjacent=origin+distance*direction;
        if(!waterInterfaceScalar(distance)||distance<=0.0||!waterTraceFinite3(adjacent))return false;
        if(axis==0)worldDx=adjacent.xz-playerPoint.xz;else worldDy=adjacent.xz-playerPoint.xz;
    }
    return waterWaveFootprintValid(worldDx,worldDy);
}
float waterInterfaceVisibility(vec3 viewPoint, vec3 normalView, vec3 lightDirection) {
#ifndef SHADOWS_ENABLED
    return 1.0;
#else
    ivec2 size=textureSize(shadowtex1,0);
    if(any(lessThanEqual(size,ivec2(0))))return 0.0;
    vec4 clip=shadowProjection*shadowModelView*vec4(viewToPlayerPosition(viewPoint),1);
    if(!waterTraceFinite4(clip)||clip.w<=1e-6)return 0.0;
    vec3 coordinate=clip.xyz/clip.w*.5+.5;
    if(any(lessThan(coordinate,vec3(0)))||any(greaterThanEqual(coordinate,vec3(1))))return 0.0;
    float receiver=coordinate.z-effectiveShadowBias(normalView,lightDirection);
    // Bounded stable 2x2 comparison filter. Unknown/out-of-map taps reject direct
    // illumination; skylight and local lamps remain independently available.
    vec2 texel=coordinate.xy*vec2(size)-.5;
    ivec2 base=ivec2(floor(texel));vec2 fraction=fract(texel);
    float visible=0.0;
    for(int y=0;y<2;++y)for(int x=0;x<2;++x){
        ivec2 p=base+ivec2(x,y);
        if(any(lessThan(p,ivec2(0)))||any(greaterThanEqual(p,size)))continue;
        float stored=texelFetch(shadowtex1,p,0).r;
        if(!waterInterfaceScalar(stored)||stored<0.0||stored>1.0)continue;
        float weight=(x==0?1.0-fraction.x:fraction.x)*(y==0?1.0-fraction.y:fraction.y);
        if(receiver<=stored)visible+=weight;
    }
    return visible;
#endif
}
#endif
