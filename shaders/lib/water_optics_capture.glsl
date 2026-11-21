#ifndef AURORA_WATER_OPTICS_CAPTURE_INCLUDED
#define AURORA_WATER_OPTICS_CAPTURE_INCLUDED
#include "/lib/water_optics_settings.glsl"
#ifdef AURORA_WATER_OPTICS_ACTIVE

bool waterOpticsOpaqueBlend(ivec4 blendState) {
    return all(equal(blendState, ivec4(0)))
        || (blendState.x == 1 && blendState.y == 0);
}
bool waterOpticsSurfaceBlend(ivec4 blendState) {
    return waterOpticsOpaqueBlend(blendState)
        || (blendState.x == 770 && blendState.y == 771);
}

// A fraction of the existing custom directional modulation, not a separation
// of Minecraft's already baked lightmap. Hardware stores the result in R16F;
// zero is valid (caves/shadow), while -1 explicitly rejects the background.
float waterOpticsDirectionalFraction(float ndotl, vec2 levels, float visibility) {
    if (isnan(ndotl) || isinf(ndotl) || ndotl < 0.0
        || any(isnan(levels)) || any(isinf(levels))
        || any(lessThan(levels, vec2(0.0))) || any(greaterThan(levels, vec2(1.0)))
        || isnan(visibility) || isinf(visibility) || visibility < 0.0 || visibility > 1.0) return -1.0;
    float strength = float(LIGHTING_STRENGTH);
    float ambient = float(AMBIENT_LIGHT);
    float direct = float(DIRECT_LIGHT);
    if (isnan(strength) || isinf(strength) || strength < 0.0 || strength > 1.0
        || isnan(ambient) || isinf(ambient) || ambient < 0.0
        || isnan(direct) || isinf(direct) || direct < 0.0) return -1.0;
    float skyWeight = levels.y * (1.0 - levels.x);
    float weight = strength * skyWeight;
    float residual = 1.0 + weight * (ambient - 1.0);
    float directional = weight * direct * ndotl * visibility;
    float total = residual + directional;
    if (isnan(total) || isinf(total) || total <= 0.0
        || isnan(residual) || isinf(residual) || residual < 0.0
        || isnan(directional) || isinf(directional) || directional < 0.0) return -1.0;
    return clamp(directional / total, 0.0, 1.0);
}

#ifdef WRITE_SURFACE_DATA
uniform sampler2D colortex5;
#ifndef APPLY_LATE_FOG
uniform ivec4 blendFunc;
#endif
vec4 waterOpticsOpaqueOwnership(ivec2 pixel, ivec4 blendState) {
    const vec4 blocker = vec4(1.0, 0.0, 0.0, 0.0);
    if (!waterOpticsOpaqueBlend(blendState)) return blocker;
    ivec2 size = textureSize(colortex5, 0);
    if (any(lessThanEqual(size, ivec2(0))) || any(lessThan(pixel, ivec2(0)))
        || any(greaterThanEqual(pixel, size))) return blocker;
    // Frame-cleared 5.a is zero before deferred. A later draw over a valid
    // snapshot must block replacement even if that draw itself uses no blend.
    // Late pixels with invalid snapshot5 cannot qualify for the compositor.
    if (texelFetch(colortex5, pixel, 0).a != 0.0) return blocker;
    // This output uses OVERWRITE blending, so a known opaque surface removes
    // stale earlier sky/particle flags that its own color has fully covered.
    return vec4(0.0);
}
#endif

#ifdef APPLY_WATER_STYLE
#include "/lib/water_filtered_waves.glsl"
void captureWaterOpticsSurface(vec3 viewPosition, vec3 normalView, vec2 lightmapUV,
    vec2 worldDx, vec2 worldDy, int waterSurface, ivec4 blendState,
    vec4 nativeScene, float windowDepth, out vec4 surface, out vec4 ownership) {
    surface = vec4(0.0);
    ownership = vec4(1.0, 0.0, 0.0, 0.0);
    if (waterSurface != 1 || !waterOpticsSurfaceBlend(blendState)) return;
    if (any(isnan(nativeScene)) || any(isinf(nativeScene))
        || any(lessThan(nativeScene.rgb, vec3(0.0)))
        || any(greaterThan(nativeScene.rgb, vec3(65504.0)))
        || nativeScene.a <= 0.0 || nativeScene.a > 1.0) return;
    if (isnan(windowDepth) || isinf(windowDepth) || windowDepth < 0.0 || windowDepth >= 1.0
        || any(isnan(viewPosition)) || any(isinf(viewPosition))
        || any(isnan(normalView)) || any(isinf(normalView))
        || any(isnan(upPosition)) || any(isinf(upPosition))
        || any(isnan(lightmapUV)) || any(isinf(lightmapUV))
        || isnan(rainStrength) || isinf(rainStrength)) return;
    float environment = celestialEnvironmentWeight();
    if (isnan(environment) || isinf(environment) || environment <= 0.0) return;
    float normalScale = max(max(abs(normalView.x), abs(normalView.y)), abs(normalView.z));
    float upScale = max(max(abs(upPosition.x), abs(upPosition.y)), abs(upPosition.z));
    float viewScale = max(max(abs(viewPosition.x), abs(viewPosition.y)), abs(viewPosition.z));
    if (normalScale <= 1e-6 || upScale <= 1e-6 || viewScale <= 1e-6) return;
    vec3 normal = celestialUnit(normalView);
    float upDot = dot(normal, celestialUnit(upPosition));
    // M1 owns one front-facing top interface only. Side faces/undersides retain
    // the native W3 result; wave animation cannot change the original face gate.
    if (upDot < 0.95 || dot(normal, celestialUnit(-viewPosition)) <= 0.0) return;
    float upwardSurface = smoothstep(0.5, 0.95, upDot);
    normal = waterFilteredWaveNormal(normal, viewPosition, upwardSurface, worldDx, worldDy);
    float normalLengthSquared = dot(normal, normal);
    if (any(isnan(normal)) || any(isinf(normal)) || isnan(normalLengthSquared)
        || isinf(normalLengthSquared) || abs(normalLengthSquared - 1.0) > 0.001) return;
    vec2 levels = clamp((lightmapUV - vec2(0.5 / 16.0)) * (16.0 / 15.0), 0.0, 1.0);
    surface = vec4(normal, windowDepth);
    // Additive normalized-byte counter: exactly one qualifying layer is byte1.
    // The other channels are meaningful only when that count remains exactly1.
    ownership = vec4(1.0 / 255.0, levels, 0.0);
}
#include "/lib/water_exit_capture.glsl"
#endif
#endif
#endif
