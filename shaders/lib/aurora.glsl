#ifndef AURORA_NIGHT_INCLUDED
#define AURORA_NIGHT_INCLUDED
#include "/lib/aurora_settings.glsl"
#include "/lib/atmosphere_settings.glsl"
#include "/lib/pipeline_settings.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/celestial.glsl"

uniform mat4 gbufferModelViewInverse;
uniform float frameTimeCounter;

float auroraTemporalPhase() {
    float seconds = frameTimeCounter;
    if (isnan(seconds) || isinf(seconds)) seconds = 0.0;
    // All waves use integer harmonics. 200 seconds divides Iris's 3600s reset;
    // supported integer speeds keep both loop boundaries visually continuous.
    return 6.28318530718 * fract(max(seconds, 0.0) * (float(AURORA_SPEED) / 200.0));
}
vec3 auroraRibbonLight(vec3 worldDirection) {
    // A bounded direction-plane projection avoids an atan seam and horizon pole.
    // These are distant artistic ribbons: no position/parallax or physical volume.
    vec2 uv = worldDirection.xz / (max(worldDirection.y, 0.0) + 0.18);
    float phase = auroraTemporalPhase();
    vec3 light = vec3(0.0);
    for (int ribbon = 0; ribbon < 3; ++ribbon) {
        float index = float(ribbon);
        float center = -0.8 - 0.55 * index
                     + 0.18 * sin(1.6 * uv.x + phase + 2.0 * index)
                     + 0.09 * sin(3.1 * uv.x - 2.0 * phase + index);
        float distance = uv.y - center;
        float coreDistance = distance / 0.10;
        float tailDistance = (distance - 0.22) / 0.30;
        // Signed distance is squared explicitly: GLSL pow has no negative-base guarantee.
        float core = exp(-coreDistance * coreDistance);
        float tail = exp(-tailDistance * tailDistance);
        float fold = 0.5 + 0.5 * sin(11.0 * uv.x + sin(2.3 * uv.x - 2.0 * phase)
                                   + 3.0 * phase + 2.0 * index);
        float striation = 0.35 + 0.65 * fold * fold;
        // Linear HDR teal cores and softer violet trails toward the upper sky.
        light += striation * (vec3(0.08, 1.35, 0.75) * core
                            + vec3(0.25, 0.05, 0.55) * (0.45 * tail));
    }
    return clamp(light, 0.0, 2.0);
}
vec3 applyNightAurora(vec3 rayView, vec3 scene) {
#if AURORA_ENABLED == 0 || SCENE_COLOR_MODE == 0 || SKY_STYLE == 0 || DEBUG_VIEW != 0
    return scene;
#else
    float weight = clamp(AURORA_INTENSITY, 0.0, 1.0)
                 * clamp(SKY_BLEND, 0.0, 1.0) * celestialEnvironmentWeight();
    float elevation = clamp(dot(celestialUnit(sunPosition), celestialUnit(upPosition)), -1.0, 1.0);
    float night = 1.0 - smoothstep(-0.20, -0.05, elevation);
    float dry = 1.0 - clamp(rainStrength, 0.0, 1.0);
    weight *= night * dry * dry;
    if (isnan(weight) || isinf(weight) || weight <= 0.0) return scene;
    if (any(isnan(rayView)) || any(isinf(rayView))) return scene;
    float scale = max(max(abs(rayView.x), abs(rayView.y)), abs(rayView.z));
    if (scale <= 1e-6) return scene;
    // Rotate the direction only. Camera translation must not move this distant sky.
    vec3 worldDirection = mat3(gbufferModelViewInverse) * celestialUnit(rayView);
    if (any(isnan(worldDirection)) || any(isinf(worldDirection))) return scene;
    worldDirection = celestialUnit(worldDirection);
    float height = worldDirection.y;
    float vertical = smoothstep(0.04, 0.18, height) * (1.0 - smoothstep(0.82, 0.98, height));
    float north = smoothstep(0.0, 0.45, -worldDirection.z);
    weight *= vertical * north;
    if (weight <= 0.0) return scene;
    return scene + auroraRibbonLight(worldDirection) * weight;
#endif
}
#endif
