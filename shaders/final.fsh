#version 330 compatibility
#include "/lib/settings.glsl"
#include "/lib/color.glsl"
// final writes directly to the screen, not back into colortex0.
// Opaque + translucent gbuffers have already built the complete scene.
uniform sampler2D colortex0;
in vec2 texcoord;
layout(location = 0) out vec4 color;
void main() {
    vec4 scene = texture(colortex0, texcoord);
    color = vec4(gradeColor(scene.rgb), scene.a);
}
