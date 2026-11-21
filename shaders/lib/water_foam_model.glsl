#ifndef AURORA_WATER_FOAM_MODEL_INCLUDED
#define AURORA_WATER_FOAM_MODEL_INCLUDED
#include "/lib/water_filtered_waves.glsl"

// This is a bounded horizontal material-flow model for optical foam. Minecraft
// vertices remain unchanged: it is not a breaking-wave mesh or a fluid solver.
struct WaterFoamFlow {
    vec2 displacement;
    vec2 velocity;
    mat2 jacobian;
    float areaRatio;
    bool valid;
};
bool waterFoamFinite(float v) { return !isnan(v) && !isinf(v); }
bool waterFoamFinite2(vec2 v) { return !any(isnan(v)) && !any(isinf(v)); }
bool waterFoamFinite3(vec3 v) { return !any(isnan(v)) && !any(isinf(v)); }
WaterFoamFlow waterFoamFlowAt(vec2 materialXZ, float seconds, float strength,
                            float speed, vec2 worldDx, vec2 worldDy) {
    WaterFoamFlow result;
    result.displacement = vec2(0.0);
    result.velocity = vec2(0.0);
    result.jacobian = mat2(1.0);
    result.areaRatio = 1.0;
    result.valid = false;
    if (!waterFoamFinite2(materialXZ) || !waterFoamFinite(seconds)
        || !waterFoamFinite(strength) || !waterFoamFinite(speed)
        || seconds < 0.0 || seconds > 3600.0
        || !waterWaveFootprintValid(worldDx, worldDy)) return result;
    strength = clamp(strength, 0.0, 1.0);
    speed = clamp(speed, 0.0, 2.0);
    // Same six conceptual height modes as W2. Lambda*sum(A*|kappa|)<0.178:
    // J stays positive definite, det(J)>0.675; the horizontal map cannot fold.
    const vec2 wave[6] = vec2[6](vec2(11,3),vec2(4,-9),vec2(7,13),
                                vec2(49,19),vec2(-83,31),vec2(151,97));
    const float amplitude[6] = float[6](.06,.04,.03,.006,.0035,.0015);
    const float harmonic[6] = float[6](10,-13,7,24,-31,43);
    vec2 tile = fract(materialXZ / 128.0);
    float cycle = fract(seconds * speed / 200.0);
    for (int index = 0; index < 6; ++index) {
        float weight = waterWavePixelFilter(wave[index], worldDx, worldDy);
        float scale = 1.5 * strength * amplitude[index] * weight;
        vec2 kappa = (6.28318530718 / 128.0) * wave[index];
        vec2 direction = normalize(kappa);
        float angle = 6.28318530718 * fract(dot(wave[index], tile) + harmonic[index] * cycle);
        float sine = sin(angle);
        result.displacement += scale * direction * cos(angle);
        result.velocity -= scale * direction * sine * (6.28318530718 * harmonic[index] * speed / 200.0);
        result.jacobian -= scale * sine * outerProduct(direction, kappa);
    }
    result.areaRatio = determinant(result.jacobian);
    result.valid = waterFoamFinite2(result.displacement) && waterFoamFinite2(result.velocity)
                && waterFoamFinite(result.areaRatio) && result.areaRatio > 0.675;
    return result;
}
bool waterFoamMaterialPoint(vec2 surfaceXZ, float seconds, float strength, float speed,
                           vec2 worldDx, vec2 worldDy, out vec2 materialXZ,
                           out WaterFoamFlow flow) {
    materialXZ = surfaceXZ;
    flow = waterFoamFlowAt(materialXZ, seconds, strength, speed, worldDx, worldDy);
    if (!flow.valid || any(greaterThan(abs(surfaceXZ),vec2(256.0)))) return false;
    // Invert x=q+D(q,t). Three bounded 2x2 Newton steps keep foam attached to
    // this model's material coordinates, rather than treating q as world x.
    for (int iteration=0; iteration<3; ++iteration) {
        vec2 residual = materialXZ + flow.displacement - surfaceXZ;
        mat2 j = flow.jacobian;
        vec2 step = vec2(j[1][1]*residual.x-j[1][0]*residual.y,
                         -j[0][1]*residual.x+j[0][0]*residual.y) / flow.areaRatio;
        if (!waterFoamFinite2(step) || length(step) > 0.3) return false;
        materialXZ -= step;
        flow = waterFoamFlowAt(materialXZ, seconds, strength, speed, worldDx, worldDy);
        if (!flow.valid) return false;
    }
    return length(materialXZ + flow.displacement - surfaceXZ) <= 0.0001;
}
float waterFoamEvidence(float areaRatio, float shoreDistance, float grain, float waveSpeed) {
    if (!waterFoamFinite(areaRatio) || !waterFoamFinite(shoreDistance)
        || !waterFoamFinite(grain) || !waterFoamFinite(waveSpeed)) return 0.0;
    // Compression is det(dX/dq), never a proxy based on normal height/steepness.
    // A static wave pattern does not continuously create crest foam.
    float crest = (1.0-smoothstep(0.90,0.98,areaRatio)) * 0.45 * clamp(waveSpeed,0.0,1.0);
    float shore = shoreDistance < 0.0 ? 0.0 : (1.0-smoothstep(0.02,0.55,shoreDistance))*0.6;
    return clamp(max(crest,shore) * mix(0.55,1.0,clamp(grain,0.0,1.0)),0.0,0.6);
}
float waterFoamEvolve(float previousCoverage, float previousAge, float evidence,
                      float elapsed, bool historyValid, out float age) {
    age = 0.0;
    if (!waterFoamFinite(evidence)) return 0.0;
    evidence = clamp(evidence,0.0,0.6);
    if (!historyValid || !waterFoamFinite(previousCoverage) || !waterFoamFinite(previousAge)
        || !waterFoamFinite(elapsed) || previousCoverage < 0.0 || previousCoverage > 0.6
        || previousAge < 0.0 || previousAge > 2.5 || elapsed <= 0.0 || elapsed > 0.1
        || previousAge + elapsed > 2.5) return evidence;
    float surviving = previousCoverage * exp2(-elapsed / 0.65);
    if (surviving > evidence) { age = previousAge + elapsed; return surviving; }
    return evidence;
}
vec3 waterFoamDiffuse(vec3 skyIrradiance, vec3 directIrradiance, vec3 lampIrradiance,
                      float skyAccess, float blockAccess, float normalDotLight, float visibility) {
    if (!waterFoamFinite3(skyIrradiance) || !waterFoamFinite3(directIrradiance)
        || !waterFoamFinite3(lampIrradiance) || !waterFoamFinite(skyAccess)
        || !waterFoamFinite(blockAccess) || !waterFoamFinite(normalDotLight)
        || !waterFoamFinite(visibility)) return vec3(0.0);
    float sky = clamp(skyAccess,0.0,1.0);
    float block = clamp(blockAccess,0.0,1.0);
    vec3 incident = max(skyIrradiance,vec3(0.0))*sky
                  + max(directIrradiance,vec3(0.0))*sky*clamp(normalDotLight,0.0,1.0)*clamp(visibility,0.0,1.0)
                  + max(lampIrradiance,vec3(0.0))*block*block*block;
    // Diffuse albedo / pi. There is deliberately no emission or light-independent
    // white term: zero incident illumination gives exactly zero foam radiance.
    return min(vec3(65504.0),vec3(0.88,0.91,0.92)*(1.0/3.14159265359)*incident);
}
#endif
