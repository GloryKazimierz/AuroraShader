#version 330 compatibility
#include "/lib/lighting_settings.glsl"
#include "/lib/lighting.glsl"
#include "/lib/shadow.glsl"
uniform sampler2D colortex0;
uniform sampler2D colortex1;
uniform sampler2D colortex2;

// Explicit precision and clears: a sky/background pixel must be invalid.
// RGBA16 avoids visible 8-bit quantization of rotating view-space normals.
/*
const int colortex1Format = RGBA16;
const int colortex2Format = RG16;
*/
const bool colortex1Clear = true;
const vec4 colortex1ClearColor = vec4(0.5, 0.5, 0.5, 0.0);
const bool colortex2Clear = true;
const vec4 colortex2ClearColor = vec4(0.0, 0.0, 0.0, 0.0);

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
in vec2 texcoord;
void main() {
    // Integer texel fetch avoids blending normals across object silhouettes.
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
    vec4 surface = texelFetch(colortex1, pixel, 0);
    color = scene;
    if (surface.a > 0.5) {
        vec2 levels = texelFetch(colortex2, pixel, 0).rg;
        float visibility = hardShadowVisibility(pixel);
        color.rgb = lightScene(scene.rgb, decodeNormal(surface.rgb), levels, visibility);
    }
    // Alpha is unchanged. Iris flips colortex0 after this fullscreen pass.
    // Most transparent geometry renders afterward using its original shading.
}
