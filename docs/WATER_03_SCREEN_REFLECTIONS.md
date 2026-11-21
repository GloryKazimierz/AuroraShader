# Water 03: Bounded screen-space water reflections

Date: 2026-11-21. Branch: `codex/water-03-screen-reflections`.
Base: W2 commit `db67a74a9244b81c809ce776a9c8567f17587039`.
[中文学习版](WATER_03_SCREEN_REFLECTIONS.zh-CN.md) · [Water roadmap](WATER_ROADMAP.md).

W3 adds the first consumer of the W1 scene snapshot: a bounded screen-space
reflection ray, directed by the water normal. Implementation and CPU/offline/native
checks are complete, with three static synthetic views recorded. No Minecraft/Iris
appearance or performance result is claimed.

## 1. Controls and scope

| Control | Default / values | Purpose |
|---|---|---|
| `WATER_SCREEN_REFLECTIONS` | 1 / 0, 1 | Enable scene-reflection tracing; off is the W2 comparison path |
| `WATER_REFLECTION_STEPS` | 64 / 64, 128 | Maximum screen-space traversal steps, not world-distance reach |
| Existing Water Reflection Strength | Unchanged | Artistic strength of scene reflection and the available sky fallback |

The new controls follow reflection strength on the water screen. Profiles still
control seven settings; they do not override these two options. Increasing the
budget may reach more visible samples, with additional work; it does not reveal
off-screen geometry or guarantee a hit. There is no measured FPS claim.

This is screen-space ray tracing against one captured depth layer, not hardware
ray tracing, voxel tracing or path tracing. No new backend is installed. Hidden
surfaces, screen-exterior objects, missing layers and unsupported captured materials
are unavailable. W3 retains native water geometry, coverage, alpha and existing
water-normal controls. Flow, refraction and underwater transport are later work.

## 2. Matched inputs and an explicit occlusion guard

| Input | Role |
|---|---|
| `colortex5` RGBA16F | W1 lit linear RGB before the deferred fog call; alpha is sample validity |
| `colortex6` R32F | Nonlinear depth paired with that RGB, reconstructed before view-depth comparison |
| `depthtex1` | Matching pre-translucency depth used to detect unsupported foreground occlusion |

The water pass reads snapshots without writing to them. Scene data cannot be read
from colortex0–3 in a gbuffers program because those names map to texture atlases.
W1's published-side/clear contract remains an Iris integration assumption until
observed in the game. [Iris color buffers](https://shaders.properties/current/reference/buffers/colortex/),
[W1 timing and validity notes](WATER_01_SNAPSHOT.md).

An invalid snapshot is not necessarily empty sky. W1 rejects hands and unknown
surface metadata, leaving snapshot depth 1. The original `depthtex1` can still
contain a foreground surface there. The guard must stop an unsupported occlusion
rather than continue through it and reflect a farther object. It supplies no new
reflectable color: accepted hit color/depth still come from paired 5/6. An accepted hit additionally requires binary validity 1, finite nonnegative
half-float-range RGB and exact depth agreement between `colortex6` and `depthtex1`.
Buffer sizes must agree. A missing snapshot is a miss, not permission to invent geometry. Depth names are shorthand
for capture timing, not a proof that every earlier draw is opaque.
[Iris depth overview](https://shaders.properties/current/reference/buffers/depthtex/).

## 3. A bounded perspective-correct trace

The agreed traversal contract is:

- A normalized reflection ray from a 0.01-view-unit original-normal offset, starting at 0.05 travel; exclude the projected source pixel from hits.
- Maximum ray length 64 view-space units; clip at the near plane before perspective division.
- Two-dimensional pixel-grid traversal visits resolved crossed-cell intervals; 64 or 128 processed cells is the budget.
- Perspective-correct ray depth intervals compared with the captured view-depth surface.
- Adaptive view-depth tolerance: clamp the ray-depth span in a cell to a 0.15 base and 0.5 cap; finite/validity checks and explicit misses.

The near plane is reconstructed from `gbufferProjectionInverse` and padded inward
by `max(0.0001, abs(nearZ)*0.0001)` before clipping; it is not an independent camera
setting. Projection and inverse projection share the Iris world-camera contract,
whose hand paths have a documented depth-scale exception. W1 conservatively
excludes newly nearer hand-like depths. [Iris matrices](https://shaders.properties/current/reference/uniforms/matrices/).

The screen-step budget and ray-length limit are independent: a long projected ray
can exhaust 64 pixels well before reaching 64 view units. A view unit is the shader's
coordinate unit, not a guaranteed physical meter under arbitrary camera transforms.
The depth tolerance covers a single visible layer, not measured block thickness
or water depth. Too large can invent hits; too small can miss thin surfaces.

Perspective-correct traversal advances to the next x or y grid boundary, advancing
both axes at an exact corner. A screen-length interval no larger than
max(0.0001, 4 * 2^-23 * maxBufferDimension) pixels is discarded before texture
fetches and budget counting. This explicit float-precision policy prevents almost
corner-touching rays from consuming different budgets for microscopic intervals:
the floor is 0.0001 pixel at dimension 96 and about 0.00195 pixel at dimension 4096.
The hard loop cap is 256 iterations, including skipped intervals; the 64/128 option
counts only processed intervals. Thus the trace covers resolved grid intervals,
not every mathematically nonzero sliver or zero-area corner-touch neighbor.
Finite depth samples still cannot guarantee every subpixel pole or silhouette.
The adaptive slab trades
some tolerance for grazing depth variation against possible false hits, and remains
capped at 0.5. Near clipping, occlusion and budget exhaustion need independent tests.

During development, analytic geometry fixtures exposed misses from the earlier
major-axis-only traversal and fixed 0.15 slab. Full grid intervals and the bounded
adaptive tolerance address those mechanisms. Final CPU and native fixtures pass
within the stated scope below. Earlier failed revisions
are not being reported as successful runs.
[McGuire and Mara's algorithm paper](https://jcgt.org/published/0003/04/04/paper.pdf).
The paper's historical performance numbers are not Aurora measurements.

## 4. Confidence, Fresnel and environment are separate

Hit confidence describes how safely the available screen data supports a candidate.
It controls the transition from a scene hit back to the existing water/sky result.
The current confidence is the product of three heuristic fades: distance from the
viewport edge over 0–8 pixels, travel over 48–64 view units, and steps over the last
25% of the chosen budget. It is not a calibrated probability or a material property.
Fresnel describes the interface's angle-dependent reflection weighting. Reducing
confidence must not be described as changing water's physical reflectance.
[Dielectric reflection and transmission](https://www.pbr-book.org/4ed/Reflection_Models/Dielectric_BSDF).

Local scene hits are designed to work independently of `SKY_STYLE`, `SKY_BLEND`
and sky-light access. Those controls affect the analytic sky fallback, not whether
a valid lit cave surface exists. Existing material, blend, linear/debug, dimension,
fluid-camera and original upward-face restrictions remain explicit. In a cave with
no usable environment fallback, a miss keeps the existing water appearance rather
than introducing a bright outdoor sky. This fallback remains the analytic M7 palette:
it does not reflect the actual aurora, sky glow, sun/moon discs or clouds. W1 does
not capture later cloud draws. SSR alone does not add those missing sky components.

Reflection candidates replace the corresponding fallback contribution; they are
not added as a second full-strength reflection. W2 normals guide the ray while
unresolved ripple roughness and temporal accumulation remain absent. Snapshot RGB
was shaded from the original camera view; later view-dependent source highlights
will need additional care even when the ray intersection is correct.

## 5. Two optical limitations retained deliberately

**Native source-alpha composition remains.** With ordinary blending,
`output = alpha * waterSource + (1-alpha) * background`. Therefore alpha also
attenuates a reflection placed in `waterSource`. W3 does not divide by alpha,
change transparency or independently impose physical transmission on the background.
Fresnel-shaped source color is still an artistic approximation.
For a fully supported, confidence-1 hit, the synthetic bench's alpha 0.55 and
default reflection strength 0.35 reduce a normal-incidence F0 of 0.02 to a 0.00385
reflection coefficient; even the grazing limit is at most 0.1925 before fog/tone
and other gates. This explains a subtle overhead change without implying a failed trace.
[Iris blend rules](https://shaders.properties/current/reference/shadersproperties/rendering/).

**Atmospheric fog along water-to-hit is not modeled yet.** Captured RGB is before
the deferred camera-path fog, not universally free of every earlier fog contribution.
W3 does not feed the hit position into the camera-origin fog function: that would
attenuate camera-to-hit and then camera-to-water, two inappropriate paths. Existing
late fog still applies once from camera to water. The omitted reflected segment
can leave distant reflections too clear; this is a temporary limitation, not a
physically complete solution. A future segment policy must also decide how the
artistic `FOG_START` distance is shared rather than restarting it per bounce.
[Transmittance along segments](https://www.pbr-book.org/4ed/Volume_Scattering/Transmittance).

W4 is next: own reflection/transmission composition, define attenuation/refraction
and layered-transparency limits, and make fog ownership explicit. W3 adds scene
information; it does not complete the water optics system. The next W4 separation
will organize shared WaterParams/optics, water surface-data capture and composite
optics; simulation and postprocessing remain separate responsibilities. W3 does
not introduce compute-wave simulation, a new water composite pass or TAA.

## 6. Files and validation status

| File | Responsibility |
|---|---|
| [`water_screen_reflection_settings.glsl`](../shaders/lib/water_screen_reflection_settings.glsl) | Default-on scene tracing and 64/128-step budget |
| [`water_screen_reflection.glsl`](../shaders/lib/water_screen_reflection.glsl) | Projection, bounded traversal, validity/occlusion guard, confidence and source-RGB replacement |
| [`water.glsl`](../shaders/lib/water.glsl) | Separate local scene weight from sky fallback; keep existing water classification/normal/fog composition |
| [`shaders.properties`](../shaders/shaders.properties), language files | Two controls, updated strength help and bilingual explanations; profiles unchanged |

W3 reads existing W1 buffers and adds no render pass or attachment. Its fetch and
traversal cost depends on water coverage and termination, not only the budget value.


| Evidence layer | Status |
|---|---|
| CPU projection/traversal/occlusion and historical/source/UI checks | Passed the complete M1–M19/W1/W2/W3 validator; 28 scenes and 270 ray/budget cases: 214 hits, 56 misses |
| Offline program compilation | All 1,854 compile/link configurations passed |
| Native compilation | All 1,854 configurations passed; [native compile report](validation/W3_GPU_compile.json) |
| Native trace, guard, source composition and regression tests | Passed: 28 scenes × two budgets, 270 queries, 214 hits and 56 misses; [native reflection report](validation/W3_GPU_screen_reflections.json) |
| Independent synthetic visual bench | Three static daylight perspective views completed on Intel Xe OpenGL 3.3; [report](validation/W3_visual_final/report.json), [contact sheet](validation/W3_visual_final/contact_sheet.png) |
| Actual Iris snapshot binding/flip and Minecraft water rendering | Unobserved |
| In-game GPU time, VRAM and quality tradeoffs | Unmeasured |

The CPU suite includes 204 independent analytic-plane comparisons. Maximum
observed projected-position/ray-distance errors are 1.02244 pixels / 0.350923 view
units, reflecting the finite sampled-depth approximation rather than exact mesh
intersection. Valid black and FP16-maximum radiance are tested as legitimate
payloads. All 102 W2 shader/config/language files restore exactly under the
historical adapter, including the SSR-off behavior checks. The current menu has
60 controls, 12 screens and 191 matching bilingual keys; profiles still control
seven options and retain 53 others.

Native checks used Intel Xe OpenGL 3.3 compatibility. The trace's maximum numeric
comparison error was 0.000561409, within its absolute-plus-relative tolerance
(maximum tolerance fraction 0.796285). Ten actual water-style helper configurations
cover local/cave/sky-disabled hits and exact miss/gate fallbacks; 32 of 80 pixels
change. Four actual pack-fragment regressions retain the previous wave paths with
SSR off. These are synthetic source/helper checks, not native blending-state or
Iris ordering tests. Compile, reflection and final visual reports share shader
SHA-256 c5caa7e0d8a6149f53d4725fd5d492993f4182d9684e1c1fe44fa1358e58d34e.

Synthetic traces must separate geometric hits, blocked unknown surfaces, ordinary
misses and budget exhaustion. Source or native checks cannot prove real Iris timing,
transparent ordering or the final appearance in a world.

## 7. Visual bench: all views, same scene

Use one shallow pool and one deep basin with a stone bank, colored wall, narrow
pole, glass panel, hand-held object and a dark covered inlet. Record coordinates,
camera/FOV/resolution, resource pack, time/weather, settings and hardware per run.
Compare SSR off/on and 64/128 steps; keep the rest fixed. This is a test plan,
not a claim that a Minecraft bench was built or an image captured. Empty results are unobserved.

The separate [synthetic visual tool](../tools/render_water_bench.py) ran three
256×144 static daylight views at 20/55/80 degrees from the water normal. It uses
invented CPU plane/AABB geometry and actual native water/fog/display helpers, with
real perspective water depth and derivatives. The source-alpha RGB equation is
evaluated explicitly; the bench does not exercise real transparent draw ordering
or OpenGL blending state. [Labeled contact sheet](validation/W3_visual_final/contact_sheet.png),
[reproducible run details](validation/W3_visual_final/README.md).

| Static synthetic view | Water pixels | Trace hits / changed display pixels | Maximum display-RGB difference |
|---|---:|---:|---:|
| Overhead, 20 degrees | 14,709 | 764 / 764 | 0.00523 |
| Oblique, 55 degrees | 13,408 | 1,047 / 1,047 | 0.02379 |
| Grazing, 80 degrees | 5,309 | 1,256 / 1,256 | 0.11770 |

The observed changes follow reflected wall/pillar/bank regions on water; the
overhead change is subtle and the grazing change is stronger in this fixture.
All surviving water fragments matched the independent CPU coverage mask. This is
an observation of one invented scene at one time, not a physical reference,
Minecraft result, temporal-stability result or performance measurement. It does
not establish hidden/off-screen geometry, night appearance or Iris binding/flip.

The final-source run records shader SHA-256
c5caa7e0d8a6149f53d4725fd5d492993f4182d9684e1c1fe44fa1358e58d34e.
Water coverage is checked per pixel and all off-water display pixels remain exact.
The [earlier development comparison](validation/W3_visual_preflight/report.json)
retains its older source digest; after the corner-precision correction all 13 PNGs
in these three fixed views are byte-identical to that earlier run. This observation
does not generalize to temporal stability under arbitrary camera motion.
Formal geometric/native validation is reported separately above. The blank matrix
below is still for actual Minecraft.

| Scene / camera | Question | Actual observation |
|---|---|---|
| Overhead shallow water | Does the bottom remain legible while reflected wall motion follows the normal? | |
| 30/60/80 degrees from the surface normal | Does reflection weighting grow coherently without abrupt hits? | |
| Near to far, camera dolly and orbit | Does the world stay attached while the screen-data coverage changes? | |
| Wall leaves screen, then returns | Does the reflection fall back without falsely retaining unseen geometry? | |
| Depth edge, thin pole and diagonal silhouette | Are invented thick hits or missing narrow features recorded? | |
| Glass/unknown surface and held hand in front | Does invalid foreground block a farther supported reflection? | |
| Camera-facing reflected ray / near-plane crossing | Is clipping finite and free of screen-wide streaks? | |
| 64 versus 128 steps, long projected ray | Is budget exhaustion a bounded miss, not a distant false hit? | |
| Sky style off, blend zero, dark inlet | Can supported local hits survive while sky fallback stays appropriately absent? | |
| Sunrise, sunset, moon, rain and dense fog | Are color continuity and the known missing reflected-segment fog visible? | |
| Different native water alpha / texture pack | Is alpha preserved, with its documented reflection attenuation? | |
| Underwater, waterfall, waterlogged and overlapping fluid | Do retained scope/ordering limits behave predictably? | |
| Static/moving waves, FOV and resolution changes | Is traversal shimmer or normal-induced instability visible? | |
| Matched GPU timing | What is the measured cost at each budget and water-screen coverage? | |

The [full water roadmap](WATER_ROADMAP.md) also tracks future flow, shoreline,
underwater and performance work; none is implied complete by a successful screen hit.
