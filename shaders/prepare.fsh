#version 330 compatibility
#include "/lib/scene_color.glsl"
uniform vec3 fogColor;
in vec2 texcoord;

// Iris reads these comments after preprocessing; enums must not enter active GLSL.
#if SCENE_COLOR_MODE == 0
/*
const int colortex0Format = RGBA8;
*/
#else
/*
const int colortex0Format = RGBA16F;
*/
const vec4 colortex0ClearColor = vec4(0.0, 0.0, 0.0, 1.0);
#endif

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
void main() {
    // Iris's default fog-color clear is display-encoded. Explicit initialization
    // ensures uncovered pixels and transparent backgrounds obey the scene contract.
    color = vec4(sceneFromDisplay(fogColor), 1.0);
}
