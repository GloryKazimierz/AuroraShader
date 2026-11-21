#ifndef AURORA_WATER_DEBUG_VIEW_INCLUDED
#define AURORA_WATER_DEBUG_VIEW_INCLUDED
#if DEBUG_VIEW == 7 || DEBUG_VIEW == 8 || DEBUG_VIEW == 9
#include "/lib/water_params.glsl"
#include "/lib/position.glsl"

vec3 waterDebugColor(vec4 surface, float finalDepth, float backgroundDepth, vec2 pixelCenterUV) {
    // One D24 quantization unit tolerates the raw gl_FragCoord.z -> stored depth
    // conversion. It cannot distinguish coplanar surfaces or depthless overlays.
    const float ownershipTolerance = 1.0 / 16777215.0;
    if (any(isnan(surface)) || any(isinf(surface)) || isnan(finalDepth) || isinf(finalDepth)
        || surface.a < 0.0 || surface.a >= 1.0 || finalDepth < 0.0 || finalDepth >= 1.0
        || abs(surface.a - finalDepth) > ownershipTolerance) return vec3(0.0);
    float normalLengthSquared = dot(surface.rgb, surface.rgb);
    if (isnan(normalLengthSquared) || isinf(normalLengthSquared)
        || abs(normalLengthSquared - 1.0) > 0.001) return vec3(0.0);
#if DEBUG_VIEW == 7
    return vec3(1.0);
#elif DEBUG_VIEW == 8
    // Signed view axes: +X red, +Y green, +Z blue. No tone map/display conversion.
    return surface.rgb * 0.5 + 0.5;
#else
    // Magenta distinguishes a valid water source with no usable background gap
    // from black pixels that have no accepted front-water metadata.
    const vec3 invalidGap = vec3(1.0, 0.0, 1.0);
    if (isnan(backgroundDepth) || isinf(backgroundDepth) || backgroundDepth <= surface.a
        || backgroundDepth >= 1.0 || any(isnan(pixelCenterUV)) || any(isinf(pixelCenterUV))
        || any(lessThan(pixelCenterUV, vec2(0.0))) || any(greaterThanEqual(pixelCenterUV, vec2(1.0)))) return invalidGap;
    vec3 waterView = reconstructViewPosition(pixelCenterUV, surface.a);
    vec3 backgroundView = reconstructViewPosition(pixelCenterUV, backgroundDepth);
    if (any(isnan(waterView)) || any(isinf(waterView))
        || any(isnan(backgroundView)) || any(isinf(backgroundView))) return invalidGap;
    vec3 worldDelta = mat3(gbufferModelViewInverse) * (backgroundView - waterView);
    if (any(isnan(worldDelta)) || any(isinf(worldDelta))) return invalidGap;
    float scale = max(max(abs(worldDelta.x), abs(worldDelta.y)), abs(worldDelta.z));
    if (scale <= 0.0) return invalidGap;
    WaterParams params = waterParams();
    float gapMeters = scale * length(worldDelta / scale) * params.worldBlockMeters;
    if (isnan(gapMeters) || isinf(gapMeters) || gapMeters <= 0.0) return invalidGap;
    // Same-pixel reconstructed ray separation, NOT a measured water-volume exit
    // distance. The 0..16m display range is an artistic inspection calibration.
    return vec3(clamp(gapMeters / params.debugGapRangeMeters, 0.0, 1.0));
#endif
}
#endif
#endif
