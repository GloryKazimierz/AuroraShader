#ifndef AURORA_WATER_REFLECTION_FILTER_INCLUDED
#define AURORA_WATER_REFLECTION_FILTER_INCLUDED
#include "/lib/water_screen_reflection.glsl"
uniform sampler2D colortex9;

bool waterReflectionSample(ivec2 pixel, ivec2 size, out vec3 point, out vec3 radiance) {
    point = vec3(0.0);
    radiance = vec3(0.0);
    if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, size))) return false;
    vec4 sampleColor = texelFetch(colortex5, pixel, 0);
    float sampleDepth = texelFetch(colortex6, pixel, 0).r;
    float share = texelFetch(colortex9, pixel, 0).r;
    if (!waterTraceFinite4(sampleColor) || sampleColor.a != 1.0
        || any(lessThan(sampleColor.rgb, vec3(0.0))) || any(greaterThan(sampleColor.rgb, vec3(65504.0)))
        || isnan(sampleDepth) || isinf(sampleDepth) || sampleDepth < 0.0 || sampleDepth >= 1.0
        || sampleDepth != texelFetch(depthtex1, pixel, 0).r
        || isnan(share) || isinf(share) || share < 0.0 || share > 1.0) return false;
    if (!waterTraceUnproject(pixel, sampleDepth, size, point)) return false;
    radiance = sampleColor.rgb;
    return true;
}
bool waterReflectionGeometricNormal(vec3 point, vec3 left, vec3 right,
                                    vec3 down, vec3 up, out vec3 normal) {
    normal = vec3(0.0);
    // Four one-sided tangent pairs must describe the same local plane. The
    // opposite controls reject a crease even when its nearer depths coincide.
    vec3 tangentsX[2] = vec3[2](point - left, right - point);
    vec3 tangentsY[2] = vec3[2](point - down, up - point);
    for (int y = 0; y < 2; ++y) {
        for (int x = 0; x < 2; ++x) {
            vec3 crossNormal = cross(tangentsX[x], tangentsY[y]);
            float scale = max(max(abs(crossNormal.x), abs(crossNormal.y)), abs(crossNormal.z));
            if (!waterTraceFinite3(crossNormal) || scale <= 1e-12) return false;
            vec3 candidate = normalize(crossNormal / scale);
            if (!waterTraceFinite3(candidate)) return false;
            if (x == 0 && y == 0) normal = candidate;
            else if (dot(normal, candidate) < 0.99) return false;
        }
    }
    return true;
}
void waterReflectionAccumulate(vec3 point, vec3 radiance, vec3 center, vec3 normal,
                               float tolerance, float weight, inout vec3 sum,
                               inout float totalWeight) {
    float planeDistance = abs(dot(point - center, normal));
    if (weight <= 0.0 || planeDistance >= tolerance) return;
    weight *= 1.0 - smoothstep(tolerance * 0.5, tolerance, planeDistance);
    sum += radiance * weight;
    totalWeight += weight;
}
vec3 waterFilteredReflectionRadiance(ivec2 hitPixel, vec3 hitView, vec3 nearestRadiance) {
    ivec2 size = textureSize(colortex6, 0);
    if (any(lessThan(size, ivec2(3))) || any(notEqual(size, textureSize(colortex5, 0)))
        || any(notEqual(size, textureSize(colortex9, 0)))
        || any(notEqual(size, textureSize(depthtex1, 0)))) return nearestRadiance;
    vec2 screen;
    vec3 q;
    float reciprocalW;
    if (!waterTraceProject(hitView, size, screen, q, reciprocalW)
        || any(notEqual(ivec2(floor(screen)), hitPixel))) return nearestRadiance;
    // Cache the center and four axial controls. The optional diagonal below is
    // the only extra read: at most SIX records /24 explicit texture fetches.
    // No mip chain, temporal history, large arrays or per-tap normal re-fetches.
    vec3 center, centerRGB, left, leftRGB, right, rightRGB, down, downRGB, up, upRGB;
    if (!waterReflectionSample(hitPixel, size, center, centerRGB)
        || !waterReflectionSample(hitPixel + ivec2(-1,0), size, left, leftRGB)
        || !waterReflectionSample(hitPixel + ivec2(1,0), size, right, rightRGB)
        || !waterReflectionSample(hitPixel + ivec2(0,-1), size, down, downRGB)
        || !waterReflectionSample(hitPixel + ivec2(0,1), size, up, upRGB)) return nearestRadiance;
    vec3 normal;
    if (!waterReflectionGeometricNormal(center, left, right, down, up, normal)) return nearestRadiance;
    // Unit-pixel radiance footprint. This is not a solved roughness/highlight lobe.
    vec2 offset = screen - (vec2(hitPixel) + 0.5);
    ivec2 side = ivec2(offset.x < 0.0 ? -1 : 1, offset.y < 0.0 ? -1 : 1);
    vec2 fraction = abs(offset);
    float tolerance = clamp(-center.z * 0.0005, 0.025, 0.15);
    vec3 sum = vec3(0.0);
    float totalWeight = 0.0;
    waterReflectionAccumulate(center, centerRGB, center, normal, tolerance,
        (1.0 - fraction.x) * (1.0 - fraction.y), sum, totalWeight);
    waterReflectionAccumulate(side.x < 0 ? left : right, side.x < 0 ? leftRGB : rightRGB,
        center, normal, tolerance, fraction.x * (1.0 - fraction.y), sum, totalWeight);
    waterReflectionAccumulate(side.y < 0 ? down : up, side.y < 0 ? downRGB : upRGB,
        center, normal, tolerance, (1.0 - fraction.x) * fraction.y, sum, totalWeight);
    if (fraction.x * fraction.y > 0.0) {
        vec3 diagonal, diagonalRGB;
        if (waterReflectionSample(hitPixel + side, size, diagonal, diagonalRGB))
            waterReflectionAccumulate(diagonal, diagonalRGB, center, normal, tolerance,
                fraction.x * fraction.y, sum, totalWeight);
    }
    if (totalWeight <= 1e-6) return nearestRadiance;
    vec3 filtered = sum / totalWeight;
    if (!waterTraceFinite3(filtered)) return nearestRadiance;
    return clamp(filtered, vec3(0.0), vec3(65504.0));
}
#endif
