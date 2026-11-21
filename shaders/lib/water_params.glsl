#ifndef AURORA_WATER_PARAMS_INCLUDED
#define AURORA_WATER_PARAMS_INCLUDED
#include "/lib/water_optics_settings.glsl"
// Shared calibration; optical transport fields exist only in the active M1 path.
struct WaterParams {
    float reflectionF0;
    float worldBlockMeters;
    float debugGapRangeMeters;
#ifdef AURORA_WATER_OPTICS_ACTIVE
    float refractiveIndex;
    vec3 absorptionPerMeter;
    vec3 scatteringPerMeter;
#endif
};
WaterParams waterParams() {
#ifdef AURORA_WATER_OPTICS_ACTIVE
    return WaterParams(0.02, 1.0, 16.0, 1.333,
                       vec3(0.18, 0.055, 0.025), vec3(0.012, 0.020, 0.025));
#else
    return WaterParams(0.02, 1.0, 16.0);
#endif
}
#endif
