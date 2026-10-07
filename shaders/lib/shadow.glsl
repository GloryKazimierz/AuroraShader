#include "/lib/shadow_settings.glsl"
#include "/lib/position.glsl"
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform sampler2D shadowtex1; // Opaque/cutout caster depth, no translucency.
uniform sampler2D depthtex1;  // Camera depth snapshot before translucency.

float compareShadow(vec2 shadowUV, float receiverDepth, ivec2 mapSize) {
    // Preserve the map-boundary policy for every tap: outside the map is lit.
    if (any(lessThan(shadowUV, vec2(0.0))) ||
        any(greaterThanEqual(shadowUV, vec2(1.0)))) return 1.0;
    ivec2 shadowPixel = ivec2(shadowUV * vec2(mapSize));
    float storedDepth = texelFetch(shadowtex1, shadowPixel, 0).r;
    // Same constant normalized-depth bias as Milestone 3A, for every tap.
    return receiverDepth - SHADOW_BIAS <= storedDepth ? 1.0 : 0.0;
}
float filterShadow(vec3 shadowCoord) {
    ivec2 mapSize = textureSize(shadowtex1, 0);
#if SHADOW_FILTER == 0
    return compareShadow(shadowCoord.xy, shadowCoord.z, mapSize);
#elif SHADOW_FILTER == 3
    // Fixed Poisson-style disk in SHADOW-TEXEL space, centered at zero.
    // Eight separated offsets, radius <= 1; softness scales this disk in texels.
    // No arrays, rotation or per-frame randomness. texelFetch may repeat texels.
    vec2 tapStepUV = SHADOW_SOFTNESS / vec2(mapSize);
    float visibility = 0.0;
    visibility += compareShadow(shadowCoord.xy + vec2(-0.6314, -0.5843) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2( 0.9208,  0.3354) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2(-0.4122,  0.8516) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2( 0.5840, -0.7758) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2( 0.0908,  0.0974) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2(-0.8603,  0.1847) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2( 0.4062,  0.8639) * tapStepUV, shadowCoord.z, mapSize);
    visibility += compareShadow(shadowCoord.xy + vec2(-0.0979, -0.9729) * tapStepUV, shadowCoord.z, mapSize);
    // Average eight binary visibility results, including out-of-map lit taps.
    return visibility / 8.0;
#else
    // Actual map resolution determines UV texel size (currently 2048 x 2048).
    vec2 texelSize = 1.0 / vec2(mapSize);
    // Softness controls spacing between taps in shadow-map texels.
    // 3x3 reaches 1 * softness texels from center; 5x5 reaches 2 * softness.
    vec2 tapStepUV = texelSize * SHADOW_SOFTNESS;
#if SHADOW_FILTER == 1
    const int kernelRadius = 1;
#else
    const int kernelRadius = 2;
#endif
    float visibility = 0.0;
    float sampleCount = 0.0;
    for (int y = -kernelRadius; y <= kernelRadius; ++y) {
        for (int x = -kernelRadius; x <= kernelRadius; ++x) {
            vec2 offsetUV = vec2(float(x), float(y)) * tapStepUV;
            visibility += compareShadow(shadowCoord.xy + offsetUV, shadowCoord.z, mapSize);
            sampleCount += 1.0;
        }
    }
    // Average binary comparison RESULTS, never depth values.
    // 3x3 = 9 taps; 5x5 = 25 taps.
    return visibility / sampleCount;
#endif
}
float shadowVisibility(ivec2 pixel) {
#ifdef SHADOWS_ENABLED
    float depth = texelFetch(depthtex1, pixel, 0).r;
    if (depth >= 1.0) return 1.0; // Sky has no receiver position.
    vec2 screenUV = (vec2(pixel) + 0.5) / vec2(textureSize(depthtex1, 0));
    vec3 viewPosition = reconstructViewPosition(screenUV, depth);
    vec3 playerPosition = viewToPlayerPosition(viewPosition);
    // Player-relative position -> light VIEW -> light CLIP.
    vec4 lightClip = shadowProjection * shadowModelView * vec4(playerPosition, 1.0);
    if (lightClip.w <= 0.0) return 1.0;
    // Light clip -> light NDC -> shadow UV and depth, all [0,1].
    vec3 shadowCoord = (lightClip.xyz / lightClip.w) * 0.5 + 0.5;
    // Outside this single map: assume lit instead of wrapping/clamping shadows.
    if (any(lessThan(shadowCoord, vec3(0.0))) ||
        any(greaterThanEqual(shadowCoord, vec3(1.0)))) return 1.0;
    return filterShadow(shadowCoord);
#else
    return 1.0; // Restores Milestone 2 lighting; map remains available for debug.
#endif
}
float rawShadowDepth(vec2 screenUV) {
    // Display the complete light-view map, not projected onto the camera scene.
    ivec2 size = textureSize(shadowtex1, 0);
    ivec2 pixel = clamp(ivec2(screenUV * vec2(size)), ivec2(0), size - ivec2(1));
    return texelFetch(shadowtex1, pixel, 0).r;
}
