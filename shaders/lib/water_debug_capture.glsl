#ifndef AURORA_WATER_DEBUG_CAPTURE_INCLUDED
#define AURORA_WATER_DEBUG_CAPTURE_INCLUDED
#if DEBUG_VIEW == 7 || DEBUG_VIEW == 8 || DEBUG_VIEW == 9
#define AURORA_WATER_DEBUG_CAPTURE
#include "/lib/water_filtered_waves.glsl"
// Debug-only full-resolution data. RGB is a signed unit VIEW normal; A is raw
// water window depth, not coverage. A zero normal is the explicit invalid clear.
/*
const int colortex7Format = RGBA32F;
*/
const bool colortex7Clear = true;
const vec4 colortex7ClearColor = vec4(0.0);

vec4 captureWaterDebugSurface(vec3 viewPosition, vec3 normalView, vec2 worldDx,
                              vec2 worldDy, int waterSurface, float windowDepth) {
    if (waterSurface != 1 || isnan(windowDepth) || isinf(windowDepth)
        || windowDepth < 0.0 || windowDepth >= 1.0) return vec4(0.0);
    if (any(isnan(viewPosition)) || any(isinf(viewPosition))
        || any(isnan(normalView)) || any(isinf(normalView))
        || any(isnan(upPosition)) || any(isinf(upPosition))) return vec4(0.0);
    float normalScale = max(max(abs(normalView.x), abs(normalView.y)), abs(normalView.z));
    float upScale = max(max(abs(upPosition.x), abs(upPosition.y)), abs(upPosition.z));
    if (normalScale <= 1e-6 || upScale <= 1e-6) return vec4(0.0);
    vec3 normal = celestialUnit(normalView);
    // Classification includes all water faces. Only the same top-face eligibility
    // as the real reflection path permits animated wave-normal perturbation.
    float upwardSurface = smoothstep(0.5, 0.95, dot(normal, celestialUnit(upPosition)));
    normal = waterFilteredWaveNormal(normal, viewPosition, upwardSurface, worldDx, worldDy);
    if (any(isnan(normal)) || any(isinf(normal))) return vec4(0.0);
    return vec4(normal, windowDepth);
}
#endif
#endif
