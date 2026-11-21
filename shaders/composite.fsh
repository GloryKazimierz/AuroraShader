#version 330 compatibility
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_resolve.glsl"
#include "/lib/water_underwater_resolve.glsl"
#include "/lib/water_glint.glsl"
#include "/lib/water_foam_resolve.glsl"
uniform sampler2D colortex0;
in vec2 texcoord;
#ifdef AURORA_WATER_FOAM_HISTORY
/* RENDERTARGETS: 0,13,14 */
layout(location = 1) out vec4 foamState;
layout(location = 2) out vec2 foamMetadata;
#else
/* RENDERTARGETS: 0 */
#endif
layout(location = 0) out vec4 color;
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
    color = scene;
#ifdef AURORA_WATER_OPTICS_ACTIVE
    color.rgb = resolveWaterOptics(scene.rgb, pixel, textureSize(colortex0, 0));
#endif
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
    color.rgb = resolveWaterUnderwater(color.rgb,pixel,textureSize(colortex0,0));
#endif
#ifdef AURORA_WATER_GLINT_ACTIVE
    color.rgb=applyWaterGlint(color.rgb,pixel,textureSize(colortex0,0));
#endif
#ifdef AURORA_WATER_FOAM_ACTIVE
    vec4 nextFoamState;vec2 nextFoamMetadata;
    color.rgb = resolveWaterFoam(color.rgb, pixel, textureSize(colortex0, 0), nextFoamState, nextFoamMetadata);
#ifdef AURORA_WATER_FOAM_HISTORY
    foamState=nextFoamState;foamMetadata=nextFoamMetadata;
#endif
#endif
    // Full-resolution water optics precedes bloom; alpha is always copied exactly.
}
