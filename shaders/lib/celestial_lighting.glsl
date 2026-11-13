#include "/lib/atmosphere_settings.glsl"
#include "/lib/color_space.glsl"
#include "/lib/celestial.glsl"

vec3 applyCelestialPalette(vec3 litScene, vec3 normalView, vec2 lightLevels, float visibility) {
#if LIGHT_PALETTE == 0
    return litScene;
#else
    float skyWeight = clamp(lightLevels.y, 0.0, 1.0) * (1.0 - clamp(lightLevels.x, 0.0, 1.0));
    float weight = clamp(LIGHT_PALETTE_STRENGTH * LIGHTING_STRENGTH * skyWeight, 0.0, 1.0)
                 * celestialEnvironmentWeight();
    if (weight <= 0.0) return litScene; // Caves, full block light and disabled lighting.
    vec2 phases = celestialPhases();
    // Linear RGB channel multipliers, not sRGB palette swatches or physical radiance.
    vec3 ambient = mix(vec3(0.56, 0.68, 1.0), vec3(0.78, 0.88, 1.0), phases.x);
    ambient = mix(ambient, vec3(0.76, 0.65, 0.95), phases.y);
    vec3 direct = mix(vec3(0.58, 0.78, 1.0), vec3(1.0, 0.94, 0.82), phases.x);
    direct = mix(direct, vec3(1.0, 0.66, 0.38), phases.y);
    float rain = 0.75 * clamp(rainStrength, 0.0, 1.0);
    ambient = mix(ambient, vec3(0.86, 0.90, 0.96), rain);
    direct = mix(direct, vec3(0.94, 0.95, 0.98), rain);
    // Shadow visibility removes only the direct COLOR contribution; ambient remains.
    float directAmount = DIRECT_LIGHT * diffuseTerm(normalView) * visibility;
    float total = max(AMBIENT_LIGHT + directAmount, 1e-6);
    vec3 tint = (AMBIENT_LIGHT * ambient + directAmount * direct) / total;
    // The original M6 scalar/lightmap result is retained, then tinted locally in linear space.
    // This is an artistic bridge, NOT independent albedo relighting or an HDR conversion.
    return linearToSrgb(srgbToLinear(litScene) * mix(vec3(1.0), tint, weight));
#endif
}
