#ifndef AURORA_WATER_INCLUDED
#define AURORA_WATER_INCLUDED
#include "/lib/water_settings.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/sky_palette.glsl"

float waterFresnel(float normalDotView) {
    // Schlick's angle dependence with a fixed water-like F0; not full transmission.
    float grazing = 1.0 - clamp(normalDotView, 0.0, 1.0);
    float squared = grazing * grazing;
    return 0.02 + 0.98 * squared * squared * grazing;
}
vec3 applyWaterStyle(vec3 scene, vec3 viewPosition, vec3 normalView, vec2 lightmapUV,
                     int waterSurface, ivec4 blendState, vec3 vanillaFog) {
#if WATER_STYLE == 0 || SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return scene;
#else
    // gbuffers_water also draws glass and other translucent blocks. Only an
    // explicitly assigned water ID AND fluid marker may enter this effect.
    if (waterSurface != 1) return scene;
    if (WATER_TINT_STRENGTH <= 0.0 && WATER_REFLECTION_STRENGTH <= 0.0) return scene;
    bool supportedBlend = all(equal(blendState, ivec4(0)))
                       || (blendState.x == 770 && blendState.y == 771)
                       || (blendState.x == 1 && blendState.y == 0);
    if (!supportedBlend) return scene;
    float environment = celestialEnvironmentWeight();
    if (isnan(environment) || isinf(environment) || environment <= 0.0) return scene;
    if (isnan(rainStrength) || isinf(rainStrength)) return scene;
    if (any(isnan(lightmapUV)) || any(isinf(lightmapUV))) return scene;
    // Same lightmap cell-center convention as the existing G-buffer writer.
    vec2 levels = clamp((lightmapUV - vec2(0.5 / 16.0)) * (16.0 / 15.0), 0.0, 1.0);
    float skyAccess = levels.y;
    if (skyAccess <= 0.0) return scene;
    float tintWeight = clamp(WATER_TINT_STRENGTH, 0.0, 1.0)
                     * environment * skyAccess * (1.0 - levels.x);
    vec3 tinted = scene;
    if (tintWeight > 0.0) tinted = scene * mix(vec3(1.0), vec3(0.80, 1.03, 1.08), tintWeight);
#if SKY_STYLE == 0
    return tinted;
#else
    float reflectionWeight = clamp(WATER_REFLECTION_STRENGTH, 0.0, 1.0)
                           * environment * skyAccess * clamp(SKY_BLEND, 0.0, 1.0);
    if (reflectionWeight <= 0.0) return tinted;
    if (any(isnan(normalView)) || any(isinf(normalView))
        || any(isnan(viewPosition)) || any(isinf(viewPosition))) return tinted;
    float normalScale = max(max(abs(normalView.x), abs(normalView.y)), abs(normalView.z));
    float viewScale = max(max(abs(viewPosition.x), abs(viewPosition.y)), abs(viewPosition.z));
    if (normalScale <= 1e-6 || viewScale <= 1e-6) return tinted;
    vec3 normal = celestialUnit(normalView);
    vec3 towardEye = celestialUnit(-viewPosition);
    vec3 reflected = reflect(-towardEye, normal);
    vec3 up = celestialUnit(upPosition);
    float upwardSurface = smoothstep(0.5, 0.95, dot(normal, up));
    // Preserve the strong grazing reflection at the horizon; fade only just below it.
    float aboveHorizon = smoothstep(-0.10, 0.0, dot(reflected, up));
    reflectionWeight *= upwardSurface * aboveHorizon * waterFresnel(dot(normal, towardEye));
    if (reflectionWeight <= 0.0) return tinted;
    // Analytic M7 sky color only: no scene textures, clouds, discs, aurora or SSR.
    vec3 reflectedSky = auroraSkyLinear(reflected, vanillaFog);
    // Native alpha subsequently attenuates this whole source, including reflection.
    // Never divide by alpha; this is an artistic source blend, not physical water.
    return mix(tinted, reflectedSky, clamp(reflectionWeight, 0.0, 1.0));
#endif
#endif
}
#endif
