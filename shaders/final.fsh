#version 330 compatibility
#include "/lib/settings.glsl"
#include "/lib/scene_color.glsl"
#include "/lib/tone_mapping.glsl"
#include "/lib/color.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/lighting.glsl"
#include "/lib/shadow.glsl"
// Normal mode keeps Milestone 1 grading after deferred lighting/translucency.
// Debug reads raw surface buffers, bypassing grading and later color overlays.
uniform sampler2D colortex0;
uniform sampler2D colortex1;
uniform sampler2D colortex2;
#if DEBUG_VIEW == 7 || DEBUG_VIEW == 8 || DEBUG_VIEW == 9
#include "/lib/water_debug_view.glsl"
uniform sampler2D colortex7;
uniform sampler2D depthtex0;
#if DEBUG_VIEW == 9
uniform sampler2D depthtex2;
#endif
#endif
in vec2 texcoord;
layout(location = 0) out vec4 color;
void main() {
#if DEBUG_VIEW == 0
    vec4 scene = texture(colortex0, texcoord);
#if SCENE_COLOR_MODE == 0
    color = vec4(gradeColor(scene.rgb), scene.a);
#else
    // Exposure in linear light, one tone map, one display encode. Debug skips all three.
    vec3 exposed = max(scene.rgb, vec3(0.0)) * exp2(EXPOSURE);
    vec3 displayColor = linearToSrgb(toneMapScene(exposed));
    color = vec4(gradeColor(displayColor), scene.a);
#endif
#elif DEBUG_VIEW == 4
    color = vec4(vec3(rawShadowDepth(texcoord)), 1.0);
#elif DEBUG_VIEW == 7 || DEBUG_VIEW == 8 || DEBUG_VIEW == 9
    ivec2 debugSize = textureSize(colortex7, 0);
    vec3 debugColor = vec3(0.0);
    // Final can use a different viewport size: select the source texel by UV,
    // then reconstruct at that texel's center, not at the output window pixel.
    if (all(greaterThan(debugSize, ivec2(0)))
        && all(equal(debugSize, textureSize(depthtex0, 0)))
        && !any(isnan(texcoord)) && !any(isinf(texcoord))
        && all(greaterThanEqual(texcoord, vec2(0.0))) && all(lessThan(texcoord, vec2(1.0)))) {
        ivec2 pixel = min(ivec2(texcoord * vec2(debugSize)), debugSize - ivec2(1));
        float backgroundDepth = 1.0;
#if DEBUG_VIEW == 9
        if (all(equal(debugSize, textureSize(depthtex2, 0)))) {
            backgroundDepth = texelFetch(depthtex2, pixel, 0).r;
        }
#endif
        vec2 pixelCenterUV = (vec2(pixel) + 0.5) / vec2(debugSize);
        debugColor = waterDebugColor(texelFetch(colortex7, pixel, 0),
            texelFetch(depthtex0, pixel, 0).r, backgroundDepth, pixelCenterUV);
    }
    color = vec4(debugColor, 1.0);
#else
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 surface = texelFetch(colortex1, pixel, 0);
    vec3 debugColor = vec3(0.0); // Black = no valid recorded surface.
    if (surface.a > 0.5) {
        vec3 normalView = decodeNormal(surface.rgb);
#if DEBUG_VIEW == 1
        debugColor = normalView * 0.5 + 0.5;
#elif DEBUG_VIEW == 2
        debugColor = vec3(texelFetch(colortex2, pixel, 0).rg, 0.0);
#elif DEBUG_VIEW == 3
        debugColor = vec3(diffuseTerm(normalView));
#elif DEBUG_VIEW == 5
        debugColor = vec3(shadowVisibility(pixel, normalView, shadowLightPosition));
#elif DEBUG_VIEW == 6
        // Invalid metadata/sky is black. Valid but degenerate normals use max bias.
        if (texelFetch(depthtex1, pixel, 0).r < 1.0) {
            debugColor = vec3(shadowBiasDebug(effectiveShadowBias(normalView, shadowLightPosition)));
        }
#endif
    }
    color = vec4(debugColor, 1.0);
#endif
}
