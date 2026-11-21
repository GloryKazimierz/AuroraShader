#version 330 compatibility
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_resolve.glsl"
uniform sampler2D colortex0;
in vec2 texcoord;
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
    color = scene;
#ifdef AURORA_WATER_OPTICS_ACTIVE
    color.rgb = resolveWaterOptics(scene.rgb, pixel, textureSize(colortex0, 0));
#endif
    // Full-resolution water optics precedes bloom; alpha is always copied exactly.
}
