# Milestone 16: Water color from a background-depth gap

Date: 2026-11-13. Branch: `codex/milestone-16-water-depth-color`.
Base: M15 commit `bc811801441709143cbb2ef33a2db3dadc597ee7`.
[中文学习版](MILESTONE_16.zh-CN.md).

M16 adds a gentle depth-related teal shift to classified water's **source RGB**.
It preserves native alpha, geometry, depth, blend state and the existing fog sequence.
Minecraft/Iris appearance remains unobserved; executed checks are recorded separately.

## 1. The depth snapshot is a background hint

The new input is `depthtex2`, sampled at the water fragment's own screen pixel.
In the inspected Iris source, `beginHand` copies this depth before the solid hand;
the later main-translucency transition copies `depthtex1` and runs deferred.
The world sampler setup exposes `depthtex2` to gbuffer programs.
[Copy timing](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java),
[sampler binding](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/samplers/IrisSamplers.java).

Call this a **pre-hand/main-translucency background snapshot**, not universally
opaque-only depth. Older program categories can draw translucent entities/particles
earlier; the snapshot contains the depth that actually exists at that point.
It contains no water exit surface or interior-volume occupancy.
[Iris depth buffers](https://shaders.properties/current/reference/buffers/depthtex/),
[translucent ordering](https://shaders.properties/current/reference/programs/gbuffers/#translucent-gbuffers-and-deferred).

Source evidence is pinned to Iris `99d855970316329f2e0e42ac2b79ef763cb77cc3`;
the installed game/mod version has not been freshly verified.

## 2. Reconstruct a vertical gap, not raw depth subtraction

Screen depth is nonlinear, so subtracting two depth-buffer values does not measure blocks.
Reconstruct the current water and sampled background positions with the existing inverse
projection, then transform their difference without adding camera translation:

```text
deltaView = backgroundView - waterView
require dot(deltaView,unit(waterView)) > 0
deltaWorld = mat3(gbufferModelViewInverse) * deltaView
drop = clamp(max(-deltaWorld.y,0),0,32)
q = 1 - exp(-drop / max(WATER_DEPTH_SCALE,0.0001))
face = smoothstep(0.5,0.95,dot(originalNormal,worldUpInView))
w = clamp(WATER_DEPTH_STRENGTH,0,0.35) * q * face
    * clamp(environment * sky * (1-block),0,1)
```

The lookup uses `texelFetch` at the integer pixel, without filtering or a refraction
offset. Reconstruction uses that pixel's center and the depth texture's size.
Out-of-bounds pixels, sky/clear depth 1, nonfinite data, background at/in front of
the water, nonpositive ray gap, and nonpositive vertical drop keep the prior source.
The original face normal supplies eligibility, so animated reflection waves cannot
toggle this color mask. Invalid/near-zero position, normal or up vectors also bypass.

Using vertical drop reduces the dependence on grazing view-ray length over a level
bottom. It remains a same-pixel geometric heuristic: stacked water, waterlogged blocks,
air gaps, slopes and distant banks can break the assumption that the interval is water.
A 32-block cap bounds the response; it does not establish a physical maximum depth.
At scale 8, an 8-block drop gives `q≈0.632` before the remaining gates.

## 3. Preserve source luminance while shifting chroma

Let `S` be the source after M13's original tint, and `L=(0.2126,0.7152,0.0722)`:

```text
Y = dot(S,L)
candidate = S * (0.25,0.85,1.05)
target = candidate * (Y / dot(candidate,L))
result = mix(S,target,w)
```

The candidate multiplies the existing color; it does not replace every biome/source with
one fixed hue. Renormalization preserves linear Rec.709 luminance within floating-point
error. The depth mix itself adds no luminance reduction or emission. This is a source
property before the later reflection, fog and display transform, not a guarantee of
identical perceived brightness on a monitor.

The code first divides RGB by its peak, performs the luminance calculation/mix,
then restores the peak to avoid overflowing intermediate HDR dot products.
Black, negative or nonfinite input is left unchanged. An invalid, negative or
greater-than-65504 computed result also returns the original source rather than
clamping and changing its luminance; this does not sanitize already-invalid input.

The maximum selectable weight is 0.35, so this step retains at least 65% of the old source
color even before its additional masks reduce the weight. Full block light suppresses
this new color term; original sky reflection can still operate independently.

## 4. Why it does not absorb the background

```text
M13 tint → M16 depth chroma → M13/M14 sky reflection → M9 fog once → native blend
Cout = alpha * source + (1-alpha) * background
```

Changing only `source` cannot correctly apply depth-dependent absorption to the separate
`background` term. M16 therefore does not claim physical transmission, Beer–Lambert
water absorption, refraction or SSR. It never samples/re-fogs the background color,
divides by alpha, moves geometry or changes opacity. Existing alpha still attenuates
the new source-color contribution. Physical transmission needs a separate composition design.

The existing water ID, scene/debug, blend and environment gates remain. The new term is
independent of M13 tint/reflection strengths and `SKY_STYLE`: disabling those older
effects does not disable depth color. `WATER_STYLE=0` still bypasses the complete water style.

## 5. Controls and cost

| Setting | Default | Values |
|---|---:|---|
| `WATER_DEPTH_TINT` | 1 | 0, 1 |
| `WATER_DEPTH_STRENGTH` | 0.35 | 0, 0.15, 0.25, 0.35 |
| `WATER_DEPTH_SCALE` | 8 blocks | 4, 8, 16, 32 |

A larger scale makes the same vertical gap produce less color change.

`water_depth_settings.glsl` defines these options; `water_depth.glsl` owns the
guarded fetch, reconstruction and chroma mix. `water.glsl` calls it between tint
and reflection and keeps it active when only the old effects are off.
`shaders.properties` and language files extend the existing water menu.
The old “no waves” tooltip is clarified to “no vertex displacement,” consistent
with M14's normal-only waves.

Eligible water fragments add at most one same-pixel background-depth fetch plus arithmetic.
No render target, fullscreen pass or program pair is added. Actual GPU timing is unmeasured.
Disabling depth color, zero strength, or an invalid/zero gap returns the prior source.

## 6. Runtime observation sheet

| Scene | Question to resolve | Actual result |
|---|---|---|
| Shallow/deep flat-bottom pools | Is the stronger teal gradual without new source darkening? | |
| Looking down versus grazing, camera motion | Is vertical-gap color stable and free of visible edge artifacts? | |
| Held solid/transparent items | Does excluding hand depth avoid a hand-shaped color interruption? | |
| Slopes, waterfalls, shoreline and sky background | Do original face eligibility and invalid-background fallbacks work? | |
| Stacked water, air gaps and waterlogged blocks | Where does the geometric heuristic visibly fail? | |
| Glass, entities and particles across water | Record native ordering/overlap limits | |
| Cave/block light, fluid camera and other dimensions | Do the inherited lighting/environment gates remain intact? | |
| Old tint/reflection off, sky off, depth off/zero | Do independent controls and exact baselines work? | |
| Different resource-pack alpha and biome colors | Does native coverage/source identity remain recognizable? | |

## 7. Six useful questions

1. **Why `depthtex2`?** Its pre-hand snapshot avoids confusing hand depth with the background.
2. **Why reconstruct positions?** Raw perspective depth differences are not world distances.
3. **Why remove translation for the delta?** A displacement changes orientation/scale, not origin.
4. **Why preserve luminance?** This stage changes depth-related chroma while retaining the source's light level.
5. **Why is this not water thickness?** A depth snapshot gives a visible surface, not a map of water-filled intervals.
6. **Why keep alpha unchanged?** Native composition remains intact; physical transmission is deferred until its inputs and blending are designed.

## 8. Executed checks

The full M1–M16 CPU/structural validator passed. M16 checked 91 historical-file
pins, 540 pool projections and 19,440 color cases. Maximum float32 depth-fixture
reconstruction error was 0.00615097 blocks; this is a result for those fixtures,
not a universal depth-accuracy guarantee. All 1,352 offline GLSL configurations passed.

The [native compile report](validation/M16_GPU_compile.json) also passed:
1,352 configurations covering 24 program pairs compiled and linked on the Intel
driver, finishing at 2026-11-13 08:21:21 UTC with no C++ build diagnostics.

The [extended native depth report](validation/M16_GPU_depth_extended.json) passed
on Intel Iris Xe, OpenGL 3.3 compatibility / driver 31.0.101.3962:
**40 cases, 840 color samples and 767 exactly preserved bypass pixels**.
It extends the retained [initial 34-case report](validation/M16_GPU_depth.json);
the two runs are not summed as independent coverage.

Fixtures call the actual depth helper and selected full water-style wrappers.
They cover sloped faces, valid 1x1 depth plus out-of-bounds pixels, invalid/zero
projection, negative ray gap and invalid lighting/up vectors, among other gates.
Depth values are supplied through synthetic RGBA32F red-channel textures with
perspective-derived positions. They are not Minecraft-rasterized depth, and the
wrappers do not test native water blending or real Iris resource binding.

Active RGB tolerance is `0.000003 + 0.00003*abs(expected)`; explicit bypass
pixels and wrapper alpha require exact equality. Maximum RGB difference was
about 0.004872 linear HDR units in fixtures containing values around 60,000,
not a normalized display-image error. The largest fraction of allowed tolerance
was 0.00318603. Current shader contents and the report share this digest:

```text
df486ceed290338e3df31bc42c087db32fd21eb3e2dd194a5cc3549e3552df54
```

To repeat the depth suite with a new report path:

```powershell
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --suite depth --report docs/validation/M16_GPU_depth_repeat.json
```

The `all` and `render` suites now include depth cases. Existing reports are not
overwritten. These checks add native-driver evidence; the runtime table above
remains unfilled and no timing/FPS claim is made.

Related notes: [M13 water](MILESTONE_13.md), [M14 normals](MILESTONE_14.md),
[M15 native validation](MILESTONE_15.md), [roadmap](AURORA_ROADMAP.md).
