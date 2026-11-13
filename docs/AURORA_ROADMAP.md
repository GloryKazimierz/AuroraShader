# AuroraShader: visual direction and development roadmap

Updated: 2026-11-13. [中文路线图](AURORA_ROADMAP.zh-CN.md).

## Product direction

Build a cohesive, playable fantasy shader pack with a recognizable Aurora style.
Complementary is a reference for completeness, quality, configurability and
performance tiers; Aurora's artistic choices and implementation are developed
within this project. The user's selected direction is **rich fantasy: vivid
skies, dreamlike nights, and expressive color**.

The proposed visual vocabulary is:

| Scene | Direction | Readability requirement |
|---|---|---|
| Day | Azure/cyan sky, warm sun, lively vegetation | Keep material colors recognizable |
| Dawn/dusk | Coral/gold near the sun, violet away from it | Preserve cloud and horizon detail |
| Night | Indigo sky, cool moonlight, warm local lights | Terrain and silhouettes remain usable |
| Weather | Muted palettes with coherent transitions | Rain should not leave a clear sunny backdrop |
| Signature night | A future teal/green aurora treatment | Optional and restrained enough for normal play |

An aurora is a future candidate, not a feature already implemented. Rich color
should be concentrated in lighting, atmosphere and emissive accents, rather than
turning every surface into a uniform color wash.

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
| M7 | Fantasy day/night sky and celestial light palette | Implementation branch; validation status belongs in the change report |

M6 remains available as a historical branch. M7 builds on its implementation,
without upgrading its runtime status merely because development continues.

## Sequence of work

These are priorities, not a promise that every item fits into one milestone.
Each step should ship a small, reviewable increment with its own learning notes.

1. **Sky and light identity (M7).** Establish continuous day/twilight/night
   palettes, sun-facing warmth and protected local lighting. Keep original
   stars, sun and moon rendering. Introduce explicit sRGB transfer helpers for
   palette interpolation while documenting the existing LDR scene limitations.
2. **Scene color foundation.** Design a consistent linear-light/HDR path,
   tone mapping and exposure. Audit all writers, blending, translucent surfaces
   and display encoding together. A floating-point buffer alone is not an HDR
   lighting pipeline. Avoid losing bright details before tone mapping.
3. **Atmosphere with geometry.** Add distance/height fog and weather transitions;
   treat opaque and translucent surfaces consistently. Sky horizon coloring in
   M7 is not geometry fog. Coordinate the palette before adding volumetric light.
4. **Clouds and controlled glow.** Develop clouds, emissive accents and bloom in
   separate increments. Keep each independently configurable; test bright skies,
   caves and nighttime settlements. Add volumetric effects only with an explicit
   performance budget and a useful lower-cost fallback.
5. **Water and material response.** Add water color, transmission, waves and
   reflection incrementally. Evaluate screen-space reflections and material
   conventions when the scene buffers and transparency handling can support them.
6. **Aurora signature and completeness.** Explore optional aurora/night phenomena,
   distinct dimension palettes, vegetation motion, performance profiles and broad
   compatibility. Maintain clear gameplay silhouettes and stable temporal behavior.

Shadow improvements such as receiver-plane depth correction remain available
when observed artifacts justify them. A larger menu of shadow algorithms is not
a prerequisite for progressing toward the artistic goal.

## Continuous development and publication

The user has authorized development to continue without requiring manual
acceptance after every milestone. The working loop is:

1. Pick a bounded change and record its intended visual result.
2. Implement it with explicit settings and a useful baseline/fallback.
3. Run relevant structural, numerical and available GLSL checks; review the diff.
4. Update English and Chinese explanations, known limits and runtime questions.
5. Commit the coherent change and push its development branch to GitHub.
6. Continue with the next independent step; carry unresolved runtime observations
   in the documentation rather than claiming they passed.

Routine development stays on development branches. Publishing a branch does not
mean merging it into `main` or declaring a release. Preserve historical branches,
the original learning projects, and the user's existing Minecraft junction.
Project files remain on D:.

Work continues during active development sessions. This agreement does not create
an unattended background service after a session ends. The recorded branch,
commit and next step allow the next session to resume without another design
approval round.

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

- [Complementary's stated product priorities](https://www.complementary.dev/)
- [Iris rendering program order](https://shaders.properties/current/reference/programs/overview/)
- [M7 implementation and learning notes](MILESTONE_7.md)
- [M6 shadow-bias experiment](MILESTONE_6.md)
