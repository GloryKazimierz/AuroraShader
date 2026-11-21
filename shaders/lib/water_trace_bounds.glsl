#ifndef AURORA_WATER_TRACE_BOUNDS_INCLUDED
#define AURORA_WATER_TRACE_BOUNDS_INCLUDED

// Each texel bounds the nearest positive view depth across an 8x8 opaque tile.
// A negative record disables early exit for that tile.
uniform sampler2D colortex10;
bool waterTraceEmptyPrefix(vec2 start, vec2 delta, vec3 q0, vec3 q1, float k0, float k1,
                           ivec2 size, int fineBudget, float minimumPixelSpan) {
    ivec2 tiles = textureSize(colortex10, 0);
    if (any(lessThan(tiles, max(size / 8, ivec2(1))))
        || any(greaterThan(tiles, (size + 7) / 8))) return false;
    float span = max(abs(delta.x), abs(delta.y));
    if (span < 8.0) return false;
    // Each charged fine cell spans at most one pixel on the dominant axis.
    // Even 256 uncharged corner slivers cannot exceed the additional allowance.
    float end = min(1.0, (float(fineBudget) + 256.0 * minimumPixelSpan + 2.0) / span);
    // Traverse tile boundaries from the same projected endpoints as the fine ray.
    // Ambiguous corner contacts take the fine path. Bound depth separately per
    // tile, since one global maximum can lie behind the bed at the ray origin.
    ivec2 stepDir = ivec2(sign(delta));
    ivec2 cell = ivec2(floor(start / 8.0));
    vec2 crossings = vec2(2.0);
    vec2 stride = vec2(2.0);
    for (int axis=0;axis<2;++axis) {
        if (stepDir[axis] == 0) continue;
        if (stepDir[axis]<0 && start[axis]==8.0*float(cell[axis])) cell[axis]--;
        float boundary = 8.0*float(cell[axis]+(stepDir[axis]>0 ? 1 : 0));
        crossings[axis] = (boundary-start[axis])/delta[axis];
        stride[axis] = 8.0/abs(delta[axis]);
    }
    float enter=0.0;
    float nearZ=-q0.z/k0;
    for (int index=0;index<38;++index) {
        if (any(lessThan(cell,ivec2(0))) || any(greaterThanEqual(cell,tiles))) return false;
        float leave=min(end,min(crossings.x,crossings.y));
        if (leave<=enter) return false;
        float denom=mix(k0,k1,leave);
        if (denom<=1e-8) return false;
        float farZ=-mix(q0.z,q1.z,leave)/denom;
        float deep=max(nearZ,farZ);
        float nearest=texelFetch(colortex10,cell,0).r;
        if (!(nearest>deep+max(0.002,deep*0.0001)) || isinf(nearest)) return false;
        if (leave>=end) return true;
        if (abs(crossings.x-crossings.y)*span < 0.02) return false;
        int axis=crossings.x<crossings.y ? 0 : 1;
        cell[axis]+=stepDir[axis];
        crossings[axis]+=stride[axis];
        nearZ=farZ;
        enter=leave;
    }
    return false;
}
#endif
