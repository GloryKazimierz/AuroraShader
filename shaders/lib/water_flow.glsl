#ifndef AURORA_WATER_FLOW_INCLUDED
#define AURORA_WATER_FLOW_INCLUDED

// The rendered triangle supplies its slope. Gravity projected onto the face
// points downhill on river steps and vertically down a waterfall. A flat
// triangle has no measured current. Speed is an artistic approximation.
vec3 waterFlowVelocity(vec3 geometricNormal) {
    vec3 down = vec3(0.0,-1.0,0.0);
    vec3 tangent = down - geometricNormal * dot(geometricNormal,down);
    float slope = length(tangent);
    if (slope <= 0.015) return vec3(0.0);
    return tangent * (2.4 * smoothstep(0.015,0.10,slope) / sqrt(slope));
}
float waterCurrentBand(vec3 k, vec3 dx, vec3 dy) {
    vec2 cycles = abs(vec2(dot(k,dx),dot(k,dy))) / 128.0;
    float frequency = max(cycles.x,cycles.y);
    if (frequency >= 0.5) return 0.0;
    return waterWaveSinc(3.14159265*cycles.x) * waterWaveSinc(3.14159265*cycles.y)
         * (1.0-smoothstep(0.25,0.5,frequency));
}
vec3 waterFlowGradient(vec3 position, vec3 velocity, float seconds, vec3 dx, vec3 dy) {
    // Blend independently advected world-axis patterns. Neighboring triangles
    // share phase in each direction, even when their estimated flow changes.
    // Horizontal bands travel 1.28 blocks/s and falling bands 2.56 blocks/s.
    // Integer harmonics close after 100 s and across the Iris time wrap.
    vec3 weight = abs(velocity);
    weight /= max(dot(weight,vec3(1.0)),1e-6);
    float cycle = fract(seconds/100.0);
    const vec3 k[3] = vec3[3](vec3(91,-21,12),vec3(-23,34,103),vec3(53,47,-71));
    const float a[3] = float[3](0.012,0.009,0.006);
    vec3 gradient = vec3(0.0);
    for (int i=0;i<3;++i) {
        float band = waterCurrentBand(k[i],dx,dy);
        if (band<=0.0) continue;
        float phase = dot(position,k[i])/128.0;
        vec3 travel = k[i] * sign(velocity) * vec3(1.0,2.0,1.0);
        vec3 angles = 6.2831853 * fract(vec3(phase)-cycle*travel);
        gradient += (a[i]*6.2831853/128.0)*k[i]*dot(weight,cos(angles))*band;
    }
    return gradient;
}
bool waterFlowFrame(vec3 dx, vec3 dy, vec3 faceView, vec3 playerPosition,
                    out vec3 rippleView, out float sideWeight) {
    rippleView=vec3(0.0);
    sideWeight=0.0;
    if (any(isnan(dx)) || any(isinf(dx)) || any(isnan(dy)) || any(isinf(dy))
        || any(isnan(playerPosition)) || any(isinf(playerPosition))
        || any(isnan(cameraPositionFract)) || any(isinf(cameraPositionFract))
        || isnan(frameTimeCounter) || isinf(frameTimeCounter)) return false;
    vec3 n=cross(dx,dy);
    float n2=dot(n,n);
    if (!(n2>1e-14) || isinf(n2)) return false;
    n*=inversesqrt(n2);
    mat3 normalToView=transpose(mat3(gbufferModelViewInverse));
    if (dot(normalToView*n,faceView)<0.0) n=-n;
    if (n.y< -0.10) return false;
    vec3 velocity=waterFlowVelocity(n);
    float speed=length(velocity);
    if (speed<=0.0) return false;
    vec3 anchor=vec3(uvec3(cameraPositionInt)&uvec3(127u));
    vec3 position=mod(anchor+cameraPositionFract+playerPosition,128.0);
    vec3 g=waterFlowGradient(position,velocity,frameTimeCounter*float(WATER_WAVE_SPEED),dx,dy);
    vec3 tangentSlope=g-dot(g,n)*n;
    float scale=length(normalToView*n);
    if (!(scale>1e-6)) return false;
    rippleView=normalToView*tangentSlope/scale*float(WATER_WAVE_STRENGTH)*min(speed,1.0);
    sideWeight=1.0-smoothstep(0.5,0.95,n.y);
    return !any(isnan(rippleView)) && !any(isinf(rippleView));
}
#endif
