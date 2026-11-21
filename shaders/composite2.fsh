#version 330 compatibility
#include "/lib/bloom.glsl"
uniform sampler2D colortex3;
in vec2 texcoord;
/* RENDERTARGETS: 4 */
layout(location = 0) out vec4 color;
void main() {
    color = vec4(0.0);
    if (!bloomActive()) return;
    color = vec4(blurBloom(colortex3, ivec2(gl_FragCoord.xy), ivec2(1, 0)), 0.0);
}
