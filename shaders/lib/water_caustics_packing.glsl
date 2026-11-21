#ifndef AURORA_WATER_CAUSTICS_PACKING_INCLUDED
#define AURORA_WATER_CAUSTICS_PACKING_INCLUDED
#include "/lib/water_caustics_settings.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
// Slopes are horizontal signed normal components divided by positive N.y.
// The original face has N.y>=.95 and the shared spectrum's maximum gradient
// stays below .12 at strength1. Range +/-.5 covers their combination; any
// unexpected/custom transform overflow explicitly invalidates the record.
uint causticDepthCode(float depth) {
    return floatBitsToUint(depth)+1u;
}
vec4 encodeWaterCaustic(vec3 normal, float depth) {
    if (any(isnan(normal)) || any(isinf(normal)) || isnan(depth) || isinf(depth)
        || depth<0.0 || depth>=1.0 || normal.y<=0.0
        || abs(dot(normal,normal)-1.0)>.001) return vec4(0.0);
    vec2 slope=normal.xz/normal.y;
    if (any(greaterThan(abs(slope),vec2(.5)))) return vec4(0.0);
    uint word=causticDepthCode(depth);
    vec2 encoded=floor(slope*65534.0+32768.0+0.5);
    return vec4(encoded,float(word>>16u),float(word&65535u))/65535.0;
}
bool decodeWaterCaustic(vec4 record, float actualDepth, out vec3 normal) {
    normal=vec3(0.0);
    if (any(isnan(record)) || any(isinf(record)) || isnan(actualDepth) || isinf(actualDepth)
        || any(lessThan(record,vec4(0.0))) || any(greaterThan(record,vec4(1.0)))
        || actualDepth<0.0 || actualDepth>=1.0) return false;
    uvec4 code=uvec4(floor(record*65535.0+0.5));
    uint depth=(code.z<<16u)|code.w;
    vec2 slope=(vec2(code.xy)-32768.0)/65534.0;
    // Code zero is reserved invalid for slopes AND depth.
    if (code.x==0u || code.y==0u || depth==0u) return false;
    // Preserve the raw source float in the two16-bit lanes. Real D24 storage
    // can shift gl_FragCoord.z by one normalized D24 unit, as in M0/M1.
    float capturedDepth=uintBitsToFloat(depth-1u);
    if (isnan(capturedDepth) || isinf(capturedDepth) || capturedDepth<0.0 || capturedDepth>=1.0
        || abs(capturedDepth-actualDepth)>1.0/16777215.0) return false;
    normal=normalize(vec3(slope.x,1.0,slope.y));
    return !any(isnan(normal)) && !any(isinf(normal));
}
#endif
#endif
