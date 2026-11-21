#version 330 compatibility
#include "/lib/bloom.glsl"
#include "/lib/water_temporal.glsl"
uniform sampler2D colortex0;
uniform sampler2D colortex3;
in vec2 texcoord;
#ifdef AURORA_WATER_TEMPORAL_ACTIVE
/* RENDERTARGETS: 0,12 */
layout(location = 1) out vec4 waterHistory;
#else
/* RENDERTARGETS: 0 */
#endif
layout(location = 0) out vec4 color;
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
#ifdef AURORA_WATER_TEMPORAL_ACTIVE
    // History contains no bloom. Filter only proven water, then add this frame's
    // bloom once below. No jitter, exposure change or temporal glow feedback.
    scene.rgb = resolveWaterTemporal(colortex0,scene.rgb,pixel,textureSize(colortex0,0),waterHistory);
#endif
    // Preserve the complete original value for legacy/debug/off/zero-strength paths.
    color = scene;
    if (!bloomActive()) return;
    vec2 uv = (vec2(pixel) + 0.5) / vec2(textureSize(colortex0, 0));
    vec3 glow = upsampleBloom(colortex3, uv);
    color = vec4(bloomSafe(bloomSafe(scene.rgb) + max(BLOOM_STRENGTH, 0.0) * glow), scene.a);
    // Exposure, tone mapping and display encoding remain solely in final.
}
