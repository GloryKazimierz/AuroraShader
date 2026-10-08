# Shadow Bias Study Guide — Milestone 6

For junior Graphics/Rendering Engineer interviews. M6 is experimental until the
user confirms Minecraft/Iris runtime testing. [中文学习版](SHADOW_BIAS_STUDY_GUIDE.zh-CN.md)

## 1. Depth Precision Refresher

A shadow map samples the nearest caster depth from the light. Rasterization,
finite storage precision, and receiver reconstruction introduce different errors.
Normalized depth is not a distance in Minecraft blocks; projection and depth range
affect its meaning. M6 keeps both unchanged.

## 2. Why Self-Shadowing Happens

The reconstructed receiver and selected shadow texel need not represent exactly
the same surface point. Even one physical surface can fail its own depth test.
Sampling mismatch and precision error both matter; this is not merely floating-point
rounding. [Microsoft's shadow-map artifact discussion](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/common-techniques-to-improve-shadow-depth-maps)

## 3. Constant Bias

M6 keeps `receiverDepth - bias <= storedDepth`: true means lit. For example,
`0.50003 - 0.0002 <= 0.50000` passes. Constant mode returns `SHADOW_BIAS` unchanged;
its default `0.0002` reproduces M5 comparison tolerance. One value cannot adapt to
every orientation, projection, or filter footprint.

## 4. Shadow Acne

False self-occlusion produces stripes, speckles, or dark patches. Confirm the depth
comparison and coordinate transforms before increasing tolerance. Increasing bias
can hide acne while introducing another error.

## 5. Peter-Panning

Excess tolerance rejects genuine occlusion near contact. The shadow appears
detached, making the caster look suspended. Inspect a pillar touching the ground:
clean ground alone is insufficient evidence of good bias.

## 6. Grazing Angles

When light travels nearly along a surface, a small displacement in shadow-map UV
can correspond to a large change in receiver depth. Nearby filter taps then test
different expected depths. A fixed tolerance may be too small there and too large
on a surface facing the light.

## 7. N dot L and Surface Orientation

Use normalized **view-space** receiver normal `N` and view-space direction toward
the celestial shadow light `L` from `shadowLightPosition`. Their dot product is
near one for facing surfaces and zero at grazing incidence. M6 clamps negative
values to zero; back-facing surfaces therefore receive maximum angle-aware bias.
Never mix world-space normals with view-space lights.

## 8. Angle-Aware Bias

For valid input directions, the exact model is:

```text
lo = clamp(min(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
hi = clamp(max(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
n = clamp(dot(normalize(N), normalize(L)), 0, 1)
bias = clamp(mix(lo, hi, 1 - n), lo, hi)
```

Defaults are `lo = 0.0001`, `hi = 0.0005`. Invalid/degenerate vectors use `n = 0`,
hence `hi`, without normalizing an invalid vector. Equal limits give a constant;
reversed limits are sorted. Constant mode bypasses this formula. This bounded
orientation heuristic does not measure actual depth error or guarantee better images.

## 9. True Slope-Scaled Raster Bias

Raster bias changes depth while rasterizing primitives. A common slope measure is
`max(abs(dz/dx), abs(dz/dy))` in raster/window coordinates; shadow-pass coordinates
belong to the light's projection. An API combines slope and constant terms, with
format/API-specific details. M6 measures no such derivative and changes only the
receiver comparison. These are distinct techniques. [Direct3D depth-bias definition](https://learn.microsoft.com/en-us/windows/win32/direct3d11/d3d10-graphics-programming-guide-output-merger-stage-depth-bias)

## 10. Normal Offset Bias

Normal offset moves the receiver position along its normal before projecting it
into the shadow map. It can change both UV and depth. M6 uses a normal only to
choose scalar tolerance: it does not displace geometry or lookup positions.
[Pettineo's implementation discussion](https://mynameismjp.wordpress.com/2013/09/10/shadow-maps/)

## 11. Receiver-Plane Depth Bias

Estimate local depth gradients in shadow-map coordinates, then predict a different
receiver depth at each tap: `zTap ≈ zCenter + dz/du * du + dz/dv * dv`.
This assumes local planarity; discontinuities and unstable derivatives need guards.
M6 does not implement it. [Microsoft's per-texel derivative method](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/cascaded-shadow-maps)

## 12. Bias with PCF

PCF averages binary visibility comparisons, not raw depths. Filtering erroneous
self-shadow tests cannot make those tests correct. M6 computes one receiver bias
and reuses it for every tap: Hard/3x3/5x5 use 1/9/25 comparisons on the active
filter path. Larger footprints can expose more receiver-depth variation.
[NVIDIA's PCF explanation](https://developer.nvidia.com/gpugems/gpugems/part-ii-lighting-and-shadows/chapter-11-shadow-map-antialiasing)

## 13. Bias with Poisson PCF

M6 retains eight fixed disk offsets and eight comparisons. Distribution changes
where comparisons occur, not their tolerance requirement. Each tap shares the same
bias. No random rotation or temporal filtering is added. Softness zero collapses
PCF positions to the center; Hard continues ignoring softness.

## 14. Thin Geometry Problems

Thin surfaces may occupy less than one texel or have little depth separation.
Large tolerance can erase their occlusion. Cutout coverage, missing casters, normal
orientation, and one-/two-sided geometry matter independently. M6 does not repair
those representations; do not silently flip normals or change caster scope.

## 15. Light Leaking

Bias can turn a real blocked comparison into lit visibility, allowing apparent
light through contacts or thin walls. Out-of-map samples are intentionally lit;
that boundary policy can also brighten edges. Distinguish these causes before tuning.

## 16. Debugging Checklist

1. Freeze scene, camera, time, projection, filter, and softness.
2. Compare Constant `0.0002` with Angle-Aware `0.0001–0.0005`.
3. Inspect normals, raw depth, visibility, and effective bias debug views.
4. Check contacts, grazing surfaces, leaves, thin objects, and map boundaries.
5. Repeat moving the camera; then check all four filters and softness zero.
6. Verify ambient/block lighting survives. Record artifacts, not assumed improvements.

Static structural/numerical checks cannot establish GPU compilation, runtime
stability, visual quality, or performance.

## 17. Interview Questions

1. **What causes acne?** Receiver and stored depths disagree for the same surface.
2. **Why does bias help?** It tolerates small errors in the visibility comparison.
3. **What is peter-panning?** Excess bias makes contact shadows detach.
4. **Why is constant bias imperfect?** Error changes with orientation and sampling.
5. **Why are grazing surfaces difficult?** Depth varies rapidly across shadow texels.
6. **What does N dot L measure?** Orientation relative to the light, using unit vectors.
7. **What is angle-aware bias?** A bounded normal-based receiver tolerance heuristic.
8. **Is it hardware slope bias?** No; it does not measure raster depth derivatives.
9. **What is slope-scaled depth bias?** Raster depth offset scaled by primitive depth slope.
10. **What is normal offset?** Moving the lookup position along the receiver normal.
11. **What is receiver-plane bias?** Predicting receiver depth separately for neighboring taps.
12. **Does PCF solve acne?** No; it filters potentially incorrect comparison results.
13. **Does Poisson solve bias?** No; sample distribution cannot correct depth tolerance.
14. **Why does excess bias leak light?** Genuine blockers can incorrectly pass as lit.
15. **How would you debug acne?** Verify spaces/depths, isolate bias, inspect contacts, then test motion.

## 18. One-Minute Explanation

Shadow mapping compares a receiver's depth with the nearest depth seen by a light.
Sampling and precision differences can make a surface shadow itself. Bias adds
tolerance, but too much detaches shadows or leaks light. M6 preserves constant
bias and adds a bounded heuristic using the angle between view-space normal and
light direction. Facing surfaces get less tolerance; grazing surfaces get more.
One value is shared across every PCF tap. This is neither hardware slope-scaled
raster bias nor per-tap receiver-plane correction. Filtering chooses where and how
many samples to take; bias controls how tolerant each comparison is. Runtime
testing must evaluate both acne and contact quality.
