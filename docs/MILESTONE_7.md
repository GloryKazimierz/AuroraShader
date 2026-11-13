# Milestone 7: Aurora day/night sky and celestial light color

Date: 2026-11-13. Branch: `codex/milestone-7-fantasy-sky`.
Based on M6 commit `5479a1c3b2b579e965cdb43681422abcb45b6b79`.
Minecraft/Iris runtime success is **not confirmed**. Development may continue
while this observation status remains open; see the [roadmap](AURORA_ROADMAP.md).
[中文学习版](MILESTONE_7.zh-CN.md).

## 1. What this stage changes

M7 establishes the first coordinated Aurora palette: azure days, coral/gold
near the rising or setting sun, violet twilight and indigo nights. It also adds
an independently controlled celestial tint to the existing surface lighting.
The intended result is expressive color with recognizable blocks and usable
nighttime silhouettes. This intent is not a measured image-quality result.

The sky background changes in `gbuffers_skybasic`. Its star branch still outputs
the original vertex color; `gbuffers_skytextured` remains responsible for the
unchanged sun/moon textures. Recorded opaque/cutout surfaces receive the new
palette in `deferred`, after the existing Lambert/lightmap modulation. Later
transparent geometry, water and vanilla clouds keep their existing shading. `final` retains the existing
color grading and Debug 0-6 paths.

The shadow projection, caster scope, depth comparisons, bias modes, filter tap
patterns and lightmap data layout are unchanged. There is no new aurora, bloom,
custom cloud system, volumetric light or geometry fog in this stage.

## 2. Shared implementation

| File under `shaders/` | Responsibility |
|---|---|
| `lib/atmosphere_settings.glsl` | Six user options |
| `lib/color_space.glsl` | Explicit sRGB decode/encode for the new local operations |
| `lib/celestial.glsl` | Safe directions, dimension/status gating and solar phases |
| `lib/sky_palette.glsl` | Bounded sky palette, horizon connection and rain blending |
| `lib/celestial_lighting.glsl` | Ambient/direct tint composition with local-light protection |
| `lib/geometry/sky_fragment.glsl` | Connect the palette to background sky rendering |
| `deferred.fsh` | Apply celestial color to valid recorded surfaces |

Shared functions keep the sky and surface palette on the same day/twilight
weights. They do not duplicate the shadow coordinate reconstruction.

## 3. Day and twilight follow geometry

All directions used here are in **VIEW space**. Let `S` be the normalized
`sunPosition`, `U` the normalized `upPosition`, and `R` the normalized view ray.
The implementation uses:

```text
e = clamp(dot(S, U), -1, 1)
day = smoothstep(-0.10, 0.16, e)
twilight = smoothstep(-0.18, -0.04, e)
         * (1 - smoothstep(0.08, 0.35, e))
height = clamp(dot(R, U), 0, 1)
horizon = (1 - height)^3
towardSun = max(dot(R, S), 0)
warmth = clamp(horizon * towardSun^4 * SUNSET_GLOW, 0, 1)
```

Camera rotation changes both vectors in each dot product in the same way, so it
should not change solar elevation or the sky's world-relative orientation.
No camera translation enters a direction calculation. Safe normalization first
scales by the largest absolute component. Non-finite or near-zero inputs use a
fixed upward fallback to avoid undefined normalization; that fallback is a
numerical safeguard, not a meaningful substitute for valid Iris uniforms.

`sunPosition` remains the sun at night. `shadowLightPosition` switches to the
moon for nighttime shadows and therefore cannot identify solar day/night phase.
The same elevation curves are used at dawn and dusk; this stage does not yet
have separate morning and evening palettes.
[Iris world uniforms](https://shaders.properties/current/reference/uniforms/world/),
[Iris view-space up direction](https://shaders.properties/current/reference/uniforms/camera/).

## 4. Palette interpolation and color space

The palette constants are authored as sRGB colors. Decode them, interpolate in
linear light, then encode the sky result back to sRGB. The new helpers use the
piecewise sRGB transfer functions, rather than the old grading approximation
`pow(color, 2.2)`:

```text
decode(c): c/12.92 for c < 0.04045;
           ((c + 0.055)/1.055)^2.4 otherwise
encode(l): 12.92*l for l < 0.0031308;
           1.055*l^(1/2.4) - 0.055 otherwise
```

Inputs to these helpers are clamped nonnegative. The shader selects the upper
branch at each threshold; the standard rounded constants have a negligible
rounding mismatch there. [sRGB transfer reference](https://www.w3.org/TR/css-color-4/#color-conversion-code).

Night, day and twilight each interpolate between a zenith and horizon color.
The night palette is multiplied by `NIGHT_BRIGHTNESS` in linear space. Twilight
adds a directional warm region by blending toward a gold swatch; this is a
broad sky gradient, not bloom or a replacement sun disc. The final sky is:

```text
sky = mix(mix(night, day, dayWeight), twilight, twilightWeight)
sky = mix(sky, linearVanillaFog, 0.22 * horizon^2)
overcast = linearVanillaFog * mix(0.4, 1.0, dayWeight)
sky = clamp(mix(sky, overcast, 0.85 * clamp(rainStrength, 0, 1)), 0, 1)
```

The modest fog-color connection preserves some biome/weather influence at the
horizon. It does **not** calculate fog on terrain or reconcile translucent
surfaces with distance. Geometry fog is a separate planned system.

These local operations do **not** make the renderer a full linear-light or HDR
pipeline. Scene storage, original lightmap multiplication and blending still
follow the M6 LDR path. Existing final grading can still clip strong highlights.
A later migration must audit every producer, blend and display conversion.

## 5. Surface light palette without recoloring every cave

First preserve the existing result `litScene = lightScene(...)`. Then compose
linear RGB tint multipliers from the shared phases. The scalar Lambert model
is not replaced, and the scene is already lightmapped rather than raw albedo.

```text
directAmount = DIRECT_LIGHT * diffuseTerm(normalView) * visibility
total = max(AMBIENT_LIGHT + directAmount, 0.000001)
tint = (AMBIENT_LIGHT * ambientTint + directAmount * directTint) / total
skyWeight = clamp(skyLight, 0, 1) * (1 - clamp(blockLight, 0, 1))
weight = clamp(LIGHT_PALETTE_STRENGTH * LIGHTING_STRENGTH * skyWeight, 0, 1)
       * environmentWeight
result = encode(decode(litScene) * mix(vec3(1), tint, weight))
```

Full shadow removes the direct **color contribution**, leaving the ambient
contribution. Zero skylight, full block light, zero strength or an excluded
environment returns the original result before a color-space round trip.
Partial block light smoothly reduces the tint. This is artistic modulation of
an existing scene, not independent physical relighting or colored shadow maps.

## 6. Options and fallbacks

Find the controls in the **Aurora Sky and Light** options screen (`ATMOSPHERE` internally).

| Option | Default | Allowed choices | Meaning |
|---|---:|---|---|
| `SKY_STYLE` | 1 | 0, 1 | Base-330 / Aurora |
| `SKY_BLEND` | 1.0 | 0, .25, .5, .75, 1 | Blend toward Aurora sky |
| `SUNSET_GLOW` | 1.0 | 0, .5, 1, 1.5 | Directional warm twilight gradient |
| `NIGHT_BRIGHTNESS` | 1.0 | .5, .75, 1, 1.5, 2 | Night sky only; not world exposure |
| `LIGHT_PALETTE` | 1 | 0, 1 | Neutral M6 / celestial surface tint |
| `LIGHT_PALETTE_STRENGTH` | .6 | 0, .25, .5, .6, .75, 1 | Surface palette strength |

For an M6 comparison, set **SKY_STYLE = 0 and LIGHT_PALETTE = 0** and keep all
old options identical. The zero-strength paths also provide baseline bypasses.

`hasSkylight && !hasCeiling` enables the new style in the Overworld and any
modded dimension with those properties. Nether/End-style dimensions fall back.
When the camera is in water, lava or powdered snow, new styling returns to the
baseline. Blindness/darkness fades it out using
`1 - clamp(max(blindness, darknessFactor), 0, 1)`. This is protection against
adding stylization during those states, not a new implementation of fluid fog
or status-effect rendering. Void sky blends the baseline toward the native vertex
color with the same continuous sky/environment weight; test it separately.
These dimension uniforms are Iris-specific, so OptiFine support is not claimed.
[Iris dimension uniforms](https://shaders.properties/current/reference/uniforms/biome/).

## 7. Validation and optional runtime observations

From the project root, run:

```text
python -B tools/validate.py
python -B tools/compile_glsl.py
```

The second command is optional and requires an installed `glslangValidator` on
PATH (or `--compiler PATH`). It downloads nothing. Its expanded sources use
compile-only render-stage placeholders; they do not run the Iris patcher.
Check the commit report for what actually ran. Structural
and numerical checks cannot establish Iris patcher behavior, GPU-driver behavior,
visual quality, performance, or complete Minecraft compatibility.

Use a disposable Overworld test scene with stone, wood, leaves, a cave entrance,
water and several torches. Fix camera position/yaw/pitch, FOV, resolution, render
distance, resource pack and all existing shadow/grading controls. Record the
versions of Minecraft, Iris, Sodium and the graphics driver. Freeze time/weather
when comparing settings, and restore the original game rules afterward.

Suggested times are 6000, 12000, 18000 and 23000. Also let time advance normally
through dawn/dusk. The numerical phase uses solar elevation, not a hardcoded
interpretation of those tick values.

| Comparison | What to observe | Actual result |
|---|---|---|
| Both new features off versus M6 | Baseline sky/surface lighting and Debug 0-6 | |
| Default M7 at all four times | Palette continuity, terrain readability, material identity | |
| Rotate/translate camera | Horizon stays level; warm region follows the sun | |
| Clear, rain, thunder and transitions | Continuous palette changes, no sudden daytime reset | |
| Stars, sun, moon and clouds | Original objects remain visible; no accidental recoloring path | |
| Cave, torch, mixed block/sky light | Local light protection and smooth partial influence | |
| Sky blend 0/1; palette strength 0/1 | Independent switches and bounded extremes | |
| Night brightness .5/2; sunset glow 0/1.5 | No non-finite output; assess clipping/banding | |
| Fluid camera, blindness, darkness | Baseline fallback; no fantasy sky leaking through effects | |
| Nether, End, open modded sky and void | Dimension gate and exceptional sky handling | |
| Both bias modes and four shadow filters | Shadow behavior unchanged by the palette integration | |

Leave unobserved results blank. This is a reusable observation sheet, not a new
manual approval gate for continued development. Report any actual Iris errors
or visual regressions when available.

## Recorded offline checks — 2026-11-13

- Full `python -B tools/validate.py`: passed, including the retained M1–M6 matrix.
- M7: 20,160 bounded sky cases, 20,001 phase samples, sRGB round trips,
  camera rotation invariance, protected lighting endpoints and continuous void blending passed.
- `python -B tools/compile_glsl.py`: 156 standalone program-pair compile/link
  configurations passed with installed glslangValidator, after the final sky correction.
- Full code review and whitespace checks passed. Runtime observation rows remain blank.

These results do not execute Minecraft, the Iris patcher, a GPU rendering workload,
  or a performance benchmark. The next planned stage is the scene color/HDR foundation
  described in the roadmap; pending runtime observations remain visible rather than
  becoming an approval gate.

## 8. Interview-sized explanations

1. **Why use solar elevation rather than world time?** Elevation directly relates
   the palette to the rendered sun direction and stays consistent with its path.
2. **Why is a view-space dot product camera-invariant?** A common rigid rotation
   preserves dot products. Mixing world-space and view-space vectors breaks this.
3. **Why not use the shadow light for phase?** It switches from sun to moon, so
   its altitude does not distinguish daytime from nighttime.
4. **Why decode sRGB before mixing colors?** Encoded values are nonlinear in
   light; linear interpolation then represents a mixture of light contributions.
5. **Does that make this HDR?** No. Dynamic range, scene storage, blending and
   final tone mapping are separate pipeline decisions still awaiting migration.
6. **How are torches protected?** The new tint is weighted by skylight and by
   one minus block-light level, with exact early exits at protected endpoints.
7. **Why can ambient remain visible in shadow?** Visibility multiplies the direct
   contribution. Ambient is composed independently and is not multiplied by it.
8. **Is the sky physically based atmospheric scattering?** No. It is an analytic
   artistic palette with geometric orientation and continuous interpolation.
9. **Is horizon color the same as fog?** No. Fog needs geometry distance and
   consistent compositing; changing a background color does not provide those.
10. **What remains unproven after compilation?** Runtime integration, appearance,
    temporal stability and performance require the relevant execution/measurement.

## Primary references

- [Iris gbuffers responsibilities](https://shaders.properties/current/reference/programs/gbuffers/)
- [Iris render-stage identifiers](https://shaders.properties/current/reference/macros/render_stages/)
- [Iris sun, moon and weather uniforms](https://shaders.properties/current/reference/uniforms/world/)
- [Iris player-status uniforms](https://shaders.properties/current/reference/uniforms/status/)
- [Next development priorities](AURORA_ROADMAP.md)
