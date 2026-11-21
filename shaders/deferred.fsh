#version 330 compatibility
#include "/lib/lighting_settings.glsl"
#include "/lib/lighting.glsl"
#include "/lib/shadow.glsl"
#include "/lib/celestial_lighting.glsl"
#include "/lib/fog.glsl"
#include "/lib/water_scene_snapshot.glsl"
uniform sampler2D colortex0;
uniform sampler2D colortex1;
uniform sampler2D colortex2;
uniform sampler2D depthtex2;

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

// Water tracing infrastructure: full-resolution, read-only throughout later geometry.
// Buffer 5 stores pre-camera-fog linear radiance and validity; buffer 6 stores matched depth.
/*
const int colortex5Format = RGBA16F;
const int colortex6Format = R32F;
*/
const bool colortex5Clear = true;
const bool colortex6Clear = true;
const vec4 colortex5ClearColor = vec4(0.0);
const vec4 colortex6ClearColor = vec4(1.0, 0.0, 0.0, 0.0);

/* RENDERTARGETS: 0,5,6 */
layout(location = 0) out vec4 color;
layout(location = 1) out vec4 waterSceneColor;
layout(location = 2) out float waterSceneDepth;
in vec2 texcoord;
void main() {
    // Integer texel fetch avoids blending normals across object silhouettes.
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex0, pixel, 0);
    vec4 surface = texelFetch(colortex1, pixel, 0);
    color = scene;
    waterSceneColor = vec4(0.0);
    waterSceneDepth = 1.0;
    if (surface.a > 0.5) {
        vec2 levels = texelFetch(colortex2, pixel, 0).rg;
        vec3 normalView = decodeNormal(surface.rgb);
        float visibility = shadowVisibility(pixel, normalView, shadowLightPosition);
        color.rgb = lightScene(scene.rgb, normalView, levels, visibility);
        color.rgb = applyCelestialPalette(color.rgb, normalView, levels, visibility);
        // Fog is added AFTER direct/ambient lighting, so shadows cannot darken its color.
        float surfaceDepth = texelFetch(depthtex1, pixel, 0).r;
        // Capture the same lit surface before applying camera-to-surface atmosphere.
        // Later reflection/transmission rays need their own path-dependent attenuation.
        encodeWaterSceneSnapshot(color.rgb, surface.a, surfaceDepth,
            texelFetch(depthtex2, pixel, 0).r, waterSceneColor, waterSceneDepth);
        if (surfaceDepth < 1.0) {
            vec2 screenUV = (vec2(pixel) + 0.5) / vec2(textureSize(depthtex1, 0));
            color.rgb = applyAtmosphericFog(color.rgb, reconstructViewPosition(screenUV, surfaceDepth));
        }
    }
    // Alpha is unchanged. Iris flips colortex0 after this fullscreen pass.
    // Most transparent geometry renders afterward using its original shading.
}
