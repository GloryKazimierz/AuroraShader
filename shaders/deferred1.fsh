#version 330 compatibility
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_screen_reflection_settings.glsl"
#include "/lib/position.glsl"
uniform sampler2D colortex5;
uniform sampler2D colortex6;
uniform sampler2D depthtex1;
layout(location = 0) out float nearestViewDepth;
#if defined(AURORA_WATER_OPTICS_ACTIVE) && WATER_TRACE_TILES == 1 && WATER_SCREEN_REFLECTIONS == 1
/* RENDERTARGETS: 10 */
/*
const int colortex10Format = R32F;
*/
const bool colortex10Clear = true;
const vec4 colortex10ClearColor = vec4(-1.0,0.0,0.0,0.0);
#else
/* RENDERTARGETS: 0 */
#endif
void main() {
    nearestViewDepth = -1.0;
#if defined(AURORA_WATER_OPTICS_ACTIVE) && WATER_TRACE_TILES == 1 && WATER_SCREEN_REFLECTIONS == 1
    ivec2 size = textureSize(depthtex1,0);
    if (any(notEqual(textureSize(colortex5,0),size)) || any(notEqual(textureSize(colortex6,0),size))) return;
    ivec2 origin = 8 * ivec2(gl_FragCoord.xy);
    if (any(greaterThanEqual(origin,size))) return;
    float nearest = 1e20;
    for (int y=0; y<8; ++y) {
        for (int x=0; x<8; ++x) {
            ivec2 pixel = origin + ivec2(x,y);
            if (any(greaterThanEqual(pixel,size))) continue;
            float depth = texelFetch(depthtex1,pixel,0).r;
            float savedDepth = texelFetch(colortex6,pixel,0).r;
            vec4 source = texelFetch(colortex5,pixel,0);
            if (isnan(depth) || isinf(depth) || depth < 0.0 || depth > 1.0
                || any(isnan(source)) || any(isinf(source))) return;
            if (source.a == 0.0) {
                if (any(notEqual(source.rgb,vec3(0.0))) || savedDepth != 1.0) return;
            } else if (source.a != 1.0 || savedDepth != depth || depth >= 1.0
                       || any(lessThan(source.rgb,vec3(0.0))) || any(greaterThan(source.rgb,vec3(65504.0)))) return;
            if (depth == 1.0) continue;
            vec2 ndc = 2.0*(vec2(pixel)+0.5)/vec2(size)-1.0;
            vec4 h = gbufferProjectionInverse*vec4(ndc,2.0*depth-1.0,1.0);
            if (any(isnan(h)) || any(isinf(h)) || h.w<=1e-6) return;
            float viewDepth = -h.z/h.w;
            if (!(viewDepth>0.0) || isinf(viewDepth)) return;
            nearest = min(nearest,viewDepth);
        }
    }
    nearestViewDepth = nearest;
#endif
}
