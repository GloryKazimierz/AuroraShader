#ifndef AURORA_WATER_CAUSTICS_CAPTURE_INCLUDED
#define AURORA_WATER_CAUSTICS_CAPTURE_INCLUDED
#include "/lib/water_caustics_settings.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
#include "/lib/water_filtered_waves.glsl"
#include "/lib/water_caustics_packing.glsl"
uniform mat4 gbufferModelView;
vec4 waterCausticSurface(vec3 playerPosition, vec3 normalWorld, vec2 worldDx,
                         vec2 worldDy, int waterMaterial, float depth) {
    if (waterMaterial != 1 || any(isnan(playerPosition)) || any(isinf(playerPosition))
        || any(isnan(normalWorld)) || any(isinf(normalWorld))
        || isnan(depth) || isinf(depth) || depth < 0.0 || depth >= 1.0) return vec4(0.0);
    float normalLength = length(normalWorld);
    if (normalLength <= 1e-6 || isnan(normalLength) || isinf(normalLength)) return vec4(0.0);
    vec3 original = normalWorld / normalLength;
    if (original.y < 0.95) return vec4(0.0);
    vec3 viewPosition = (gbufferModelView * vec4(playerPosition, 1.0)).xyz;
    vec3 normalView = transpose(mat3(gbufferModelViewInverse)) * original;
    normalView = waterFilteredWaveNormal(celestialUnit(normalView), viewPosition, 1.0, worldDx, worldDy);
    vec3 normal = transpose(mat3(gbufferModelView)) * normalView;
    if (any(isnan(normal)) || any(isinf(normal)) || dot(normal, normal) <= 1e-12) return vec4(0.0);
    normal = normalize(normal);
    if (normal.y < 0.65) return vec4(0.0);
    // Source alpha/normal eligibility is unchanged; compact slopes + matched
    // shadow depth use explicit invalid codes rather than blended normals.
    return encodeWaterCaustic(normal, depth);
}
#endif
#endif
