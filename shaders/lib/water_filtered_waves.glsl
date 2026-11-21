#ifndef AURORA_WATER_FILTERED_WAVES_INCLUDED
#define AURORA_WATER_FILTERED_WAVES_INCLUDED
#include "/lib/water_surface_settings.glsl"
#include "/lib/water_waves.glsl"

bool waterWaveFootprintValid(vec2 worldDx, vec2 worldDy) {
    // These are continuous world-XZ differences in blocks per screen pixel,
    // never derivatives of the wrapped phase or absolute float world position.
    // Extreme/invalid reconstruction safely removes procedural detail.
    return !any(isnan(worldDx)) && !any(isinf(worldDx))
        && !any(isnan(worldDy)) && !any(isinf(worldDy))
        && !any(greaterThan(abs(worldDx), vec2(65536.0)))
        && !any(greaterThan(abs(worldDy), vec2(65536.0)));
}
float waterWaveSinc(float x) {
    // Only called for |x| < pi/2 after finite checks. This even degree-10
    // polynomial avoids driver sin(x)/x precision loss near zero. The alternating
    // series remainder is at most (pi/2)^12 / 13! < 3.63e-8 before FP32 rounding.
    float squared = x * x;
    return 1.0 + squared * (-1.0 / 6.0 + squared * (1.0 / 120.0
         + squared * (-1.0 / 5040.0 + squared * (1.0 / 362880.0
         - squared / 39916800.0))));
}
float waterWavePixelFilter(vec2 waveVector, vec2 worldDx, vec2 worldDy) {
    if (!waterWaveFootprintValid(worldDx, worldDy)
        || any(isnan(waveVector)) || any(isinf(waveVector))) return 0.0;
    // Project each periodic wave onto the two screen-pixel axes, in cycles/pixel.
    vec2 cycles = vec2(dot(waveVector, worldDx), dot(waveVector, worldDy)) / 128.0;
    if (any(isnan(cycles)) || any(isinf(cycles))) return 0.0;
    float frequency = max(abs(cycles.x), abs(cycles.y));
    // Reject before sin: extreme footprints never create large trig arguments.
    if (frequency >= 0.5) return 0.0;
    // Exact box average for an affine pixel footprint, followed by a deliberate
    // fade toward Nyquist. This is not exact integration over a perspective pixel.
    // In this admitted band, sinc is nonnegative and bounded above by exp(-x*x/6).
    vec2 angles = 3.14159265359 * cycles;
    float boxAverage = waterWaveSinc(angles.x) * waterWaveSinc(angles.y);
    return boxAverage * (1.0 - smoothstep(0.25, 0.5, frequency));
}
vec2 waterFilteredWaveGradient(vec2 tile, vec2 worldDx, vec2 worldDy) {
    if (!waterWaveFootprintValid(worldDx, worldDy)
        || any(isnan(tile)) || any(isinf(tile))) return vec2(0.0);
    // The first three modes retain M14's conceptual height spectrum. The smaller
    // modes add surface detail, not vertex displacement or a simulated current.
#include "/lib/water_wave_spectrum.glsl"
    float cycle = waterWaveCycle();
    vec2 gradient = vec2(0.0);
    for (int wave = 0; wave < 6; ++wave) {
        float pixelWeight = waterWavePixelFilter(directions[wave], worldDx, worldDy);
        if (pixelWeight <= 0.0) continue;
        // Integer directions/harmonics keep the same 128-block and 200-second
        // periods, including negative/large camera anchors and Iris's time reset.
        float angle = 6.28318530718 * fract(dot(directions[wave], tile) + harmonics[wave] * cycle);
        gradient += amplitudes[wave] * (6.28318530718 / 128.0) * directions[wave]
                  * cos(angle) * pixelWeight;
    }
    return gradient;
}
vec3 waterFilteredWaveNormal(vec3 baseNormal, vec3 viewPosition, float surfaceEligibility,
                             vec2 worldDx, vec2 worldDy) {
#if WATER_SURFACE_DETAIL == 0
    return waterWaveNormal(baseNormal, viewPosition, surfaceEligibility);
#elif WATER_WAVES == 0
    return baseNormal;
#else
    if (isnan(surfaceEligibility) || isinf(surfaceEligibility)) return baseNormal;
    float strength = clamp(WATER_WAVE_STRENGTH, 0.0, 1.0) * clamp(surfaceEligibility, 0.0, 1.0);
    if (strength <= 0.0 || !waterWaveFootprintValid(worldDx, worldDy)) return baseNormal;
    vec3 playerPosition = viewToPlayerPosition(viewPosition);
    if (any(isnan(playerPosition)) || any(isinf(playerPosition))
        || any(isnan(cameraPositionFract.xz)) || any(isinf(cameraPositionFract.xz))) return baseNormal;
    // Keep the integer camera anchor separate; float absolute coordinates would
    // lose small-wave phase far from the world origin. Never differentiate tile.
    vec2 anchor = vec2(uvec2(cameraPositionInt.xz) & uvec2(127u));
    vec2 tile = fract((anchor + cameraPositionFract.xz + playerPosition.xz) / 128.0);
    vec2 slope = waterFilteredWaveGradient(tile, worldDx, worldDy) * strength;
    if (all(equal(slope, vec2(0.0)))) return baseNormal;
    // Retain M14's normal-space convention and original face eligibility. Wave
    // filtering changes only the reflection normal, not silhouettes or coverage.
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
