# Water 02: Filtered multiscale water normals

Date: 2026-11-21. Branch: `codex/water-02-filtered-waves`.
Base: W1 commit `5d3e91761beaa3747052c11aa429e27be8d42df4`.
[中文学习版](WATER_02_FILTERED_WAVES.zh-CN.md) · [Water roadmap](WATER_ROADMAP.md).

W2 adds finer normal detail to the broad M14 wave pattern and reduces individual
waves when a pixel cannot resolve them. W2 is implemented; CPU, offline compilation
and native W2 checks passed. The historical native depth regression also passed.
No runtime appearance, performance or Minecraft/Iris pass is claimed.

## 1. Scope and control

| Setting | Behavior |
|---|---|
| `WATER_SURFACE_DETAIL=1` (default) | Three broad waves plus three fine ripples, all filtered by their projected pixel footprint |
| `WATER_SURFACE_DETAIL=0` | Original M14 three-wave path, without the new filtering; a comparison/fallback mode |
| `WATER_WAVES=0` or wave strength 0 | Original unperturbed reflection normal |
| Wave speed 0 / 1 / 2 | Static spatial pattern / normal / double motion, as before |

The new toggle is **Fine Water Ripples**, immediately after Water Reflection Waves.
Profiles retain their seven existing controls; this setting is not a new profile
control or slider. Light still disables Water Reflection Waves, making detail inactive.

This changes reflection normals only. Geometry, shoreline silhouettes, alpha,
depth color and the analytic sky reflection source retain their existing roles.
There is no physical current, flow field, waterfall model, refraction, roughness
model or new reflection algorithm. W1 snapshots remain without a water consumer.
Existing sky, fluid-camera and upward-face gates still apply.

## 2. Why two wave scales

The original broad waves supply slow coherent shape; fine ripples add surface
variation without raising their conceptual height to the broad-wave amplitudes.
The parameters are authored periodic signals, not a measured water spectrum or
fluid simulation. Normal detail and mesh displacement are different sampling
problems. [Wave-model reference](https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-1-effective-water-simulation-physical-models).

| New ripple | Integer direction on 128-block tile | Conceptual amplitude (blocks) | Wavelength (blocks) | Temporal harmonic / 200 s |
|---|---|---:|---:|---:|
| 1 | `(49,19)` | 0.006 | 2.435556 | 24 |
| 2 | `(-83,31)` | 0.0035 | 1.444692 | -31 |
| 3 | `(151,97)` | 0.0015 | 0.713205 | 43 |

Conceptual height is used only to derive slope; no vertex receives these heights.
The original `water_waves.glsl` and `water_wave_settings.glsl` remain unchanged.
The detail-off path calls that original helper; the new helper reproduces its three
broad modes and adds the three ripples. Their original amplitudes, directions and
time harmonics remain the same.
Integer spatial/time harmonics preserve the existing 128-block spatial period and
200-second normal-speed cycle; sampled finite-precision continuity results are
recorded below rather than assumed exact.
Travel direction comes from the phase sign, not from sampled Minecraft fluid flow.

The unfiltered six-wave slope bound is approximately 0.11857748. For horizontal
water under a rigid view transform and full eligibility, the default strength 0.6
therefore bounds normal tilt by about 4.06954 degrees, versus M14's 2.56498 degrees.
At full strength the six-wave bound is approximately 6.76241 degrees.
These are mathematical upper bounds, not measured typical motion or visual quality.
This is a restrained first parameter set; at grazing views, even modest normal
changes can move a reflection noticeably. Runtime composition still determines visibility.

## 3. Filtering each wave across a pixel

Let `p` be continuous world-aligned horizontal position in blocks and `q` a wave's
integer tile direction. Its spatial frequency is `q/128` cycles per block.
Estimate `dx=dFdx(p)` and `dy=dFdy(p)`, then project them onto this wave:

```text
fx = dot(q/128, dx)       // cycles per screen pixel in x
fy = dot(q/128, dy)       // cycles per screen pixel in y
sinc(x) = sin(x)/x, with sinc(0)=1
boxWeight = sinc(pi*fx) * sinc(pi*fy)
frequency = max(abs(fx), abs(fy))
nyquistWeight = 1 - smoothstep(0.25, 0.5, frequency)
filteredSlope = originalSlope * boxWeight * nyquistWeight
```

For an affine phase over a unit pixel box, the sinc product is the exact average
of that cosine component. Real perspective mapping is only locally approximated
as affine. The additional 0.25-to-0.5 taper is a deliberate anti-aliasing policy,
not part of the exact integral: box averaging alone does not remove all frequencies
that the pixel grid cannot represent. Each projected axis reaches the half-cycle
limit at 0.5 cycles/pixel. [Sampling theory](https://pbr-book.org/4ed/Sampling_and_Reconstruction/Sampling_Theory).

The shader approximates each sinc using an even degree-10 polynomial evaluated
in Horner form. The cutoff first restricts its arguments to `|x| < pi/2`; the
alternating-series remainder is below `3.63e-8` before floating-point rounding.
This approximates the exact box formula above; it is not exact GPU arithmetic.
During development, direct `sin(x)/x` on Intel produced about `3.72e-6` error at
0.01 cycles/pixel. The polynomial avoids that observed near-zero trigonometric
issue. The independent CPU reference still uses exact `sin(x)/x`, so it does not
merely repeat the shader approximation. Final native filter results are below.

Filter weights depend on both screen directions rather than camera distance alone.
An oblique pixel can cover a long strip of water; fine ripples may need suppression
there even when the nearby surface is close to the camera. Broad waves survive
longer because their projected frequencies are lower. This is a first-order footprint
estimate, with limitations at silhouettes, discontinuities and strong perspective
variation. [Surface-footprint reference](https://www.pbr-book.org/4ed/Textures_and_Materials/Texture_Sampling_and_Antialiasing).

## 4. Derivatives before wrapping and discard

The water fragment path reconstructs a continuous view position and transforms
its `dFdx`/`dFdy` vectors into world XZ before alpha discard and per-material
eligibility branches. Filtering consumes those derivatives later. A marker defined
only in this water/detail path lets late fog reuse the reconstructed position.
Nonfinite or extreme footprints (a component over 65,536 blocks/pixel) return the
unperturbed normal rather than invent a zero-footprint sample.
Derivatives must use continuous coordinates; applying `fract` first would turn a
128-block tile boundary into a false large footprint and a visible detail stripe.
Wrapping belongs only to periodic phase evaluation. The existing small camera
anchor keeps phase arithmetic useful far from the origin.

GLSL derivatives assume a continuous expression and may be undefined in nonuniform
control flow. Computing them before divergent decisions avoids that specific
hazard; it does not prove every geometry edge or driver path is artifact-free.
[Khronos derivative reference](https://raw.githubusercontent.com/KhronosGroup/OpenGL-Refpages/main/gl4/dFdx.xml).

Filtering slopes is not complete reflection antialiasing. Normalization, Fresnel,
reflection lookup and future sharp lighting are nonlinear. Removed small-wave
variance is not yet converted into roughness, so distant water can become too
mirror-like. No temporal filtering or motion-blur solution is introduced here.

## 5. Files and validation status

| File | Responsibility |
|---|---|
| [`water_surface_settings.glsl`](../shaders/lib/water_surface_settings.glsl) | New default-on binary detail option |
| [`water_filtered_waves.glsl`](../shaders/lib/water_filtered_waves.glsl) | Six-wave detail path, polynomial sinc/footprint weights and call to original-wave fallback |
| [`water_waves.glsl`](../shaders/lib/water_waves.glsl), [`water_wave_settings.glsl`](../shaders/lib/water_wave_settings.glsl) | Unchanged original M14 helper and controls |
| [`lit_fragment.glsl`](../shaders/lib/geometry/lit_fragment.glsl) | Obtain continuous-coordinate derivatives before discard in the water path |
| [`water.glsl`](../shaders/lib/water.glsl) | Pass the footprint into the existing normal/reflection path |
| [`shaders.properties`](../shaders/shaders.properties), language files | Menu toggle and English/Chinese explanations; profiles unchanged |

| Evidence layer | Status |
|---|---|
| CPU math, historical preservation and settings checks | Full M1–M19, W1 and W2 checks passed |
| Standalone program-pair compilation | All 1,726 configurations passed |
| Native driver compilation and synthetic footprint/normal output | All 1,726 compilations and the W2 synthetic suite passed |
| Historical native depth-color regression | Passed on the same frozen shader source |
| Minecraft/Iris integration and actual water appearance | Unobserved |
| In-game GPU time and image-quality cost | Unmeasured |

No new pass, buffer or scene sampler is added. Six-wave evaluation and derivative
arithmetic have a cost; filtering high frequencies does not by itself prove faster
rendering. Runtime results must not be inferred from a synthetic image or CPU bound.

### CPU and historical preservation

The full [validator](../tools/validate.py) exited 0. The
[W2 checks](../tools/validate_water_filtered_waves.py) included 24 independent
96×96 midpoint pixel-box integrations (maximum slope error `2.13085e-7`),
648 spatial/time seam checks and 144 bounded-normal cases, plus nonuniform
normal transforms and large camera anchors. The sampled float32 clock-wrap slope
delta was at most `0.000101898`; this is not a zero-error temporal guarantee.

All 100 W1 shader/property/language files matched their pinned baseline after
exact W2 plumbing/menu/label restoration in memory; the two new GLSL helpers are
separate. UI checks cover 58 controls, 12 screens and 183 unique keys per language.
Profiles still control seven settings and preserve the other 51.
Whitespace checks passed.

### Offline and native compilation

All 1,726 standalone compile/link configurations passed. The
[native compilation report](validation/W2_GPU_compile.json) also passed all 1,726
expanded program-pair configurations on Intel Iris Xe, OpenGL 3.3 compatibility.
Fixtures use the actual listed floating-point strength token `1.0`; an integer
`1` is not a listed strength setting. Neither compiler route applies Iris transforms.

### Native filtering, derivatives and fragment composition

[Native W2 report](validation/W2_GPU_filtered_waves.json):

| Check | Observed synthetic result |
|---|---|
| 40 filter samples | Maximum absolute error `5.573874828e-8`, within `4e-7` |
| 29 normal cases, 3,440 surviving samples | Maximum absolute error `6.21128935e-7`, within `6e-5` |
| Bypass paths | 480 exact samples |
| Derivative output comparisons | 960 exact outputs, including expected discard sentinels |
| Near-detail normal fixture | All 120 of 120 normals changed |
| Actual pack fragment, 4 configurations × 120 pixels | Original/detail-off, waves-off and zero-strength outputs matched W1 exactly; detail changed 48 RGB pixels, with exact alpha/discard preservation |

Both native reports share shader SHA-256
`7ab9456b47b812ca97b15e2b6858e03cbfe96c6d31a6f8921c7597f89619dd1e`.
The derivative/normal fixtures use dyadic affine fields, including elongated
footprints representing a grazing sampling condition. They are **not a perspective
water plane or Minecraft rasterization**. The fragment check uses actual pack
fragment source with synthetic vertex/material/atlas inputs. These results establish
the stated comparisons, not real-world shimmer reduction or a GPU-time benefit.
The [historical native depth regression](validation/W2_GPU_depth_regression.json)
also passed: 40 cases, 840 color samples and 767 exact bypass pixels, with the same shader digest. This separate depth suite uses synthetic perspective positions; it performs no Minecraft draws or blending.

## 6. Observation sheet

Keep world/time/weather, texture pack, settings and resolution fixed while comparing.
Empty observed-result cells mean unobserved, not passed. The broader
[water scene matrix](WATER_ROADMAP.md#controlled-observation-matrix) remains applicable.

| View or comparison | What to judge | Observed result |
|---|---|---|
| Overhead shallow pool, detail off/on | Fine variation without obscuring the readable bottom | |
| 30/60/80 degrees from surface normal | Coherent reflections; graceful grazing suppression | |
| Near-to-horizon lake and camera dolly | Fine detail fades before unstable distant stripes/shimmer | |
| Camera rotation, FOV and resolution changes | Footprint follows projection without abrupt detail bands | |
| Positive/negative 128-block boundaries, far coordinates | No filtering seam caused by coordinate wrapping | |
| Static, normal, double speed; clock wrap | Motion changes without pattern jumps or camera swimming | |
| Waves off, strength zero, detail off | Clearly distinguish unperturbed, original and filtered paths | |
| Shore, waterlogged block, glass overlap, waterfall | Original coverage and eligibility remain; no invented flow | |
| Sun, sunset, moon, rain, cave, underwater | Existing scope respected; visible improvement recorded honestly | |
| Matched GPU timing | Record hardware/resolution/settings before a performance conclusion | |

Next is W3: bounded screen-space ray-traced reflection with hit confidence and
environment fallback, using W1 inputs and the surface normal contract. W2 itself
does not trace rays or solve missing off-screen scene information.
