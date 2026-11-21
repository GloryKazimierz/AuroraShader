#version 330 compatibility
#include "/lib/bloom.glsl"
uniform sampler2D colortex0;
uniform sampler2D colortex3;
in vec2 texcoord;
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
    // Preserve the complete original value for legacy/debug/off/zero-strength paths.
    color = scene;
    if (!bloomActive()) return;
    vec2 uv = (vec2(pixel) + 0.5) / vec2(textureSize(colortex0, 0));
    vec3 glow = upsampleBloom(colortex3, uv);
    color = vec4(bloomSafe(bloomSafe(scene.rgb) + max(BLOOM_STRENGTH, 0.0) * glow), scene.a);
    // Exposure, tone mapping and display encoding remain solely in final.
}
