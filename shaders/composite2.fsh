#version 330 compatibility
#include "/lib/bloom.glsl"
uniform sampler2D colortex4;
in vec2 texcoord;
/* RENDERTARGETS: 3 */
layout(location = 0) out vec4 color;
void main() {
    color = vec4(0.0);
    if (!bloomActive()) return;
    color = vec4(blurBloom(colortex4, ivec2(gl_FragCoord.xy), ivec2(0, 1)), 0.0);
}
