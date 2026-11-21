# AuroraShader: visual direction and development roadmap

Updated: 2026-11-21. [中文路线图](AURORA_ROADMAP.zh-CN.md).

## Product direction

Build a cohesive, playable fantasy shader pack with a recognizable Aurora style.
Complementary is a reference for completeness, quality, configurability and
performance tiers; Aurora's artistic choices and implementation are developed
within this project. The user's selected direction is **rich fantasy: vivid
skies, dreamlike nights, and expressive color**.

**Current priority: realistic, beautiful water.** The user's 2026-11-21 direction
puts waves, flow, reflections/refraction and all-view stability first, while retaining
Aurora's fantasy identity. [The water roadmap](WATER_ROADMAP.md) owns the ranked
dependencies and controlled observation matrix. W1 matched scene/depth capture is
implemented on `codex/water-01-scene-snapshot`, with CPU/offline/native checks passed.
There is no water consumer yet; Minecraft/Iris runtime remains unobserved.
[W1 implementation and evidence](WATER_01_SNAPSHOT.md).
The proposed M20 Iris-preprocessing bridge was not implemented and is deferred
behind this water-first work.

The proposed visual vocabulary is:

| Scene | Direction | Readability requirement |
|---|---|---|
| Day | Azure/cyan sky, warm sun, lively vegetation | Keep material colors recognizable |
| Dawn/dusk | Coral/gold near the sun, violet away from it | Preserve cloud and horizon detail |
| Night | Indigo sky, cool moonlight, warm local lights | Terrain and silhouettes remain usable |
| Weather | Muted palettes with coherent transitions | Rain should not leave a clear sunny backdrop |
| Signature night | M11 teal/violet sky-only aurora | Optional and restrained enough for normal play |

M11 introduces a bounded sky-only aurora; its runtime appearance remains unconfirmed.
Rich color should be concentrated in lighting, atmosphere and emissive accents,
rather than turning every surface into a uniform color wash.

## What exists

| Stage | Implemented focus | Evidence |
|---|---|---|
| M1 | Color grading | User-confirmed Minecraft runtime testing |
| M2 | Surface normals, light levels, deferred Lambert modulation | User-confirmed Minecraft runtime testing |
| M3A | Directional hard shadow mapping | User-confirmed Minecraft runtime testing |
| M3B | 3x3 PCF | User-confirmed Minecraft runtime testing |
| M4 | 3x3 versus 5x5 filter experiment | Automated checks; runtime confirmation not recorded here |
| M5 | Eight-tap Poisson PCF | Automated checks; runtime confirmation not recorded here |
| M6 | Constant versus angle-aware receiver bias | Automated checks; runtime confirmation remains pending |
| M7 | Fantasy day/night sky and celestial light palette | Offline checks recorded; runtime confirmation remains pending |
| M8 | Linear scene composition, HDR storage and final highlight mapping | Offline checks recorded; runtime confirmation remains pending |
| M9 | Distance/height/weather fog with explicit opaque and late-blend scope | Offline checks recorded; runtime confirmation remains pending |
| M10 | Controlled linear HDR bright-pixel bloom at half resolution | Offline checks recorded; runtime confirmation remains pending |
| M11 | World-oriented, night/weather-gated procedural sky aurora | Offline checks recorded; runtime confirmation remains pending |
| M12 | Native cloud color and source-depth fog with explicit blend scope | Offline checks recorded; runtime confirmation remains pending |
| M13 | Water-fluid classification, bounded tint and analytic sky-color reflection | Offline checks recorded; runtime confirmation remains pending |
| M14 | World-anchored analytic water normals for moving sky reflections | Offline checks recorded; runtime confirmation remains pending |
| M15 | Native-driver shader validation and synthetic GPU rendering checks | Native driver checks recorded; Minecraft/Iris confirmation remains pending |
| M16 | Same-pixel vertical-background-gap water color with preserved source luminance | CPU/offline/native checks recorded; Minecraft/Iris confirmation remains pending |
| M17 | Grouped settings, complete Simplified Chinese labels and three six-setting profiles | CPU/offline/native profile checks recorded; Iris UI/runtime confirmation pending |
| M18 | Shared world-anchored leaf/grass displacement and matching shadows; profiles expanded to seven controls | CPU/offline/native checks recorded; Minecraft/Iris observation remains pending |
| M19 | Independent angular sun/moon sky glow with bounded color and artistic lunar-phase brightness | CPU/offline/native checks recorded; Minecraft/Iris observation remains pending |
| W1 | Matched pre-fog scene color/depth snapshot producer; no consumer yet | CPU/offline/native checks passed; Minecraft/Iris observation remains pending |

M6–M18 remain available as historical branches. M19 builds on M18 without
upgrading any runtime status merely because development continues.

## Sequence of work

These are priorities, not a promise that every item fits into one milestone.
Each step should ship a small, reviewable increment with its own learning notes.

1. **Sky and light identity (M7).** Establish continuous day/twilight/night
   palettes, sun-facing warmth and protected local lighting. Keep original
   stars, sun and moon rendering. Introduce explicit sRGB transfer helpers for
   palette interpolation while documenting the existing LDR scene limitations.
2. **Scene color foundation (M8).** Implement linear scene composition, RGBA16F
   storage and one final exposure/highlight mapping/encoding sequence. Retain the
   baked Minecraft input product as a documented bridge, and initialize background
   colors explicitly. Future material work can migrate input operations further;
   this foundation is not a complete physical/PBR renderer.
3. **Atmosphere with geometry (M9).** Add bounded distance/height/weather fog after
   recorded surface lighting and before known late-source blending. Keep unsupported
   draw/blend paths explicit; expand that coverage as their contracts are verified.
   This is a simple fog model, not shadowed volumetric scattering.
4. **Controlled glow (M10).** Extract bright linear scene pixels before half-resolution
   area averaging, blur with a fixed separable kernel and add before final display
   mapping. This is not material emission; sky and held items can contribute. Keep
   its pass/storage cost explicit, including when the effect is off.
5. **Distinctive night identity (M11).** Add bounded teal/violet ribbons only to
   the ordinary upper sky. Use world-oriented directions, periodic motion and
   night/weather/environment gates. Keep native celestial-body/star paths and
   geometry fog separate; this is not physical auroral scattering or a light source.
6. **Native cloud atmosphere (M12).** Preserve cloud geometry, baked face/weather
   shading and alpha. Add bounded solar-phase tint, then existing M9 source-depth
   fog before supported native blends. Unknown cloud blend paths retain their
   baseline; overlap with celestial objects/aurora still needs runtime observation.
   Custom cloud geometry, volumetrics and cloud shadows remain separate future work.
7. **Water foundations (M13).** Classify actual water-fluid geometry, retain native
   alpha and apply bounded tint/analytic sky-color reflection before the existing
   foreground fog. This reflects a palette, not scene geometry, clouds or aurora;
   it adds no SSR, refraction or waves.
8. **Gentle water reflection motion (M14).** Add bounded analytic wave normals at
   world-anchored positions. Keep geometry, alpha, depth, tint and fog unchanged;
   preserve the original surface eligibility before perturbing reflection/Fresnel.
   Document periodic space/time and the limits of normal-only motion.
9. **Native GPU validation (M15).** Add a hidden Windows OpenGL harness to compile
   and link shader variants on the active driver and compare selected synthetic
   framebuffer results with CPU references. Keep compiler, GPU and Minecraft/Iris
   evidence separate; add no graphics feature or performance claim.
10. **Water depth color (M16).** Use the pre-hand/pre-translucent background depth
   at the same pixel to estimate a bounded vertical gap. Gently shift eligible
   water-source color toward equal-luminance teal, keeping native alpha and the
   existing reflection/fog sequence. This geometric heuristic is not water-volume
   thickness, absorption or transmission.
11. **Usable controls (M17).** Group all existing options, add complete Simplified
   Chinese labels, and define Light/Balanced/Soft Shadows profiles over six controls.
   Preserve artistic settings and distinguish profile matching from effect visibility;
   these profiles do not establish measured hardware/performance tiers.
12. **Gentle foliage motion (M18).** Move eleven vanilla leaf types and rooted short/tall
   grass with a shared world-position field in terrain and shadow rendering. Keep
   motion bounded, preserve unrelated geometry and expose Off/strength/speed controls.
   Extend profiles to seven controls; leave culling/model assumptions and runtime
   observations explicit. This is not a weather or plant-physics simulation.
13. **Celestial sky glow (M19).** Add bounded warm sun and cool moon halos to the sky
   background, using independent celestial directions, angular falloff and artistic
   lunar-phase brightness. Retain native discs, terrain lighting and shared fog/water
   palettes; explain angular width versus pixel footprint and finite fallbacks.
14. **Water-first specialization — current priority.** W1 implements matched
   scene/depth capture before the deferred fog call. Planned work follows with
   filtered multiscale normals, guarded SSR,
   owned reflection/transmission composition and then flow/waterfall/underwater detail.
   [The dedicated water roadmap](WATER_ROADMAP.md) records the full dependencies,
   tracing limits, shore/foam/rain/caustics plans and scene/performance observations.
   Existing M13/M14/M16 water remains the starting point, not a claim that these
   planned systems are already implemented.
15. **Broader completeness — secondary.** Dimension palettes, vegetation expansion
   and unrelated graphics features wait behind water work, except for fixes needed
   to keep the pack stable. Compatibility and measured performance remain part of
   every water stage.

Shadow improvements such as receiver-plane depth correction remain available
when observed artifacts justify them. A larger menu of shadow algorithms is not
a prerequisite for progressing toward the artistic goal.

## Continuous development and publication

The user has authorized development to continue without requiring manual
acceptance after every milestone. The working loop is:

1. Pick a bounded change and record its intended visual result.
2. Implement it with explicit settings and a useful baseline/fallback.
3. Run relevant structural, numerical, available GLSL and native-driver checks;
   review the diff. Keep synthetic GPU coverage distinct from Minecraft runtime.
4. Update English and Chinese explanations, known limits and runtime questions.
5. Commit the coherent change and push its development branch to GitHub.
6. Continue with the next independent step; carry unresolved runtime observations
   in the documentation rather than claiming they passed.

Routine development stays on development branches. Publishing a branch does not
mean merging it into `main` or declaring a release. Preserve historical branches,
the original learning projects, and the user's existing Minecraft junction.
Project files remain on D:.

The user explicitly activated a continuing development goal with `/goal nonstop`.
Keep advancing coherent stages and carrying their code, tests and explanations
together. Do not stop for routine milestone acceptance or silently mark the broad
product goal complete after one feature. Recorded commits and next steps preserve
continuity across development turns; runtime evidence remains a separate record.

## Knowledge that travels with the code

For each visual system, keep the following together in GitHub:

- The problem, the intended appearance and the pipeline stage responsible.
- Coordinate spaces, equations, defaults and the reason for each guard.
- What was measured or checked, and what still requires Minecraft/Iris observation.
- A small controlled comparison with empty fields for unobserved results.
- Trade-offs and concise Graphics/Rendering interview explanations.
- A next-step note that separates implementation work from outstanding observations.

Static or standalone compiler success must never be relabeled as Minecraft/Iris
runtime success. No performance improvement is claimed without measurement.

## References

- [Water-first roadmap and observation matrix](WATER_ROADMAP.md)
- [Complementary's stated product priorities](https://www.complementary.dev/)
- [Iris rendering program order](https://shaders.properties/current/reference/programs/overview/)
- [M19 celestial sky-glow learning notes](MILESTONE_19.md)
- [M18 foliage wind and matching-shadow notes](MILESTONE_18.md)
- [M17 settings and profile guide](MILESTONE_17.md)
- [M16 water depth-color learning notes](MILESTONE_16.md)
- [M15 native GPU validation learning notes](MILESTONE_15.md)
- [M14 analytic water-normal learning notes](MILESTONE_14.md)
- [M13 water foundation learning notes](MILESTONE_13.md)
- [M12 native cloud atmosphere learning notes](MILESTONE_12.md)
- [M11 procedural sky aurora learning notes](MILESTONE_11.md)
- [M10 controlled bloom learning notes](MILESTONE_10.md)
- [M9 fog and composition learning notes](MILESTONE_9.md)
- [M8 scene color and HDR learning notes](MILESTONE_8.md)
- [M7 implementation and learning notes](MILESTONE_7.md)
- [M6 shadow-bias experiment](MILESTONE_6.md)
