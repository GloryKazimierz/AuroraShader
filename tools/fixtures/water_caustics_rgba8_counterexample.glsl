// Test-only rejected low-precision storage, never included by a pack program.
#ifndef AURORA_WATER_CAUSTICS_PACKING_INCLUDED
#define AURORA_WATER_CAUSTICS_PACKING_INCLUDED
#include "/lib/water_caustics_settings.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
// Slopes are horizontal signed normal components divided by positive N.y.
// The original face has N.y>=.95 and the shared spectrum's maximum gradient
// stays below .12 at strength1. Range +/-.5 covers their combination; any
// unexpected/custom transform overflow explicitly invalidates the record.
uint causticDepthCode(float depth) {
    return uint(floor(depth*65534.0+0.5))+1u;
}
vec4 encodeWaterCaustic(vec3 normal, float depth) {
    if (any(isnan(normal)) || any(isinf(normal)) || isnan(depth) || isinf(depth)
        || depth<0.0 || depth>=1.0 || normal.y<=0.0
        || abs(dot(normal,normal)-1.0)>.001) return vec4(0.0);
    vec2 slope=normal.xz/normal.y;
    if (any(greaterThan(abs(slope),vec2(.5)))) return vec4(0.0);
    uint word=causticDepthCode(depth);
    vec2 encoded=floor(slope*254.0+128.0+0.5);
    return vec4(encoded,float(word>>8u),float(word&255u))/255.0;
}
bool decodeWaterCaustic(vec4 record, float actualDepth, out vec3 normal) {
    normal=vec3(0.0);
    if (any(isnan(record)) || any(isinf(record)) || isnan(actualDepth) || isinf(actualDepth)
        || any(lessThan(record,vec4(0.0))) || any(greaterThan(record,vec4(1.0)))
        || actualDepth<0.0 || actualDepth>=1.0) return false;
    uvec4 code=uvec4(floor(record*255.0+0.5));
    uint depth=(code.z<<8u)|code.w;
    vec2 slope=(vec2(code.xy)-128.0)/254.0;
    // Code zero is reserved invalid for slopes AND depth. RGBA8 compares the
    // same declared 16-bit quantization; an edge-bin mismatch rejects safely.
    if (code.x==0u || code.y==0u || depth==0u) return false;
    if (depth!=causticDepthCode(actualDepth)) return false;
    normal=normalize(vec3(slope.x,1.0,slope.y));
    return !any(isnan(normal)) && !any(isinf(normal));
}
#endif
#endif
