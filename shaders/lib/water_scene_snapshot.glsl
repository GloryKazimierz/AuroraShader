#ifndef AURORA_WATER_SCENE_SNAPSHOT_INCLUDED
#define AURORA_WATER_SCENE_SNAPSHOT_INCLUDED
#include "/lib/pipeline_settings.glsl"
#ifndef DEBUG_VIEW
#include "/lib/lighting_settings.glsl"
#endif

// Pack a matched deferred-time radiance/depth sample for future water tracing.
// The caller supplies lit RGB BEFORE camera-path fog, not final display color.
// Alpha is a validity flag, independent of the original scene's coverage alpha.
void encodeWaterSceneSnapshot(vec3 radiance, float surfaceValidity,
                              float opaqueDepth, float preHandDepth,
                              out vec4 snapshotColor, out float snapshotDepth) {
    snapshotColor = vec4(0.0);
    snapshotDepth = 1.0;
#if SCENE_COLOR_MODE == 0 || DEBUG_VIEW != 0
    return;
#else
    // Only surfaces represented by this pack's opaque normal/light G-buffer qualify.
    // Sky, unrecorded geometry and invalid data remain explicit trace misses.
    if (isnan(surfaceValidity) || isinf(surfaceValidity) || surfaceValidity <= 0.5) return;
    if (any(isnan(radiance)) || any(isinf(radiance))
        || any(lessThan(radiance, vec3(0.0)))
        || any(greaterThan(radiance, vec3(65504.0)))) return;
    if (isnan(opaqueDepth) || isinf(opaqueDepth) || opaqueDepth < 0.0 || opaqueDepth >= 1.0
        || isnan(preHandDepth) || isinf(preHandDepth) || preHandDepth < 0.0 || preHandDepth > 1.0) return;
    // Iris captures depthtex2 before opaque hands and depthtex1 before deferred.
    // A nearer depth1 can be a hand over stale terrain metadata: exclude it.
    if (opaqueDepth < preHandDepth) return;
    snapshotColor = vec4(radiance, 1.0);
    snapshotDepth = opaqueDepth;
#endif
}
#endif
