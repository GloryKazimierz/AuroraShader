#ifndef AURORA_SKY_PALETTE_INCLUDED
#define AURORA_SKY_PALETTE_INCLUDED
#include "/lib/atmosphere_settings.glsl"
#include "/lib/scene_color.glsl"
#include "/lib/celestial.glsl"

vec3 auroraSkyLinear(vec3 rayView, vec3 vanillaFog) {
    vec3 phases = vec3(celestialPhases(), clamp(rainStrength, 0.0, 1.0));
    float height = clamp(dot(celestialUnit(rayView), celestialUnit(upPosition)), 0.0, 1.0);
    float horizon = pow(1.0 - height, 3.0);
    float towardSun = max(dot(celestialUnit(rayView), celestialUnit(sunPosition)), 0.0);
    vec3 night = mix(srgbToLinear(vec3(0.035, 0.045, 0.12)),
                     srgbToLinear(vec3(0.12, 0.16, 0.30)), horizon) * NIGHT_BRIGHTNESS;
    vec3 day = mix(srgbToLinear(vec3(0.12, 0.38, 0.82)),
                   srgbToLinear(vec3(0.53, 0.75, 0.95)), horizon);
    vec3 twilight = mix(srgbToLinear(vec3(0.17, 0.09, 0.35)),
                        srgbToLinear(vec3(0.68, 0.30, 0.48)), horizon);
    // Localize coral/gold near the actual solar direction, without replacing its disc.
    float warmth = clamp(horizon * pow(towardSun, 4.0) * SUNSET_GLOW, 0.0, 1.0);
    twilight = mix(twilight, srgbToLinear(vec3(1.0, 0.56, 0.18)), warmth);
    vec3 sky = mix(mix(night, day, phases.x), twilight, phases.y);
    vec3 fogLinear = srgbToLinear(clamp(vanillaFog, 0.0, 1.0));
    // Modest biome-colored horizon connection; NOT terrain/distance fog.
    sky = mix(sky, fogLinear, 0.22 * horizon * horizon);
    // Rain approaches a muted vanilla-weather palette continuously.
    vec3 overcast = fogLinear * mix(0.4, 1.0, phases.x);
    return clamp(mix(sky, overcast, 0.85 * phases.z), 0.0, 1.0);
}
vec3 applyAuroraSky(vec3 rayView, vec3 baseline, vec3 vanillaFog) {
#if SKY_STYLE == 0
    return sceneFromDisplay(baseline);
#else
    float weight = clamp(SKY_BLEND, 0.0, 1.0) * celestialEnvironmentWeight();
    if (weight <= 0.0) return sceneFromDisplay(baseline); // Exact disabled/fluid/dimension bypass.
    vec3 linearSky = mix(srgbToLinear(baseline), auroraSkyLinear(rayView, vanillaFog), weight);
    return sceneFromLinear(linearSky);
#endif
}
#endif
