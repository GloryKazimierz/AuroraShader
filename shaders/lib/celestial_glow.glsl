#ifndef AURORA_CELESTIAL_GLOW_INCLUDED
#define AURORA_CELESTIAL_GLOW_INCLUDED
#include "/lib/celestial_glow_settings.glsl"
#include "/lib/atmosphere_settings.glsl"
#include "/lib/pipeline_settings.glsl"
#ifndef DEBUG_VIEW
#include "/lib/lighting_settings.glsl"
#endif
#include "/lib/celestial.glsl"

uniform vec3 moonPosition;
uniform int moonPhase;

bool glowUnitDirection(vec3 direction, out vec3 unitDirection) {
    unitDirection = vec3(0.0);
    if (any(isnan(direction)) || any(isinf(direction))) return false;
    float scale = max(max(abs(direction.x), abs(direction.y)), abs(direction.z));
    if (scale <= 1e-6) return false;
    // Scale before normalization to avoid overflow for finite large vectors.
    unitDirection = normalize(direction / scale);
    return true;
}

float glowAngularLobe(float alignment) {
    if (isnan(alignment) || isinf(alignment)) return 0.0;
    float distance = 1.0 - clamp(alignment, -1.0, 1.0);
    // Two positive angular falloffs: bounded by one, without acos or screen projection.
    return 0.75 * exp(-distance / 0.012) + 0.25 * exp(-distance / 0.08);
}

float glowMoonPhaseBrightness(int phase) {
    if (phase < 0 || phase > 7) return 0.0;
    int folded = min(phase, 8 - phase);
    // Artistic cosine-derived brightness, not vanilla light levels or disc geometry.
    // Exact full/new values and folded pairs avoid trigonometric rounding asymmetry.
    if (folded == 0) return 1.0;
    if (folded == 1) return 0.85355339059;
    if (folded == 2) return 0.5;
    if (folded == 3) return 0.14644660941;
    return 0.0;
}

float glowBodyLobe(vec3 rayUnit, vec3 upUnit, vec3 bodyPosition) {
    vec3 bodyUnit;
    // An invalid celestial vector disables only that body, never invents a zenith glow.
    if (!glowUnitDirection(bodyPosition, bodyUnit)) return 0.0;
    float visibility = smoothstep(-0.08, 0.04, dot(bodyUnit, upUnit));
    if (visibility <= 0.0) return 0.0;
    return visibility * glowAngularLobe(dot(rayUnit, bodyUnit));
}

vec3 applyCelestialGlow(vec3 rayView, vec3 scene) {
#if CELESTIAL_GLOW == 0 || SCENE_COLOR_MODE == 0 || SKY_STYLE == 0 || DEBUG_VIEW != 0
    return scene;
#else
    float sunStrength = clamp(SUN_GLOW_STRENGTH, 0.0, 1.0);
    float moonStrength = clamp(MOON_GLOW_STRENGTH, 0.0, 0.5);
    if (sunStrength <= 0.0 && moonStrength <= 0.0) return scene;
    if (isnan(sunStrength) || isinf(sunStrength) || isnan(moonStrength) || isinf(moonStrength)
        || isnan(SKY_BLEND) || isinf(SKY_BLEND)
        || isnan(rainStrength) || isinf(rainStrength)
        || isnan(blindness) || isinf(blindness)
        || isnan(darknessFactor) || isinf(darknessFactor)) return scene;
    // Do not repair or reinterpret an invalid source; all bypasses preserve it.
    if (any(isnan(scene)) || any(isinf(scene)) || any(lessThan(scene, vec3(0.0)))) return scene;
    vec3 rayUnit;
    vec3 upUnit;
    if (!glowUnitDirection(rayView, rayUnit) || !glowUnitDirection(upPosition, upUnit)) return scene;
    float dry = 1.0 - clamp(rainStrength, 0.0, 1.0);
    float weight = clamp(SKY_BLEND, 0.0, 1.0) * celestialEnvironmentWeight() * dry * dry
                 * smoothstep(-0.025, 0.04, dot(rayUnit, upUnit));
    if (isnan(weight) || isinf(weight) || weight <= 0.0) return scene;

    // Use each actual position independently; shadowLightPosition switches bodies.
    // A valid moon remains independent of sun direction, including in modded skies.
    float sun = sunStrength * glowBodyLobe(rayUnit, upUnit, sunPosition);
    float moon = moonStrength * glowMoonPhaseBrightness(moonPhase)
               * glowBodyLobe(rayUnit, upUnit, moonPosition);
    vec3 added = weight * (sun * vec3(1.0, 0.62, 0.28) + moon * vec3(0.24, 0.38, 1.0));
    if (any(isnan(added)) || any(isinf(added)) || any(lessThan(added, vec3(0.0)))) return scene;
    if (max(max(added.x, added.y), added.z) <= 0.0) return scene;
    // Added light is at most 1.5 per component. Keep the RGBA16F scene finite.
    vec3 result = scene + added;
    if (any(isnan(result)) || any(isinf(result)) || any(lessThan(result, vec3(0.0)))
        || max(max(result.x, result.y), result.z) > 65504.0) return scene;
    return result;
#endif
}
#endif
