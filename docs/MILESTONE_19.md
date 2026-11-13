# Milestone 19: Warm sun and cool moon sky glow

Date: 2026-11-13. Branch: `codex/milestone-19-celestial-glow`.
Base: M18 commit `60871f45b7e84e331bacaf541874c7ae4df86090`.
[中文学习版](MILESTONE_19.zh-CN.md).

M19 adds a warm halo around the sun and a quieter blue halo around the moon, only
in the sky background. The original textured discs remain separate. This is an
artistic sky effect, not new terrain illumination or physical atmospheric scattering.
The defaults have not yet been judged in Minecraft/Iris.

## 1. Controls and pipeline position

The existing **Aurora Sky and Light** page gains:

| Option | Default | Allowed values |
|---|---|---|
| `CELESTIAL_GLOW` | 1 | 0: Off, 1: On |
| `SUN_GLOW_STRENGTH` | 0.4 | 0, 0.2, 0.4, 0.6, 1 |
| `MOON_GLOW_STRENGTH` | 0.15 | 0, 0.05, 0.15, 0.3, 0.5 |

A zero strength disables only that body's glow. Off or both strengths zero restores
the M18 sky input exactly. The feature requires linear HDR mode, Aurora Sky style,
normal rendering and a positive Sky Blend/environment weight.

`applyCelestialGlow(rayView, scene)` runs only for `MC_RENDER_STAGE_SKY`:

```text
existing sky palette -> celestial glow -> existing night aurora -> scene color
existing sun / moon / star draws retain their own rendering paths
scene composition -> existing bloom -> exposure / tone mapping / display output
```

No pass, attachment or sampler is added. Alpha, native disc textures, star rendering,
void/sunset stages, shared fog palette, cloud source and water-reflection palette
are unchanged. Existing bloom may spread sufficiently bright rendered sky pixels;
it is still a separate image-processing feature.
[Iris stage hooks](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/mixin/MixinSkyRenderer.java).

There are now 57 controls and 179 keys per language. The three new controls are
outside the unchanged seven-setting quality profiles; selecting a profile preserves
them along with the other 47 unprofiled controls, for 50 retained values in total.

## 2. Why an angular halo follows the sky

Let `r` be the normalized view ray and `b` a normalized celestial direction.
Their dot product is `cos(theta)`, where `theta` is angular separation:

```text
c = clamp(dot(r, b), -1, 1)
A(c) = 0.75 * exp(-(1 - c) / 0.012)
     + 0.25 * exp(-(1 - c) / 0.08)
```

The narrow part forms a brighter center; the broad part supplies a gentle outer
halo. Both decay smoothly away from the body. No inverse cosine is needed.
The lobe equals 1 at its center and stays in [0, 1].

Its angular width is fixed in sky directions. Its pixel footprint changes naturally
with field of view and image resolution; it is not a fixed-radius screen-space
circle. Rotating the camera rotates both directions together, preserving their
dot product. This differs from bloom, which blurs an already rendered image.

The shader uses `sunPosition` and `moonPosition` independently, in their supplied
view space. It neither negates the sun vector to invent the moon nor uses
`shadowLightPosition`, which selects the current shadow-casting body.
[Iris world uniforms](https://shaders.properties/current/reference/uniforms/world/).

The pinned Iris implementation samples separate `SUN_ANGLE` and `MOON_ANGLE`
environment attributes. Keeping separate directions also avoids assuming every
supported sky has diametrically opposed bodies.
[Celestial implementation](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/uniforms/CelestialUniforms.java).

## 3. Horizon, rain and lunar phase

With normalized up direction `u`, the weights are:

```text
rayHorizon = smoothstep(-0.025, 0.04, dot(r, u))
bodyHorizon = smoothstep(-0.08, 0.04, dot(b, u))
dry = 1 - clamp(rainStrength, 0, 1)
common = clamp(SKY_BLEND, 0, 1) * environment * dry^2 * rayHorizon
sunAdd = common * sunStrength * sunHorizon * A(dot(r, sun)) * (1, 0.62, 0.28)
moonAdd = common * moonStrength * moonHorizon * A(dot(r, moon))
          * moonPhaseWeight * (0.24, 0.38, 1)
result = scene + sunAdd + moonAdd
```

Each body's own elevation controls its horizon fade. There is no sun-derived
night switch for the moon. Rain smoothly reduces both glows to zero at full rain.
The existing environment guard suppresses the feature in ceiling/non-skylit
dimensions, fluid-camera views and strong blindness/darkness conditions.

`moonPhase` is an integer from 0 to 7; 0 denotes full moon and 4 new moon.
[Iris phase contract](https://shaders.properties/current/reference/uniforms/world/#moonphase),
[phase binding](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/uniforms/WorldTimeUniforms.java).

M19 uses the artistic curve `P = (1 + cos(2*pi*phase/8)) / 2`, with exact full/new
endpoints:

| Phase | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| Weight | 1 | 0.853553 | 0.5 | 0.146447 | 0 | 0.146447 | 0.5 | 0.853553 |

This is a glow brightness choice, not Minecraft's light-level table, a reconstruction
of the moon texture, or a physical lunar illumination calculation. It does not
change the phase image or terrain moonlight, and does not interpolate between phase IDs.

## 4. Bounds and fallbacks

Both color vectors have nonnegative components at most 1. With lobe/gates at most 1,
sun strength at most 1 and moon strength at most 0.5, each added RGB component is
bounded by 1.5. Default strengths give the conservative bound 0.55.
These are bounds on added scene-linear color, not display brightness measurements.

Required directions are checked before normalization, with scaling to avoid overflow.
The new helper returns the original scene for invalid required runtime inputs or an output
that would be negative, nonfinite or exceed the finite half-float limit 65504.
It does not repair a pre-existing invalid scene.

An invalid sun direction suppresses only the sun; an invalid moon direction or phase
suppresses only the moon. This isolates independent inputs. Off, both strengths zero,
legacy mode, debug, Base-330 sky, zero Sky Blend or zero environment contribution
keep the incoming scene exactly. A below-horizon contribution also vanishes without
changing the other body.

The warm/cool RGB values and horizon fades are artistic choices. There is no
atmospheric density integration, volumetric shadow, lens ghost, terrain light source
or new reflection of the celestial discs. Cost is additional sky-fragment arithmetic;
no measured FPS result is claimed.

## 5. Source map and runtime worksheet

`lib/celestial_glow.glsl` and `lib/celestial_glow_settings.glsl` isolate the formula
and controls; `lib/geometry/sky_fragment.glsl` supplies the single stage-limited call. Settings layout and eight new
EN/ZH language keys expose it. Historical notes and all existing language values
remain unchanged. Primary Iris implementation links use commit
`99d855970316329f2e0e42ac2b79ef763cb77cc3`; they do not verify the active game installation.

| Controlled observation | Actual result |
|---|---|
| Off / both strengths zero match M18 sky; individual strengths isolate bodies | |
| Halo follows each native disc while camera rotates and time changes | |
| FOV/resolution changes retain angular shape, with changing pixel footprint | |
| Sunrise/sunset and both horizon fades remain smooth | |
| All eight phases: full strongest, new no added moon halo; native texture retained | |
| Rain, blindness/darkness, fluid views and non-skylit dimensions fall back correctly | |
| Stars, cloud overlap, aurora and bloom retain readable silhouettes | |
| Sky glow does not appear in fog/water palette or change terrain illumination | |
| Profiles preserve glow strengths; EN/ZH labels fit the menu | |

The blank results require Minecraft/Iris observation; they are not implied by formula
or compiler checks. Recorded automated checks are listed separately below.

## 6. Learning questions

1. **Why use a dot product?** Normalized directions provide angular separation without projection or inverse cosine.
2. **Why two lobes?** A compact center and broad tail can be tuned independently in one bounded shape.
3. **Why independent celestial vectors?** Shadow selection and a negated sun do not represent both supplied sky bodies.
4. **Why does zoom change apparent size?** A fixed sky angle occupies a different screen area under a different projection.
5. **Why not add the glow to fog?** It is a sky-background treatment, not a shared physical scattering model.
6. **Why preserve native discs?** Their textures and phase silhouettes already have separate rendering paths.
7. **Why exact bypasses?** Turning the feature off provides a reliable M18 comparison.
8. **What does a driver fixture prove?** Numerical execution of supplied inputs, not Iris bindings, draw ordering or a real world.

## 7. Executed native checks

The [M19 celestial GPU report](validation/M19_GPU_celestial.json) passed on Intel
Iris Xe, OpenGL 3.3 compatibility, driver 31.0.101.3962, with an unchanged shader
digest during the run.

- **40 helper fixtures / 840 samples:** independent bodies, phase, direction scaling,
  rotation, horizon/environment gates, invalid inputs and half-float limits.
  The 577 bypass checks retain exact finite channels/alpha; the 80 nonfinite-source
  samples preserve their NaN/infinity classifications. Maximum finite RGB error:
  approximately `3.934e-6` in scene-linear units.
- **13 actual sky-program branch fixtures / 273 samples:** 259 unaffected pixels
  match the glow-off baseline exactly; 14 eligible pixels change. Maximum RGB error:
  approximately `2.086e-7`. Alpha remains exact.

Active comparisons use `1e-5 + 1e-7 * abs(expected)` tolerance. Near alignment 1,
the lobe slope is 65.625: one downward FP32 step of `2^-24` changes its value by
about `3.912e-6`. This motivated a fixture tolerance adjustment, not a shader
correction or a universal bound on driver error. Bypass and alpha checks remain
exact; nonfinite values retain their required classifications.

The sky fixtures use synthetic rays/uniforms and compile-only stage placeholders,
not verified Iris enum values. They do not establish native disc rendering, Iris
bindings/order, real sky geometry, Minecraft appearance or performance.
The [full native compilation report](validation/M19_GPU_compile.json) passed all
**1,610 program/option configurations across 24 program pairs** on the same driver.
Its shader digest matches the celestial fixture report exactly. These expanded
programs do not include Iris runtime transformations. The unmodified full historical/
CPU validator passed through M19; all **1,610 offline compile/link configurations**
and syntax/whitespace checks passed. Focused checks account for intended M19 changes
while verifying **97 prior files**, and cover **17,280 bounded color cases, 2,049
monotone angular samples and 24 shared-frame rotations**, alongside independent-body,
phase, environment and finite-HDR fallback checks.

```powershell
python -B tools/validate_gpu.py --cxx C:/msys64/ucrt64/bin/g++.exe --suite celestial --report docs/validation/NEW_CELESTIAL_RUN.json
```

Use a new report name; existing reports are not overwritten.
Water-transparency composition remains a separate research item.
[Roadmap](AURORA_ROADMAP.md).
