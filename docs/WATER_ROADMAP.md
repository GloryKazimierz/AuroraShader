# AuroraShader: water-first development

Updated: 2026-11-21. [中文路线图](WATER_ROADMAP.zh-CN.md).
Starting implementation: M19 commit `74c7164874e446ebd8e763f146286c2c6908b820`.
Current work: **W1 matched scene/depth capture**, branch `codex/water-01-scene-snapshot`.
W1 is implemented and CPU/offline/native checks passed; no water consumer or
Minecraft/Iris runtime result exists yet. See [W1 evidence](WATER_01_SNAPSHOT.md).

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
| M13 water style | Fluid classification, source tint, Fresnel-shaped analytic sky-color mix | Native alpha also attenuates reflection; no scene reflection or optical composition |
| M14 waves | Three world-anchored analytic slopes perturb the reflection normal | No flow field, refraction, silhouette movement or distant detail filtering |
| M16 depth color | Same-pixel vertical background gap shifts source chroma while preserving luminance | Not water-path length, absorption or transmitted-background attenuation |
| Shared gates | Water style is restricted by sky access, camera fluid state and upward-facing surface eligibility | Cave water, underwater views and waterfall faces need distinct treatment |

These implementations have recorded numerical/compiler/native-driver evidence in
[M13](MILESTONE_13.md), [M14](MILESTONE_14.md) and [M16](MILESTONE_16.md).
Their Minecraft water appearance is not recorded as passed. Sky aurora, clouds and
sun/moon textures are not currently present in water's analytic reflection palette.
The proposed M20 Iris-preprocessing bridge was **not implemented**; water work now
takes priority. It remains a possible validation improvement, not a completed stage.

## Ranked work and dependencies

The rows are an implementation order, not fixed delivery dates or a promise that
each row fits one commit. Debuggable, reversible increments come before extra effects.

| Stage | Deliverable | Dependency and completion question |
|---|---|---|
| **W1 — implemented; automated checks passed** | Matched linear scene-color and depth snapshots before the applicable distance-fog step; explicit producer/consumer contracts | CPU/offline/native checks verified the producer contract and original-output preservation within their test scope. No consumer; actual Iris binding/flip and Minecraft rendering remain unobserved. A snapshot is not yet reflection or transmission. |
| **W2 — planned** | Shared multiscale water normals with pixel-footprint filtering | Preserve world/time continuity; retain broad motion while filtering unresolved ripples. Use one normal model for later reflection/refraction/glints. Geometry displacement waits for shoreline and culling contracts. |
| **W3 — planned** | Screen-space ray-traced reflection, confidence and environment fallback | Needs W1 depth/color agreement and W2 normals. Validate hits independently, then blend failures smoothly. Cover borders, occlusion, thin objects and moving cameras. |
| **W4 — planned** | Owned water composition: Fresnel reflection/transmission balance, depth attenuation and guarded refraction | Needs reliable scene inputs and water coverage. Define water-path estimates, layered-transparency limits and fog ownership before replacing native source blending. |
| **W5 — planned** | Distinct still-water, directional-flow and waterfall motion | Use verified fluid inputs where available; label any inferred flow. Join top/side motion and keep banks attached. A global scrolling pattern is not measured river flow. |
| **W6 — planned** | Underwater and waterline transitions | Define entry/exit media, underwater extinction, surface underside and total internal reflection. Reuse W4 transport rather than applying a second unrelated color overlay. |
| **W7 — planned** | Shore/impact foam, rain response and optional caustics | Require credible contact, turbulence/weather and receiver-light information. Add only where signals support the effect; foam is not a permanent bright rim around every bank. |
| **W8 — planned across stages** | Performance tiers, compatibility and artistic tuning | Measure actual GPU time and scene stability. Tune ray budgets, resolution and filtering from evidence; preserve a useful fallback path. |

W3 can establish ray hits before W4, but its integration must retain the stated
native-alpha limitation until composition changes. Water material reflection should
eventually work independently of the Aurora-sky style switch: sky availability
controls the environment fallback, while a valid local-scene hit has its own evidence.

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
