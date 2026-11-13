#ifndef AURORA_CLOUDS_INCLUDED
#define AURORA_CLOUDS_INCLUDED
#include "/lib/cloud_settings.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/fog.glsl"

vec3 cloudColorTint() {
    vec2 phases = celestialPhases();
    vec3 night = vec3(0.55, 0.65, 1.05);
    vec3 day = vec3(1.02, 1.0, 0.96);
    vec3 twilight = vec3(1.15, 0.72, 0.50);
    vec3 tint = mix(mix(night, day, phases.x), twilight, phases.y);
    // The native cloud source already includes weather shading; only mute our hue.
    return mix(tint, vec3(1.0), 0.8 * clamp(rainStrength, 0.0, 1.0));
}
vec3 applyCloudAtmosphere(vec3 scene) {
#if CLOUD_STYLE == 0 || SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return scene;
#else
    // Iris uses all-zero blendFunc when blending is DISABLED. Treat it as opaque
    // only here, on the verified cloud draw path; do not change M9's generic rules.
    bool supportedBlend = all(equal(blendFunc, ivec4(0)))
                       || (blendFunc.x == 770 && blendFunc.y == 771)
                       || (blendFunc.x == 1 && blendFunc.y == 0);
    if (!supportedBlend) return scene;
    float environment = celestialEnvironmentWeight();
    if (isnan(environment) || isinf(environment) || environment <= 0.0) return scene;
    if (isnan(rainStrength) || isinf(rainStrength)) return scene;
    float weight = clamp(CLOUD_COLOR_STRENGTH, 0.0, 1.0) * environment;
    vec3 tinted = scene;
    if (weight > 0.0) tinted = scene * mix(vec3(1.0), cloudColorTint(), weight);
#if CLOUD_FOG == 0 || FOG_ENABLED == 0
    return tinted;
#else
    // Clouds are late geometry. Fog this source using its own depth, before native
    // blending, so the already fogged background is neither replaced nor fogged again.
    vec2 uv = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 viewPosition = reconstructViewPosition(uv, gl_FragCoord.z);
    return applyAtmosphericFog(tinted, viewPosition);
#endif
#endif
}
#endif
