# AuroraShader: water-first development

The first reflection-stability stage distinguishes known obstruction from an unresolved ray and filters reflected color on a continuous surface. [M2 evidence](WATER_M2_REFLECTION_STABILITY.md).

The water M1 development branch adds two-segment absorption, bounded scattering and configurable clarity. [Using and verifying water optics](WATER_M1_OPTICS.md).

Updated: 2026-11-21. [中文路线图](WATER_ROADMAP.zh-CN.md).
Starting implementation: M19 commit `74c7164874e446ebd8e763f146286c2c6908b820`.
Foundation: **Water M0 / W4A common optics and diagnostic capture**, branch `codex/water-04a-optics-foundation`.
[The layered architecture](WATER_ARCHITECTURE.md) defines A–L modules, buffer ownership and the active water M0–M7 sequence. M0 is implemented; complete historical CPU, focused offline and native checks passed.
W3 is implemented; CPU/offline/native checks passed and three static synthetic views are recorded. [W3 notes](WATER_03_SCREEN_REFLECTIONS.md).
W2 is implemented with CPU/offline/native checks passed; historical native depth
regression also passed. [W2 evidence](WATER_02_FILTERED_WAVES.md).
W1 is implemented with CPU/offline/native checks passed; W3 is its first
water consumer. Minecraft/Iris runtime remains unobserved. See [W1 evidence](WATER_01_SNAPSHOT.md).

## Visual direction

Water is now the main development priority. Aim for readable clear shallows,
restrained teal-to-indigo depth, warm sunset glints, cool moonlit water and coherent
reflections of Aurora's sky. Preserve biome character and underwater visibility
where lighting and water clarity allow it. The goal is convincing water in motion
and across viewpoints, not a single attractive still image.

The physical cues must agree: a ripple changes the surface normal used by reflection,
refraction and highlights; increasing optical distance attenuates the transmitted
background; grazing views become more reflective. Artistic colors remain adjustable.
No routine user acceptance is required between stages. Code, learning notes and
actual evidence travel together on GitHub development branches; `main`, historical
projects and existing junctions remain unchanged. Project and generated files stay on D:.

## What the current water actually does

| Existing system | Current scope | Important gap |
|---|---|---|
| M13 base water style | Fluid classification, source tint, Fresnel-shaped analytic sky-color mix | Native alpha also attenuates reflection; owned optical composition remains absent |
| W3 scene reflections (automated checks passed) | First W1 consumer, guarded screen-space ray and existing-result fallback | Off-screen/hidden data absent; native alpha and unmodeled reflected-segment atmosphere remain |
| M14 / W2 waves | Three broad waves plus three pixel-footprint-filtered ripples; original broad-wave fallback | No flow field, refraction, silhouette movement or unresolved-variance roughness |
| M16 depth color | Same-pixel vertical background gap shifts source chroma while preserving luminance | Not water-path length, absorption or transmitted-background attenuation |
| Shared gates | Sky/color fallback retains sky access; W3 scene hits are independent of sky style/blend/access, with dimension/fluid/upward-face gates retained | Underwater and waterfall faces still need distinct treatment; cave reflections depend on supported captured surfaces |

These implementations have recorded numerical/compiler/native-driver evidence in
[M13](MILESTONE_13.md), [M14](MILESTONE_14.md), [M16](MILESTONE_16.md) and
[W3](WATER_03_SCREEN_REFLECTIONS.md).
Their Minecraft water appearance is not recorded as passed. Sky aurora, clouds and
sun/moon textures are not currently present in water's analytic reflection palette.
The proposed M20 Iris-preprocessing bridge was **not implemented**; water work now
takes priority. It remains a possible validation improvement, not a completed stage.

## Ranked work and dependencies

The W1–W3 records below are complete within their evidence scope. W4–W8 retain the
broader dependency groups; the newer [water M0–M7 sequence](WATER_ARCHITECTURE.md)
owns the active implementation order. Neither is a fixed delivery schedule.

| Stage | Deliverable | Dependency and completion question |
|---|---|---|
| **W1 — implemented; automated checks passed** | Matched linear scene-color and depth snapshots before the applicable distance-fog step; explicit producer/consumer contracts | CPU/offline/native checks verified the producer contract and original-output preservation within their test scope. W3 consumer implemented; actual Iris binding/flip and Minecraft rendering remain unobserved. A snapshot is not yet reflection or transmission. |
| **W2 — implemented; CPU/offline/native checks passed** | Shared multiscale water normals with pixel-footprint filtering | Synthetic affine-footprint and actual-fragment comparisons passed; historical native depth regression passed. Minecraft appearance unobserved. Geometry displacement and unresolved-variance roughness remain planned. |
| **W3 — implemented; CPU/offline/native checks passed** | Bounded screen-space ray-traced reflection, confidence and environment fallback | W1/W2 integration verified within synthetic scope: 270 ray/budget cases; 1,854 offline/native compile configurations; three static perspective views. Actual Iris binding, moving-camera appearance and performance remain unobserved. |
| **W4 — planned** | Separate shared water parameters/optics, surface-data capture and composite composition; Fresnel/transmission, attenuation and guarded refraction | Needs reliable scene inputs and water coverage. Define water-path estimates, layered-transparency limits and fog ownership before replacing native source blending. |
| **W5 — planned** | Distinct still-water, directional-flow and waterfall motion | Use verified fluid inputs where available; label any inferred flow. Join top/side motion and keep banks attached. A global scrolling pattern is not measured river flow. |
| **W6 — planned** | Underwater and waterline transitions | Define entry/exit media, underwater extinction, surface underside and total internal reflection. Reuse W4 transport rather than applying a second unrelated color overlay. |
| **W7 — planned** | Shore/impact foam, rain response and optional caustics | Require credible contact, turbulence/weather and receiver-light information. Add only where signals support the effect; foam is not a permanent bright rim around every bank. |
| **W8 — planned across stages** | Performance tiers, compatibility and artistic tuning | Measure actual GPU time and scene stability. Tune ray budgets, resolution and filtering from evidence; preserve a useful fallback path. |

W3 establishes ray hits before W4 and explicitly retains native-alpha attenuation
and unmodeled water-to-hit atmospheric fog. Its scene-hit path is independent
of sky-style/sky-access controls; those govern the environment fallback. W4 owns
the subsequent reflection/transmission and fog-composition work. After that contract,
finish the reflection appearance with a shared sky environment (including Aurora
identity), sun/moon glints and roughness informed by filtered-out wave variance.
Those systems remain planned: the current palette fallback contains no actual
aurora, glow, discs or later cloud layer. Measure their continuity and cost before
adding quality tiers.

## Optical model and tracing scope

A useful design sketch for one visible water interface is:

```text
F = Fresnel(view, normal, relative refractive index)
T = exp(-extinctionRGB * distanceInsideWater)
water = F * reflectedLight + (1-F) * (T * background + scatteredLight)
```

This is a design sketch, not the current shader equation or a full path tracer.
Scattered light must depend on available illumination; cave water must not become
self-lit. A depth-buffer interval is only an estimate of the water-filled interval,
particularly with air gaps, layered water and transparent objects. The air/water
IOR boundary and the above/below-water side matter for refraction and total internal
reflection. [Dielectric optics](https://www.pbr-book.org/4ed/Reflection_Models/Specular_Reflection_and_Transmission),
[reflection/transmission](https://www.pbr-book.org/4ed/Reflection_Models/Dielectric_BSDF),
[transmittance](https://www.pbr-book.org/4ed/Volume_Scattering/Transmittance).

SSR traces against visible screen-depth data. Off-screen or hidden geometry is
missing, so a miss needs a documented fallback and confidence transition. It is
not a full scene representation. [Screen-space tracing and its limits](https://casual-effects.blogspot.com/2014/08/screen-space-ray-tracing.html).
World-space voxel tracing would need a new scene representation, updates, memory
and material policy. Hardware ray tracing/path tracing needs separate verified
renderer/API and acceleration-structure support; this repository supplies none of
that today. Compute-shader availability alone does not establish hardware RT.
[Iris program stages](https://shaders.properties/current/reference/programs/overview/).

## Controlled observation matrix

Keep seed/location, camera path, FOV, resolution, exposure, time and weather fixed
for each A/B comparison. Use a separate D: test setup when available; do not change
historical worlds or junctions. Empty results mean **unobserved**, not a pass.

| Scene / view | What must be judged | Observed result |
|---|---|---|
| Flat pools at shallow, medium and deep levels; directly overhead | Floor readability, gradual attenuation, biome color and absence of artificial glow | |
| Same pool at 0°, 30°, 60° and 80° from the surface normal | Continuous Fresnel transition, reflection/transmission balance and horizon behavior | |
| Orbit/translate camera; change FOV at fixed world location | World-anchored waves and geometrically coherent reflections, no screen-fixed swimming | |
| Near, middle and distant water | Fine detail resolves nearby and fades smoothly at distance; no sparkling/strobing horizon | |
| River bends, shallow steps and waterlogged boundaries | Credible downstream motion, stable joins and correct water classification | |
| Waterfall top, vertical sheet and impact zone | Distinct downward flow, preserved side coverage and localized turbulence/foam | |
| Sloped shore, cliffs, thin poles and fences | No bank see-through, false ray hits, long reflection streaks or permanent white rim | |
| Reflected object entering/leaving screen or passing behind foreground geometry | Confidence/fallback transitions without black holes or abrupt reflection loss | |
| Noon, sunset, full/new moon, rain and fog | Coherent glints, sky identity and light levels without clipped white water | |
| Camera crossing the waterline; looking upward from below | Continuous medium transition, believable refraction/window and total internal reflection | |
| Cave pool with torch; glass, particles, entities and held items around water | Local lighting, transparent ordering and no hand-shaped depth/reflection artifacts | |
| Other biome/resource-pack alpha, resize and quality presets | Stable material intent, no stale buffers, documented fallbacks and measured cost | |

## Iteration evidence

1. Check equations and invariants: finite radiance, bounded energy/weights, exact
   Off paths, camera-coordinate invariance and valid ray intervals.
2. Compile the affected options and run synthetic GPU fixtures for hits, misses,
   borders, invalid depths and composition. Record their limited scope.
3. Capture the controlled Minecraft scenes and short motion sequences when a real
   test instance is available. Judge appearance, ordering and temporal artifacts there.
4. Measure GPU cost at stated hardware/resolution/settings before assigning quality
   tiers. Test duration and isolated shader success are not in-game FPS evidence.
5. Publish the code, observations, unresolved cases and next change together.

Wave parameters should connect wavelength, amplitude and speed; broad mesh motion
and fine normal detail have different sampling limits.
[Wave-model reference](https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-1-effective-water-simulation-physical-models).
The first structural deliverable is W1's trustworthy scene/depth input, which makes
later reflection and transmission reviewable without confusing depth or fog spaces.

[Above-water refraction and dispersion](WATER_M3_REFRACTION.md) now follow the captured water surface to a matched background hit.

[Slope flow, rain and contact ripples](WATER_CURRENTS.md) add camera-independent surface movement and a 15-impulse local history.

[Foam and directional highlights](WATER_M5_FOAM.md) share surface shadows and pixel footprints.
