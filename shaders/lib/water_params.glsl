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
    // Art-directed coefficients per metre in linear RGB. Dissolved colored
    // matter absorbs light; suspended material increases the scattered fraction.
#if WATER_BODY == 1
    const vec3 absorption = vec3(0.24, 0.052, 0.090);
    const vec3 scattering = vec3(0.032, 0.105, 0.083);
#elif WATER_BODY == 2
    const vec3 absorption = vec3(0.080, 0.155, 0.340);
    const vec3 scattering = vec3(0.066, 0.044, 0.022);
#elif WATER_BODY == 3
    const vec3 absorption = vec3(0.32, 0.075, 0.018);
    const vec3 scattering = vec3(0.008, 0.018, 0.035);
#else
    const vec3 absorption = vec3(0.18, 0.055, 0.025);
    const vec3 scattering = vec3(0.012, 0.020, 0.025);
#endif
    return WaterParams(0.02, 1.0, 16.0, 1.333, absorption, scattering);
#else
    return WaterParams(0.02, 1.0, 16.0);
#endif
}
#endif
