#ifndef AURORA_WATER_SCREEN_REFLECTION_INCLUDED
#define AURORA_WATER_SCREEN_REFLECTION_INCLUDED
#include "/lib/water_screen_reflection_settings.glsl"
#include "/lib/position.glsl"
uniform mat4 gbufferProjection;
uniform sampler2D colortex5;
uniform sampler2D colortex6;
uniform sampler2D depthtex1;

bool waterTraceFinite3(vec3 value) {
    return !any(isnan(value)) && !any(isinf(value));
}
bool waterTraceFinite4(vec4 value) {
    return !any(isnan(value)) && !any(isinf(value));
}
bool waterTraceProject(vec3 view, ivec2 size, out vec2 pixel, out vec3 weightedView, out float reciprocalW) {
    pixel = vec2(0.0);
    weightedView = vec3(0.0);
    reciprocalW = 0.0;
    vec4 clip = gbufferProjection * vec4(view, 1.0);
    if (!waterTraceFinite4(clip) || clip.w <= 1e-6) return false;
    reciprocalW = 1.0 / clip.w;
    weightedView = view * reciprocalW;
    pixel = (clip.xy * reciprocalW * 0.5 + 0.5) * vec2(size);
    return waterTraceFinite3(weightedView) && !any(isnan(pixel)) && !any(isinf(pixel));
}
bool waterTraceUnproject(ivec2 pixel, float depth, ivec2 size, out vec3 view) {
    view = vec3(0.0);
    vec2 uv = (vec2(pixel) + 0.5) / vec2(size);
    vec4 point = gbufferProjectionInverse * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    if (!waterTraceFinite4(point) || point.w <= 1e-6) return false;
    view = point.xyz / point.w;
    return waterTraceFinite3(view) && view.z < 0.0;
}
bool waterTracePoint(vec3 q0, vec3 q1, float k0, float k1, float fraction, out vec3 view) {
    view = vec3(0.0);
    float denominator = mix(k0, k1, fraction);
    if (isnan(denominator) || isinf(denominator) || denominator <= 1e-8) return false;
    view = mix(q0, q1, fraction) / denominator;
    return waterTraceFinite3(view) && view.z < 0.0;
}

// A bounded screen-space grid trace, not an off-screen scene representation.
// Visit crossed pixels including diagonal entries. Discard only corner slivers
// below the declared FP32 pixel precision bound, plus zero-area corner contacts.
bool traceWaterScene(vec3 originView, vec3 directionView, out ivec2 hitPixel,
                     out vec3 hitView, out vec3 hitRGB, out float hitDistance,
                     out float hitConfidence, out int stepsTaken) {
    hitPixel = ivec2(-1);
    hitView = vec3(0.0);
    hitRGB = vec3(0.0);
    hitDistance = 0.0;
    hitConfidence = 0.0;
    stepsTaken = 0;
#if WATER_SCREEN_REFLECTIONS == 0
    return false;
#else
    const float minimumTravel = 0.05;
    const float maximumTravel = 64.0;
    int stepLimit = clamp(int(WATER_REFLECTION_STEPS), 1, 128);
    ivec2 size = textureSize(colortex6, 0);
    if (any(lessThanEqual(size, ivec2(0))) || any(notEqual(size, textureSize(colortex5, 0)))
        || any(notEqual(size, textureSize(depthtex1, 0)))) return false;
    if (!waterTraceFinite3(originView) || !waterTraceFinite3(directionView)) return false;
    float directionScale = max(max(abs(directionView.x), abs(directionView.y)), abs(directionView.z));
    if (directionScale <= 1e-6) return false;
    vec3 direction = normalize(directionView / directionScale);
    if (!waterTraceFinite3(direction)) return false;

    // Derive the standard Iris camera near plane from the SAME inverse projection
    // as depth reconstruction; do not introduce a separately configured near value.
    vec4 nearH = gbufferProjectionInverse * vec4(0.0, 0.0, -1.0, 1.0);
    if (!waterTraceFinite4(nearH) || nearH.w <= 1e-6) return false;
    float nearZ = nearH.z / nearH.w;
    if (isnan(nearZ) || isinf(nearZ) || nearZ >= 0.0) return false;
    nearZ -= max(0.0001, abs(nearZ) * 0.0001);
    if (originView.z >= nearZ) return false;
    float endTravel = maximumTravel;
    if (direction.z > 0.0) endTravel = min(endTravel, (nearZ - originView.z) / direction.z);
    if (isnan(endTravel) || isinf(endTravel) || endTravel <= minimumTravel) return false;

    vec2 sourceScreen, p0, p1;
    vec3 sourceQ, q0, q1;
    float sourceK, k0, k1;
    if (!waterTraceProject(originView, size, sourceScreen, sourceQ, sourceK)
        || any(lessThan(sourceScreen, vec2(0.0))) || any(greaterThanEqual(sourceScreen, vec2(size)))) return false;
    ivec2 sourcePixel = ivec2(floor(sourceScreen));
    if (!waterTraceProject(originView + direction * minimumTravel, size, p0, q0, k0)
        || !waterTraceProject(originView + direction * endTravel, size, p1, q1, k1)
        || any(lessThan(p0, vec2(0.0))) || any(greaterThanEqual(p0, vec2(size)))) return false;

    // Clip only the projected endpoint, carrying homogeneous interpolation data
    // with the same fraction. Every subsequent fetch still checks integer bounds.
    vec2 delta = p1 - p0;
    float screenEnd = 1.0;
    for (int axis = 0; axis < 2; ++axis) {
        if (delta[axis] > 0.0) screenEnd = min(screenEnd, (float(size[axis]) - p0[axis]) / delta[axis]);
        else if (delta[axis] < 0.0) screenEnd = min(screenEnd, -p0[axis] / delta[axis]);
    }
    if (isnan(screenEnd) || isinf(screenEnd) || screenEnd <= 0.0) return false;
    p1 = mix(p0, p1, screenEnd);
    q1 = mix(q0, q1, screenEnd);
    k1 = mix(k0, k1, screenEnd);
    delta = p1 - p0;
    float projectedSpan = max(abs(delta.x), abs(delta.y));
    if (projectedSpan < 1e-5) return false;
    // Four FP32 epsilons at viewport scale, with a tiny absolute floor. This
    // removes numerically ambiguous corner slivers rather than changing a tie
    // comparison or charging unstable extra cells to the confidence budget.
    float minimumPixelSpan = max(0.0001, 4.76837158203125e-7 * float(max(size.x, size.y)));
    ivec2 stepDirection = ivec2(sign(delta));
    ivec2 cell = ivec2(floor(p0));
    for (int axis = 0; axis < 2; ++axis) {
        if (stepDirection[axis] < 0 && p0[axis] == float(cell[axis])) cell[axis] -= 1;
    }
    float enterFraction = 0.0;
    // At most one corner sliver between ordinary cells; the hard iteration cap
    // also bounds pathological input while only processed cells consume budget.
    for (int iteration = 0; iteration < 256; ++iteration) {
        if (stepsTaken >= stepLimit || enterFraction >= 1.0) break;
        // Recompute both crossings from integer cell boundaries, avoiding drift
        // from accumulated floating-point increments. A stationary axis ends at1.
        vec2 crossings = vec2(1.0);
        for (int axis = 0; axis < 2; ++axis) {
            if (stepDirection[axis] != 0) {
                float boundary = float(cell[axis] + (stepDirection[axis] > 0 ? 1 : 0));
                crossings[axis] = (boundary - p0[axis]) / delta[axis];
            }
        }
        float exitFraction = min(1.0, min(crossings.x, crossings.y));
        if (exitFraction <= enterFraction) return false;
        if (projectedSpan * (exitFraction - enterFraction) <= minimumPixelSpan) {
            // Skip before texture reads, unknown-occluder tests and step counting.
            enterFraction = exitFraction;
            for (int axis = 0; axis < 2; ++axis) {
                if (crossings[axis] <= exitFraction) cell[axis] += stepDirection[axis];
            }
            continue;
        }
        stepsTaken += 1;
        ivec2 pixel = cell;
        if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, size))) return false;
        vec3 segmentStart, segmentEnd;
        if (!waterTracePoint(q0, q1, k0, k1, enterFraction, segmentStart)
            || !waterTracePoint(q0, q1, k0, k1, exitFraction, segmentEnd)) return false;
        float rayDepthMin = min(-segmentStart.z, -segmentEnd.z);
        float rayDepthMax = max(-segmentStart.z, -segmentEnd.z);
        // Bound uncertainty from one depth sample over this pixel's ray span.
        // This is a finite sampling tolerance, NOT physical object thickness.
        float thickness = clamp(rayDepthMax - rayDepthMin, 0.15, 0.5);
        vec4 payload = texelFetch(colortex5, pixel, 0);
        float depth = texelFetch(colortex6, pixel, 0).r;
        float opaqueDepth = texelFetch(depthtex1, pixel, 0).r;
        if (!waterTraceFinite4(payload) || isnan(depth) || isinf(depth)
            || isnan(opaqueDepth) || isinf(opaqueDepth) || opaqueDepth < 0.0 || opaqueDepth > 1.0) return false;
        if (payload.a == 0.0) {
            // W1 clears invalid pairs, including hands and unrecorded surfaces.
            // Keep raw opaque depth as an OCCLUSION GUARD, never a hit/color source.
            if (any(notEqual(payload.rgb, vec3(0.0))) || depth != 1.0) return false;
            if (opaqueDepth < 1.0) {
                vec3 unknownView;
                if (!waterTraceUnproject(pixel, opaqueDepth, size, unknownView)) return false;
                if (rayDepthMax >= -unknownView.z) return false;
            }
        } else {
            if (payload.a != 1.0 || any(lessThan(payload.rgb, vec3(0.0)))
                || any(greaterThan(payload.rgb, vec3(65504.0))) || depth < 0.0 || depth >= 1.0
                || depth != opaqueDepth) return false;
            vec3 sceneView;
            if (!waterTraceUnproject(pixel, depth, size, sceneView)) return false;
            float frontDepth = -sceneView.z;
            if (any(notEqual(pixel, sourcePixel)) && rayDepthMax >= frontDepth
                && rayDepthMin <= frontDepth + thickness) {
                // Solve the bounded depth slab against the ACTUAL 3D ray, then
                // confirm that the candidate belongs to this sampled screen cell.
                float firstT = max(minimumTravel, dot(segmentStart - originView, direction));
                float lastT = min(endTravel, dot(segmentEnd - originView, direction));
                float depthSlope = -direction.z;
                bool overlaps = lastT >= firstT;
                if (abs(depthSlope) > 1e-7) {
                    float a = (frontDepth + originView.z) / depthSlope;
                    float b = (frontDepth + thickness + originView.z) / depthSlope;
                    firstT = max(firstT, min(a, b));
                    lastT = min(lastT, max(a, b));
                    overlaps = overlaps && lastT >= firstT;
                } else {
                    overlaps = overlaps && -originView.z >= frontDepth && -originView.z <= frontDepth + thickness;
                }
                if (overlaps) {
                    vec3 candidate = originView + direction * firstT;
                    vec2 candidateScreen;
                    vec3 candidateQ;
                    float candidateK;
                    if (!waterTraceProject(candidate, size, candidateScreen, candidateQ, candidateK)) return false;
                    if (any(notEqual(ivec2(floor(candidateScreen)), pixel)) && lastT > firstT) {
                        // Negative traversal enters at an upper pixel boundary.
                        // Try just inside the SAME intersected interval, never
                        // outside its cell/depth slab or beyond the ray budget.
                        firstT = mix(firstT, lastT, 0.001);
                        candidate = originView + direction * firstT;
                        if (!waterTraceProject(candidate, size, candidateScreen, candidateQ, candidateK)) return false;
                    }
                    if (all(equal(ivec2(floor(candidateScreen)), pixel))) {
                        vec2 edge = min(candidateScreen, vec2(size) - candidateScreen);
                        float edgeWeight = smoothstep(0.0, 8.0, min(edge.x, edge.y));
                        float rangeWeight = 1.0 - smoothstep(48.0, 64.0, firstT);
                        float budgetWeight = 1.0 - smoothstep(float(stepLimit) * 0.75, float(stepLimit), float(stepsTaken));
                        float confidence = edgeWeight * rangeWeight * budgetWeight;
                        if (confidence > 0.0) {
                            hitPixel = pixel;
                            hitView = candidate;
                            hitRGB = payload.rgb;
                            hitDistance = firstT;
                            hitConfidence = confidence;
                            return true;
                        }
                    }
                }
            }
        }
        enterFraction = exitFraction;
        // No epsilon tie: a genuine corner advances both coordinates. Every
        // processed interval above the precision bound consumes one step.
        for (int axis = 0; axis < 2; ++axis) {
            if (crossings[axis] <= exitFraction) cell[axis] += stepDirection[axis];
        }
    }
    return false;
#endif
}
vec3 applyWaterScreenReflection(vec3 tinted, vec3 fallback, vec3 surfaceView,
                                vec3 originalNormalView, vec3 reflectedDirection, float localWeight) {
#if WATER_SCREEN_REFLECTIONS == 0
    return fallback;
#else
    if (localWeight <= 0.0) return fallback;
    // Small original-normal bias never displaces the water mesh or its depth.
    vec3 origin = surfaceView + originalNormalView * 0.01;
    ivec2 pixel;
    vec3 hitView, radiance;
    float distance, confidence;
    int steps;
    if (!traceWaterScene(origin, reflectedDirection, pixel, hitView, radiance, distance, confidence, steps)) return fallback;
    // Replace the fallback contribution; do not add a second Fresnel reflection.
    // Radiance is pre-camera-fog. Reflected-segment atmosphere is deferred to W4;
    // the existing late fog still applies exactly once from water to camera.
    return mix(fallback, mix(tinted, radiance, clamp(localWeight, 0.0, 1.0)), confidence);
#endif
}
#endif
