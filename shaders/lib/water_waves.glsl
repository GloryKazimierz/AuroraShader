#ifndef AURORA_WATER_WAVES_INCLUDED
#define AURORA_WATER_WAVES_INCLUDED
#include "/lib/water_wave_settings.glsl"
#include "/lib/camera_anchor.glsl"
#include "/lib/position.glsl"
#include "/lib/celestial.glsl"
uniform float frameTimeCounter;

float waterWaveCycle() {
    float seconds = frameTimeCounter;
    if (isnan(seconds) || isinf(seconds)) seconds = 0.0;
    // Integer harmonics repeat every 200s at normal speed and across Iris's 3600s reset.
    return fract(max(seconds, 0.0) * (float(WATER_WAVE_SPEED) / 200.0));
}
vec2 waterWaveGradient(vec2 tile) {
    const vec2 directions[3] = vec2[3](vec2(11.0, 3.0), vec2(4.0, -9.0), vec2(7.0, 13.0));
    const float amplitudes[3] = float[3](0.06, 0.04, 0.03);
    const float harmonics[3] = float[3](10.0, -13.0, 7.0);
    float cycle = waterWaveCycle();
    vec2 gradient = vec2(0.0);
    for (int wave = 0; wave < 3; ++wave) {
        float angle = 6.28318530718 * fract(dot(directions[wave], tile) + harmonics[wave] * cycle);
        // Analytic derivative of a conceptual sine height field, per world block.
        // Height is never applied to vertices: only the reflection normal changes.
        gradient += amplitudes[wave] * (6.28318530718 / 128.0) * directions[wave] * cos(angle);
    }
    return gradient;
}
vec3 waterWaveNormal(vec3 baseNormal, vec3 viewPosition, float surfaceEligibility) {
#if WATER_WAVES == 0
    return baseNormal;
#else
    float strength = clamp(WATER_WAVE_STRENGTH, 0.0, 1.0) * clamp(surfaceEligibility, 0.0, 1.0);
    if (strength <= 0.0) return baseNormal;
    vec3 playerPosition = viewToPlayerPosition(viewPosition);
    if (any(isnan(playerPosition)) || any(isinf(playerPosition))
        || any(isnan(cameraPositionFract.xz)) || any(isinf(cameraPositionFract.xz))) return baseNormal;
    // Unsigned low bits wrap negative anchors safely; signed negative % is not portable GLSL.
    vec2 anchor = vec2(uvec2(cameraPositionInt.xz) & uvec2(127u));
    vec2 tile = fract((anchor + cameraPositionFract.xz + playerPosition.xz) / 128.0);
    vec2 slope = waterWaveGradient(tile) * strength;
    // Normal covectors use inverse-transpose. The up-length restores the scale
    // discarded by baseNormal normalization on horizontal world-space water.
    mat3 normalToView = transpose(mat3(gbufferModelViewInverse));
    vec3 upView = normalToView * vec3(0.0, 1.0, 0.0);
    vec3 slopeView = normalToView * vec3(slope.x, 0.0, slope.y);
    if (any(isnan(upView)) || any(isinf(upView))
        || any(isnan(slopeView)) || any(isinf(slopeView))) return baseNormal;
    float upLength = length(upView);
    if (isnan(upLength) || isinf(upLength) || upLength <= 1e-6) return baseNormal;
    vec3 perturbed = baseNormal - slopeView / upLength;
    if (any(isnan(perturbed)) || any(isinf(perturbed))) return baseNormal;
    float scale = max(max(abs(perturbed.x), abs(perturbed.y)), abs(perturbed.z));
    if (scale <= 1e-6) return baseNormal;
    return celestialUnit(perturbed);
#endif
}
#endif
