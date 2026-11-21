#ifndef AURORA_WATER_TRANSPORT_INCLUDED
#define AURORA_WATER_TRANSPORT_INCLUDED
#include "/lib/water_params.glsl"
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_caustics_settings.glsl"

vec3 waterBeerTransmission(vec3 extinction, float meters) {
    return exp(-clamp(extinction * max(meters, 0.0), vec3(0.0), vec3(80.0)));
}
vec3 waterTransportRadiance(vec3 source, float directShare, float viewMeters,
                            float lightMeters, float blockLevel, float skyLevel,
                            vec3 skyRadiance) {
    WaterParams params = waterParams();
    vec3 extinction = (params.absorptionPerMeter + params.scatteringPerMeter)
                    / max(float(WATER_CLARITY), 0.001);
    vec3 outgoing = waterBeerTransmission(extinction, viewMeters);
    vec3 incoming = waterBeerTransmission(extinction, lightMeters);
    // Only the recorded directional component travels the sun/moon-to-bottom leg.
    // Ambient, local lamps and the baseline lightmap are not darkened by that leg.
    float share = clamp(directShare, 0.0, 1.0);
    vec3 incident = max(source, vec3(0.0)) * (vec3(1.0 - share) + share * incoming);
    // A bounded single-scatter source approximation, not solved volumetric transport.
    // It responds to recorded local radiance and sky access; an unlit cave cannot glow.
    source = max(source, vec3(0.0));
    skyRadiance = max(skyRadiance, vec3(0.0));
    vec3 scatterSource = min(source + skyRadiance,
        source * mix(0.25, 0.60, clamp(blockLevel, 0.0, 1.0))
        + skyRadiance * (0.25 * clamp(skyLevel, 0.0, 1.0)));
    vec3 scatterAlbedo = params.scatteringPerMeter
                      / (params.absorptionPerMeter + params.scatteringPerMeter);
    return incident * outgoing + (vec3(1.0) - outgoing) * scatterAlbedo * scatterSource;
}
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
vec3 waterTransportRadiance(vec3 source, float directShare, float viewMeters,
                            float lightMeters, float blockLevel, float skyLevel,
                            vec3 skyRadiance, float causticGain) {
    // Preserve the established transport expression for neutral focusing.
    // Redistribute only its direct component; both Beer legs remain applied once.
    vec3 baseline=waterTransportRadiance(source,directShare,viewMeters,lightMeters,
                                       blockLevel,skyLevel,skyRadiance);
    if (isnan(causticGain) || isinf(causticGain) || causticGain==1.0) return baseline;
    WaterParams params=waterParams();
    vec3 extinction=(params.absorptionPerMeter+params.scatteringPerMeter)
                   /max(float(WATER_CLARITY),0.001);
    vec3 direct=max(source,vec3(0.0))*clamp(directShare,0.0,1.0)
               *waterBeerTransmission(extinction,lightMeters)
               *waterBeerTransmission(extinction,viewMeters);
    return max(vec3(0.0),baseline+direct*(clamp(causticGain,0.0,4.0)-1.0));
}
#endif
float waterTransportFresnel(float normalDotEye) {
    float grazing = 1.0 - clamp(normalDotEye, 0.0, 1.0);
    float square = grazing * grazing;
    WaterParams params = waterParams();
    return params.reflectionF0 + (1.0 - params.reflectionF0) * square * square * grazing;
}
#endif
