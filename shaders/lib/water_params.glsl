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
#if defined(AURORA_WATER_OPTICS_ACTIVE) && WATER_BODY == 4
uniform vec3 auroraWaterBiomeWeights;
#endif
WaterParams waterParams() {
#ifdef AURORA_WATER_OPTICS_ACTIVE
    // Coefficients per metre in linear RGB. Interpolate the medium before Beer attenuation.
    const vec3 freshA=vec3(.18,.055,.025), freshS=vec3(.012,.020,.025);
    const vec3 glacierA=vec3(.24,.052,.090), glacierS=vec3(.032,.105,.083);
    const vec3 woodlandA=vec3(.080,.155,.340), woodlandS=vec3(.066,.044,.022);
    const vec3 oceanA=vec3(.32,.075,.018), oceanS=vec3(.008,.018,.035);
#if WATER_BODY == 1
    vec3 absorption=glacierA, scattering=glacierS;
#elif WATER_BODY == 2
    vec3 absorption=woodlandA, scattering=woodlandS;
#elif WATER_BODY == 3
    vec3 absorption=oceanA, scattering=oceanS;
#elif WATER_BODY == 4
    vec3 weights=auroraWaterBiomeWeights;
    if(any(isnan(weights))||any(isinf(weights)))weights=vec3(0.0);
    weights=clamp(weights,0.0,1.0);
    float sum=dot(weights,vec3(1.0));
    weights/=max(sum,1.0);
    float fresh=max(1.0-sum,0.0);
    vec3 absorption=fresh*freshA+weights.x*glacierA+weights.y*woodlandA+weights.z*oceanA;
    vec3 scattering=fresh*freshS+weights.x*glacierS+weights.y*woodlandS+weights.z*oceanS;
#else
    vec3 absorption=freshA, scattering=freshS;
#endif
    return WaterParams(0.02, 1.0, 16.0, 1.333, absorption, scattering);
#else
    return WaterParams(0.02, 1.0, 16.0);
#endif
}
#endif
