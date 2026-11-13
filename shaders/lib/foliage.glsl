#ifndef AURORA_FOLIAGE_INCLUDED
#define AURORA_FOLIAGE_INCLUDED
#include "/lib/foliage_settings.glsl"
#include "/lib/pipeline_settings.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/camera_anchor.glsl"
uniform float frameTimeCounter;

// Both terrain and shadow call this exact world-oriented displacement.
// Matrix uniforms stay at the call sites, so the same math can be tested independently.
vec3 foliageDisplacement(vec3 playerPosition, vec2 material, vec4 midBlock) {
#if FOLIAGE_WIND == 0 || SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return vec3(0.0);
#else
    float strength = clamp(FOLIAGE_WIND_STRENGTH, 0.0, 1.0);
    if (strength <= 0.0) return vec3(0.0);
    // Modern Sodium encodes nonfluid as 0; the general Iris attribute uses -1.
    if (material.y != 0.0 && material.y != -1.0) return vec3(0.0);
    bool leaves = material.x == 10002.0;
    bool shortGrass = material.x == 10003.0;
    bool tallLower = material.x == 10004.0;
    bool tallUpper = material.x == 10005.0;
    if (!leaves && !shortGrass && !tallLower && !tallUpper) return vec3(0.0);
    if (any(isnan(playerPosition)) || any(isinf(playerPosition))
        || any(isnan(cameraPositionFract.xz)) || any(isinf(cameraPositionFract.xz))) return vec3(0.0);

    float rootWeight = 1.0;
    if (!leaves) {
        if (isnan(midBlock.y) || isinf(midBlock.y)) return vec3(0.0);
        // at_midBlock points vertex -> block center in signed 1/64-block units.
        // The small dead zone fixes ground-level roots despite attribute quantization.
        // Tall halves share a single 0..2 height: their joining edges bend equally.
        float height = 0.5 - midBlock.y / 64.0 + (tallUpper ? 1.0 : 0.0);
        float plantHeight = shortGrass ? 1.0 : 2.0;
        float bend = clamp((height - 1.0 / 64.0) / (plantHeight - 1.0 / 64.0), 0.0, 1.0);
        rootWeight = bend * bend;
        if (rootWeight <= 0.0) return vec3(0.0);
    }

    // Preserve precision at large and negative world coordinates. No shifted cameraPosition.
    vec2 anchor = vec2(uvec2(cameraPositionInt.xz) & uvec2(127u));
    vec2 tile = fract((anchor + cameraPositionFract.xz + playerPosition.xz) / 128.0);
    float seconds = frameTimeCounter;
    if (isnan(seconds) || isinf(seconds)) seconds = 0.0;
    float cycle = fract(max(seconds, 0.0) * (float(FOLIAGE_WIND_SPEED) / 200.0));
    // Integer spatial/time harmonics join the 128-block tile and Iris's 3600s reset.
    float phase0 = 6.28318530718 * fract(dot(vec2(1.0, 2.0), tile) + 37.0 * cycle);
    float phase1 = 6.28318530718 * fract(dot(vec2(3.0, -1.0), tile) - 53.0 * cycle);
    // Orthonormal directions: field length <= sqrt(0.6^2 + 0.4^2).
    // Sampling continuous vertex position keeps neighboring leaf/plant edges coherent.
    vec2 field = 0.6 * sin(phase0) * vec2(0.8, 0.6)
               + 0.4 * sin(phase1) * vec2(-0.6, 0.8);
    vec2 offset = field * (leaves ? 0.08 : 0.20) * strength * rootWeight;
    if (any(isnan(offset)) || any(isinf(offset))) return vec3(0.0);
    return vec3(offset.x, 0.0, offset.y);
#endif
}

vec4 foliageWindClip(vec4 baseline, vec4 viewVertex, mat4 passInverse,
                     mat4 passModelView, mat4 projection, vec2 material, vec4 midBlock) {
#if FOLIAGE_WIND == 0 || SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return baseline;
#else
    if (FOLIAGE_WIND_STRENGTH <= 0.0) return baseline;
    vec4 playerH = passInverse * viewVertex;
    if (any(isnan(playerH)) || any(isinf(playerH)) || abs(playerH.w) <= 1e-6) return baseline;
    vec3 delta = foliageDisplacement(playerH.xyz / playerH.w, material, midBlock);
    if (all(equal(delta, vec3(0.0)))) return baseline;
    // Project only a direction (w=0): matrix translations must not move wind vectors.
    // Preserve original ftransform rounding, and return it exactly on every bypass.
    vec4 projectedDelta = projection * (passModelView * vec4(delta, 0.0));
    vec4 displaced = baseline + projectedDelta;
    if (any(isnan(projectedDelta)) || any(isinf(projectedDelta))
        || any(isnan(displaced)) || any(isinf(displaced))) return baseline;
    return displaced;
#endif
}
#endif
