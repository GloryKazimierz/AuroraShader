// Receiver-side normalized-depth tolerance; NOT rasterizer slope-scaled bias.
// shadow_settings.glsl is included by shadow.glsl before this file.
vec2 shadowBiasBounds() {
    // Treat reversed user bounds as the same interval, and keep it nonnegative.
    return clamp(vec2(min(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX),
                      max(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX)), 0.0, 0.002);
}
float shadowBiasNdotL(vec3 normalView, vec3 lightDirectionView) {
    // BOTH vectors are VIEW-space. Invalid/near-zero directions use max bias.
    if (any(isnan(normalView)) || any(isinf(normalView)) ||
        any(isnan(lightDirectionView)) || any(isinf(lightDirectionView))) return 0.0;
    float normalScale = max(max(abs(normalView.x), abs(normalView.y)), abs(normalView.z));
    float lightScale = max(max(abs(lightDirectionView.x), abs(lightDirectionView.y)), abs(lightDirectionView.z));
    if (normalScale <= 1e-6 || lightScale <= 1e-6) return 0.0;
    // Scaling before normalization avoids length overflow for large finite inputs.
    vec3 normalUnit = normalize(normalView / normalScale);
    vec3 lightUnit = normalize(lightDirectionView / lightScale);
    return clamp(dot(normalUnit, lightUnit), 0.0, 1.0);
}
float effectiveShadowBias(vec3 normalView, vec3 lightDirectionView) {
#if SHADOW_BIAS_MODE == 0
    // Exact M3A-M5 comparison tolerance; independent of angle and new bounds.
    return SHADOW_BIAS;
#else
    vec2 bounds = shadowBiasBounds();
    float angleFactor = 1.0 - shadowBiasNdotL(normalView, lightDirectionView);
    return clamp(mix(bounds.x, bounds.y, angleFactor), bounds.x, bounds.y);
#endif
}
float shadowBiasDebug(float effectiveBias) {
    // Prospective receiver bias even with shadows off or outside map coverage.
    vec2 bounds = shadowBiasBounds();
    float span = bounds.y - bounds.x;
    if (span <= 1e-8) return 0.0; // Equal bounds are black; never divide by zero.
    return clamp((effectiveBias - bounds.x) / span, 0.0, 1.0);
}
