#ifndef AURORA_BLOOM_INCLUDED
#define AURORA_BLOOM_INCLUDED
#include "/lib/bloom_settings.glsl"
#include "/lib/pipeline_settings.glsl"
#include "/lib/lighting_settings.glsl"

// Storage protection for the new RGBA16F path, not an artistic display clamp.
float bloomSafeComponent(float value) {
    return isnan(value) ? 0.0 : clamp(value, 0.0, 65504.0);
}
vec3 bloomSafe(vec3 value) {
    return vec3(bloomSafeComponent(value.r), bloomSafeComponent(value.g), bloomSafeComponent(value.b));
}
bool bloomActive() {
#if BLOOM_ENABLED == 0 || SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return false;
#else
    return BLOOM_STRENGTH > 0.0;
#endif
}
vec3 extractBloom(vec3 scene) {
    vec3 rgb = bloomSafe(scene);
    float peak = max(rgb.r, max(rgb.g, rgb.b));
    float threshold = max(BLOOM_THRESHOLD, 0.0);
    float knee = threshold * clamp(BLOOM_SOFT_KNEE, 0.0, 1.0);
    float soft = 0.0;
    if (knee > 0.0) {
        float ramp = clamp(peak - threshold + knee, 0.0, 2.0 * knee);
        soft = ramp * ramp / (4.0 * knee);
    }
    // One scale preserves positive linear RGB ratios; zero is safe and stays black.
    float contribution = max(max(peak - threshold, 0.0), soft);
    return bloomSafe(rgb * (contribution / max(peak, 0.000001)));
}
vec3 bloomFetch(sampler2D source, ivec2 pixel) {
    ivec2 extent = textureSize(source, 0);
    return bloomSafe(texelFetch(source, clamp(pixel, ivec2(0), extent - 1), 0).rgb);
}
vec3 blurBloom(sampler2D source, ivec2 pixel, ivec2 axis) {
    // Separable 9-tap binomial approximation. Weights sum to one.
    const float weights[9] = float[9](1.0, 8.0, 28.0, 56.0, 70.0, 56.0, 28.0, 8.0, 1.0);
    vec3 sum = vec3(0.0);
    for (int tap = 0; tap < 9; ++tap) {
        sum += bloomFetch(source, pixel + (tap - 4) * axis) * (weights[tap] / 256.0);
    }
    return bloomSafe(sum);
}
vec3 upsampleBloom(sampler2D source, vec2 uv) {
    // Explicit bilinear reconstruction, independent of the texture's sampler filter.
    vec2 position = uv * vec2(textureSize(source, 0)) - 0.5;
    ivec2 base = ivec2(floor(position));
    vec2 weight = fract(position);
    vec3 lower = mix(bloomFetch(source, base), bloomFetch(source, base + ivec2(1, 0)), weight.x);
    vec3 upper = mix(bloomFetch(source, base + ivec2(0, 1)), bloomFetch(source, base + ivec2(1, 1)), weight.x);
    return bloomSafe(mix(lower, upper, weight.y));
}
#endif
