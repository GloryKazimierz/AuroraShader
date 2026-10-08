# Milestone 6: Shadow Bias Robustness

Status: experimental implementation on `milestone-6-shadow-bias`, based on the
latest Milestone 5 state. Minecraft/Iris runtime testing is **not confirmed**.
This branch is not merged into `main`.

Read the [study guide](SHADOW_BIAS_STUDY_GUIDE.md) for interview preparation and
the [test sheet](MILESTONE_6_BENCHMARK.md) for controlled comparisons.
[中文学习版](MILESTONE_6.zh-CN.md).

## 1. The problem: an imperfect comparison

A shadow map records depth from the light. A receiver is lit when its projected
depth is no farther away than the stored depth. Finite depth precision,
rasterization, reconstruction, and differences between camera pixels and shadow
texel positions mean the two depths need not agree perfectly on the same surface.
An ideal mathematical surface can therefore incorrectly shadow itself.

This **shadow acne** appears as dark speckles, bands, or repeating patterns. A
small tolerance can make these nearly equal depths count as equal. But excessive
tolerance hides real occlusion: contact shadows detach, producing **peter-panning**;
thin blockers can lose shadows and light can leak through geometry. The purpose
of this milestone is to study that trade-off, not promise artifact-free shadows.
[Microsoft's shadow-map artifact overview](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/common-techniques-to-improve-shadow-depth-maps).

## 2. Two strategies and their defaults

| Option | Default | Meaning |
|---|---:|---|
| `SHADOW_BIAS_MODE` | `0` | `0` Constant; `1` Angle-Aware |
| `SHADOW_BIAS` | `0.0002` | Legacy constant normalized-depth tolerance |
| `SHADOW_BIAS_MIN` | `0.0001` | Lower angle-aware endpoint |
| `SHADOW_BIAS_MAX` | `0.0005` | Upper angle-aware endpoint |

The three numeric options offer `0`, `0.00005`, `0.0001`, `0.0002`, `0.0005`,
`0.001`, and `0.002`. They are normalized shadow-depth values, not world meters.
The filter default remains 3x3 PCF; softness remains `1.0`.

Constant mode returns `SHADOW_BIAS` unchanged. In particular, `0.0002` preserves
the Milestone 5 comparison behavior. It ignores the angle-aware endpoints and
normal/light inputs. One constant is simple and reproducible, but the best
compromise varies with surface orientation, projection, resolution, and scene.

## 3. Exact angle-aware formula

For finite configured endpoint values:

```text
lo = clamp(min(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
hi = clamp(max(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
NdotL = clamp(dot(safeNormalView, safeLightDirectionView), 0, 1)
angleFactor = 1 - NdotL
effectiveBias = clamp(mix(lo, hi, angleFactor), lo, hi)
lit = receiverDepth - effectiveBias <= storedDepth
```

Reversed endpoints are sorted. Equal endpoints give a constant angle-aware bias.
Both input vectors are checked for NaN/infinity and for a maximum absolute
component no greater than `1e-6`. An invalid/degenerate input selects `NdotL = 0`,
giving the maximum bias. Otherwise each vector is divided by its maximum absolute
component before normalization; this avoids length-squared overflow for large
finite inputs. The dot product and result are explicitly clamped.

With the defaults, representative results are:

| N dot L | 1.00 | 0.75 | 0.50 | 0.25 | 0.00 |
|---|---:|---:|---:|---:|---:|
| Effective bias | 0.0001 | 0.0002 | 0.0003 | 0.0004 | 0.0005 |

A directly facing surface gets the minimum. Grazing and back-facing surfaces get
the maximum after clamping. The motivation is that grazing surfaces can have a
large light-depth change across a small shadow-texel displacement. N dot L is a
bounded orientation proxy; it does not measure the actual error.

## 4. Coordinate spaces and implementation boundary

The decoded G-buffer normal is in **camera view space**. The light input is Iris
`shadowLightPosition`, also in view space, pointing toward the active celestial
shadow source (sun by day, moon by night). Both are normalized as directions; no
camera translation is added. [Iris uniform reference](https://shaders.properties/current/reference/uniforms/overview/).

The receiver depth and stored depth being compared are normalized **shadow-map
depths**. Using view space to compute the angle does not change those depths.
Camera-depth reconstruction, player-relative conversion, `shadowModelView`, and
`shadowProjection` retain the tested position path. Bias changes only the
comparison tolerance, not positions, projection, or shadow-map generation.

## 5. A heuristic, not API slope-scaled raster bias

True raster slope-scaled bias commonly depends on a primitive's depth gradient
over raster coordinates. For example, Direct3D combines a format-dependent
constant term with a factor times the maximum horizontal/vertical depth slope.
That adjusts depth during rasterization. This milestone instead subtracts a
bounded, normal/light-based tolerance while evaluating the **receiver**.
[Direct3D depth-bias definition](https://learn.microsoft.com/en-us/windows/win32/direct3d11/d3d10-graphics-programming-guide-output-merger-stage-depth-bias).

The two approaches share a motivation but are not equivalent. This implementation
does not use primitive depth derivatives, shadow-map texel footprint, or API
polygon-offset state. Shading normals can also differ from geometric normals,
weakening the orientation proxy. It is an educational heuristic, not a physical
model or a guarantee of improved quality.

## 6. Bias and filtering remain separate

One effective bias is computed per receiver and reused for every filter tap.
Hard/3x3/5x5/Poisson retain **1/9/25/8** comparisons, respectively, with their
existing sample positions and softness behavior. PCF averages binary visibility
results, never raw depths. Out-of-map samples remain lit; softness zero still
matches the center comparison and Hard still ignores softness.

Filtering changes where/how many comparisons are made. Bias changes how much
error each comparison tolerates. PCF can smooth an erroneous edge without fixing
self-shadowing. Poisson distribution likewise cannot repair a wrong comparison.
Wider kernels can compare samples farther from the receiver center, making one
shared tolerance less adequate on a tilted plane.

Caster scope, `shadowtex1`, ambient lighting, block-light protection, and
direct-light-only shadowing are unchanged. Debug 0-5 keep their meanings; their
images naturally respond to the selected bias where they show shadow visibility.
Constant mode is the regression baseline.

## 7. Debug 6: Effective Shadow Bias

Debug 6 is ungraded grayscale: `clamp((effectiveBias - lo) / (hi - lo), 0, 1)`.
A span no greater than 1e-8 (including equal bounds) outputs black, avoiding division by zero. Sky/background and invalid
receiver pixels output black using camera depth and the G-buffer validity flag.
A receiver marked valid but carrying a degenerate normal uses the maximum in
Angle-Aware mode. Constant `0.0002` with default bounds produces gray `0.25`.

This is a preview of the potential receiver bias, including when shadows are
disabled or the receiver lies outside shadow-map coverage. It is not a map of
shadow visibility, error magnitude, or actual shadow contribution.

## 8. Validation and first runtime test

Run `python -B tools/validate.py` and whitespace checks. Structural/numerical
checks cover option paths, old filter counts, constant equivalence, angle
monotonicity/bounds, degenerate vectors, debug normalization, and preserved
transforms/lighting. They do **not** prove GLSL driver compilation, Minecraft/Iris
runtime behavior, visual improvement, or performance.

Load this worktree deliberately: `D:\MinecraftShaders\MyShader-pcf-kernels`.
The existing `MyShader` junction points at the separate sky experiment; this
milestone does not repoint it. Follow the test sheet's loading procedure.

Start at 3x3 PCF, softness `1.0`, Constant `0.0002`; then change only to Angle-Aware
`0.0001`-`0.0005`. Compare flat ground, grazing surfaces, pillar contact, thin
geometry, and leaves from identical cameras. Move/rotate afterward, then repeat
with Hard, 5x5, and Poisson. Record acne, contact gaps, leaks, and shimmer rather
than inventing a single quality score.

## 9. Limits, next experiment, and interview explanation

Maximum bias can still detach contacts and erase thin shadows. The model lacks
per-tap plane correction, resolution adaptation, and geometric thickness; it
does not cure aliasing or temporal instability. No performance gain is claimed.

After runtime testing, a focused Milestone 7 could compare **receiver-plane depth
bias**: estimate local depth variation and adjust each tap's receiver depth.
Plane assumptions and derivative discontinuities would need safeguards. This is
only a proposal; no receiver-plane correction, PCSS, cascades, or temporal
filtering is implemented. [Microsoft's per-texel depth-bias discussion](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/cascaded-shadow-maps).

Interview explanation: “I preserved all filter patterns and changed only
comparison tolerance. Constant bias reproduces the baseline; angle-aware bias
interpolates bounded tolerance using view-space N dot L. It may help grazing
surfaces but can worsen contact separation. It is a receiver-side heuristic,
not hardware slope-scaled raster bias. I validate compatibility numerically and
compare artifacts in a controlled runtime scene.”

## Development checks performed

- `python -B tools/validate.py`: structural/numerical checks passed for both bias
  modes, four filters, seven debug modes, five softness values and prior invariants.
- Standalone `glslangValidator`: 139 program-pair compile/link configurations passed,
  including every bias/filter/debug path in deferred/final and all 19 default pairs.
  Includes were expanded; the Iris star render-stage macro used a compile-only
  stand-in. This checks GLSL 330 syntax/interfaces, not Iris patching or GPU execution.
- Runtime screenshots, artifact observations and benchmark results remain pending.
