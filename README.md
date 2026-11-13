# AuroraShader

AuroraShader is growing into a rich fantasy shader pack: azure days, coral/gold
sunsets, indigo nights, and optional teal/violet aurora ribbons. The goal is
a coherent, playable visual style with configurable performance, developed in
small documented stages.

**Current development: Milestone 14 — Stable Water Reflection Waves**
on `codex/milestone-14-water-waves`, based on M13 commit `fd394d3`.
Three gentle analytic waves now vary the normal used for classified water's sky
reflection and Fresnel weight. The pattern follows world coordinates, with safe
negative/large camera anchors and periodic spatial/time phases. Original face
eligibility is retained while the reflection direction changes.

The existing Water page adds waves (on), strength (0.6) and motion (normal).
Off or strength zero returns the exact M13 reflection normal. Static selects a
fixed rippled pattern, not a flat surface. Integer wave frequencies tile every
128 blocks and share a 200-second base loop that joins across Iris's clock reset.
The maximum horizontal-water slope is bounded by about 0.07466212 at full strength.

Only reflection normals change: mesh positions, shorelines, alpha, depth, tint,
material classification, shadow casting and fog math remain unchanged. A shared
camera-anchor include relocates two existing declarations without changing them.
There are still 24 program pairs and no additional attachments or textures.
Runtime appearance, motion stability and GPU cost remain unmeasured.
See [M14 English learning notes](docs/MILESTONE_14.md) /
[M14 中文原理与学习说明](docs/MILESTONE_14.zh-CN.md).

**Water source foundation (M13):**
Vanilla water fluid geometry is explicitly classified by material ID and fluid
marker. Sky-lit water receives a gentle cyan color multiplier and an angle-dependent
blend of analytic Aurora sky color on upward-facing surfaces. Glass, lava, host
blocks, held items and unknown fluids retain their existing source paths.

The **Water Color and Sky Reflection** page offers style (default Aurora), tint
strength (0.35) and reflection strength (0.35). Style off or both strengths zero
restores the M12 source before its existing late fog. Tint is reduced by block
light; zero skylight disables both additions. Reflection also requires Aurora Sky
and follows Sky Blend, fading below the reflected horizon. Fluid cameras, legacy
scene mode, debug and unsupported blend states bypass the new water effect.

This is a source-color approximation: native alpha still attenuates the reflection.
It does not sample terrain, clouds, celestial discs or aurora, and adds no SSR,
refraction, waves, opacity change, geometry displacement or shadow behavior. No new
attachment or program pair is added. Runtime water classification and appearance
remain unconfirmed; waterlogged/flowing fluid support follows pinned Iris source.
See [M13 English learning notes](docs/MILESTONE_13.md) /
[M13 中文原理与学习说明](docs/MILESTONE_13.zh-CN.md).

**Cloud atmosphere foundation (M12):**
Native cloud geometry now receives a restrained warm twilight/cool night tint and
its own distance/height fog before ordinary blending. Original cloud coverage,
face shading, alpha and native draw/depth behavior are retained. This is cloud
composition, not a new noise field, volumetric cloud renderer or cloud shadow map.

The **Cloud Color and Atmosphere** page exposes style (default Aurora), color
strength (0.6) and cloud fog (on). Native M11 style disables the entire addition;
zero color strength disables only tint, while cloud fog also follows the global
fog switch. Legacy scene mode, debug, excluded environments and unsupported blend
states retain the original cloud source. No extra program or buffer is allocated.

The cloud path is based on documented matrix contracts and a pinned Iris 1.10.5 /
Minecraft 1.21.11 source snapshot; the currently installed runtime was not freshly
verified. Fast/Fancy/Sodium cloud appearance, overlap and cost remain unmeasured.
See [M12 English learning notes](docs/MILESTONE_12.md) /
[M12 中文原理与学习说明](docs/MILESTONE_12.zh-CN.md).

**Signature night foundation (M11):**
Optional teal cores and violet trails animate toward the northern night sky. They
use world-oriented directions, fade with daylight/rain/vision effects, and are
restricted to Iris's upper sky background. The original star/sun/moon paths, fog
palette, terrain lighting and bloom algorithm are unchanged.

The **Aurora Night Ribbons** page exposes enable, intensity and motion: defaults
are on, 0.6 and normal. Normal motion loops every 200 seconds; double is 100;
Frozen uses a fixed zero phase. Integer harmonics also join across Iris's
3600-second timer reset. Legacy scene/sky modes, debug views and zero intensity
bypass the effect. No extra texture, attachment or program pair is added.

This is a bounded artistic sky pattern, with no physical aurora volume, positional
parallax or terrain illumination. Runtime appearance and cost remain unmeasured.
A [CPU mathematical preview](docs/images/aurora-math-preview.png) isolates the
ribbon shape on a synthetic background; it is not a Minecraft screenshot.
See [M11 English learning notes](docs/MILESTONE_11.md) /
[M11 中文原理与学习说明](docs/MILESTONE_11.zh-CN.md).

**Controlled glow foundation (M10):**
Bright scene pixels are extracted before area downsampling, softened with two
separable 9-tap filters at half resolution, and added before final exposure and
tone mapping. The **Controlled Bloom** page exposes enable, strength, threshold
and soft transition. Defaults are on, 0.08, 1.0 and 0.5 respectively.

Bloom preserves scene alpha and bypasses legacy mode, debug views, off and zero
strength. It selects bright RGB, not material emissiveness, so sky and held items
can contribute. The fixed small kernel is the first controlled glow step, not a
multi-scale cinematic bloom. Two half-resolution RGBA16F scratch attachments and
four fullscreen passes are added; disabling the effect does not yet remove that
allocation/pass cost. Both viewport dimensions must be at least two pixels.
Appearance and GPU cost remain unmeasured in Minecraft/Iris.
See [M10 English learning notes](docs/MILESTONE_10.md) /
[M10 中文原理与学习说明](docs/MILESTONE_10.zh-CN.md).

**Atmosphere foundation (M9):**
Recorded opaque surfaces receive fog after deferred lighting. Known late terrain,
weather and particle sources receive fog before their original framebuffer blend.
The fog uses bounded height-dependent density, a clear near range, rain strength,
and the existing Aurora sky palette. It is an analytic atmosphere approximation,
not volumetric shadowing or physical multiple scattering.

The **Distance and Height Fog** page controls density, clear distance, reference
height, height scale and rain increase. Fog requires the linear scene mode;
`FOG_ENABLED=0` disables it. The default density is 0.006 per block, clear distance
24 blocks, reference height 64, height scale 64 and rain increase 1.
Camera skylight access, fluids, vision effects and dimension properties limit the
new fog. Hands, sky, clouds, glint/eye overlays and unresolved late entity paths
are outside this first fog scope. Unknown blend modes retain their source color.
See [M9 English learning notes](docs/MILESTONE_9.md) /
[M9 中文原理与学习说明](docs/MILESTONE_9.zh-CN.md).

**Scene color foundation (M8):**
The default scene path stores linear RGB in RGBA16F, composites geometry and
transparency in that space, and applies exposure, highlight mapping and display
encoding once in final. A prepare pass initializes background fog color correctly.

This is a scene-compositing foundation, not a physical material-lighting rewrite:
the existing Minecraft texture/tint/AO/lightmap product is decoded as one baked
display-like source. Its texture filtering and internal shading are retained.
Normal/light-level/depth data and alpha coverage are never gamma converted.

The **Scene Color and Highlights** page offers `SCENE_COLOR_MODE=0` for the M7
RGBA8 display path and `1` (default) for linear/HDR. `TONE_MAPPING=1` uses a
peak-based soft shoulder beginning at `TONEMAP_KNEE=0.6`; `0` clips instead.
Output is still SDR. Post-map artistic grading can clip extreme settings.
See [M8 English learning notes](docs/MILESTONE_8.md) /
[M8 中文原理与学习说明](docs/MILESTONE_8.zh-CN.md).

Sky and light colors follow solar elevation smoothly; vanilla stars, sun and moon
remain. M7 established their shared palette; M8 keeps that design while moving
scene storage and composition into linear light. Special blend paths such as
armor glint and emissive eyes still need Minecraft observation.

The user has authorized continuous development with code and learning notes
pushed together. Runtime observations remain pending where not supplied; they
are tracked separately and no longer block independent subsequent development.
Offline checks must never be reported as Minecraft/Iris runtime success.

Start with the [English roadmap](docs/AURORA_ROADMAP.md) /
[中文开发路线](docs/AURORA_ROADMAP.zh-CN.md) and
[M7 implementation and study notes](docs/MILESTONE_7.md) /
[M7 中文原理与测试说明](docs/MILESTONE_7.zh-CN.md).

The **Aurora Sky and Light** options page controls the palette. Set
`SCENE_COLOR_MODE=0`, `SKY_STYLE=0` and `LIGHT_PALETTE=0` for the older M6
rendering logic; sky blend and light color
strength also have zero-strength bypasses. Defaults are Aurora sky, sky blend 1,
sunset warmth 1, night sky brightness 1, Aurora light colors, color strength 0.6.
Zero skylight, full block light and excluded environments retain the original result;
partial block light smoothly reduces the new tint.

Repeatable checks (run from this D: checkout):

```text
python -B tools/validate.py
python -B tools/compile_glsl.py
git diff --check
```

The optional compiler check needs an installed `glslangValidator`; it does not
download tools or invoke Minecraft. Generated compiler inputs stay on the project
drive in a verified temporary directory and are removed after the check.

Defaults remain Constant `0.0002`, 3x3 PCF and softness `1.0`; the initial
Angle-Aware range is `0.0001` to `0.0005`. Hard / 3x3 / 5x5 / Poisson keep
1 / 9 / 25 / 8 comparisons and their existing distributions.

| Milestone | Feature |
|---|---|
| M1 | Color grading |
| M2 | Deferred Lambert lighting |
| M3A | Hard shadow mapping |
| M3B | 3x3 PCF |
| M4 | 3x3 vs 5x5 PCF experiment |
| M5 | Poisson PCF |
| M6 | Shadow Bias Robustness |
| M7 | Fantasy day/night sky and celestial light palette |
| M8 | Linear/HDR scene composition, exposure and soft highlight mapping |
| M9 | Distance/height/rain fog with explicit opaque and late-source composition |
| M10 | Half-resolution HDR bright-pixel bloom with separable filtering |
| M11 | Bounded world-oriented teal/violet night-sky ribbons |
| M12 | Native cloud day/night tint and per-fragment atmosphere |
| M13 | Classified water color and bounded analytic sky reflection |
| M14 | Periodic world-anchored wave normals for water reflection |

Read [Milestone 6 (English)](docs/MILESTONE_6.md) /
[中文说明](docs/MILESTONE_6.zh-CN.md), the
[bias study guide](docs/SHADOW_BIAS_STUDY_GUIDE.md) /
[中文学习指南](docs/SHADOW_BIAS_STUDY_GUIDE.zh-CN.md), and the
[blank runtime worksheet](docs/MILESTONE_6_BENCHMARK.md) /
[中文测试表](docs/MILESTONE_6_BENCHMARK.zh-CN.md).
The [M5 Poisson experiment](docs/MILESTONE_5.md) and
[shadow mapping study guide](docs/SHADOW_MAPPING_STUDY_GUIDE.md) remain available.
This work does not merge into main or modify historical milestone branches.

Current M14 checkout: `D:\MinecraftShaders\MyShader-pcf-kernels`. The original
`MyShader` junction still resolves to the separate sky worktree, so it does not
load this development branch. Follow the benchmark's test-profile setup to select the correct pack;
this task has not created a test instance or changed a junction.

Milestone 3B adds Hard/3x3 PCF selection and shadow softness and has passed
user-confirmed Minecraft runtime testing. See [Milestone 3B](docs/MILESTONE_3B.md).

Milestone 3A (basic hard shadows) has passed Minecraft runtime testing with Iris.
See [Milestone 3A](docs/MILESTONE_3A.md) for the current pipeline, controls,
limitations and acceptance checklist. Milestone 3B is the latest user-confirmed runtime-tested baseline.

The sections below document the tested Milestone 2 baseline.

Milestone 1 was tested successfully in Minecraft by the user.
Milestone 2 adds an educational deferred Lambert lighting pass and debug views;
it has passed runtime testing in Minecraft with Iris, confirmed by the user.

Project and Git history: D:\MinecraftShaders\MyShader.
The existing Minecraft junction is managed separately and must not be modified.
Historical MyFirstShader and composite-tutorial packs remain untouched.

## Pipeline and scope

1. Base-330 geometry still produces the same texture, vertex-color and lightmap
   product in colortex0. Entity overlays and alpha discard remain unchanged.
2. gbuffers_terrain, gbuffers_block and gbuffers_entities additionally record
   surface normals and lightmap levels. Other categories remain color-only.
3. deferred runs after most opaque/cutout geometry and before most translucency.
   It modulates valid recorded surfaces with ambient + Lambert lighting.
4. Water, glass, hands, particles, clouds and other later draws retain baseline
   shading. Entities submitted after deferred are not relit by that pass.
5. final retains Milestone 1 color grading in normal mode. Debug modes instead
   inspect the surface buffers directly, bypassing all color grading.

This is intentionally an opaque-surface teaching stage, not a replacement for
all Minecraft lighting. No shadow maps, bloom, SSAO, SSR, volumetrics, PBR, water
effects, custom clouds, scattering, ray tracing or temporal effects.

## G-buffer contract

| Attachment | Format | Meaning |
| --- | --- | --- |
| colortex0 | existing default RGBA | Already lightmapped scene color and alpha |
| colortex1 | RGBA16 normalized | RGB encoded VIEW-space normal; alpha validity |
| colortex2 | RG16 normalized | R block-light level, G sky-light level |

The third attachment is needed to retain two independent lightmap levels for
the requested debug view and to protect block-lit caves. No albedo, material,
specular or additional depth buffer is allocated.

Normals: model attribute gl_Normal -> gl_NormalMatrix * gl_Normal -> view space.
The normal matrix is inverse-transpose so surface directions transform correctly.
Fragment interpolation changes length; normalize before encoding:
encoded = normalize(normalView) * 0.5 + 0.5.
Decode with normalize(encoded * 2 - 1). Zero vectors are guarded.
RGBA16 reduces view-normal quantization. Invalid/background pixels clear to
(0.5, 0.5, 0.5, 0). Metadata blending is disabled per attachment.
Full-screen reads use texelFetch to avoid averaging adjacent surface normals.

Lightmap UV centers span 0.5/16 to 15.5/16:
levels = clamp((UV - 0.5/16) * 16/15, 0, 1).
This is Minecraft block/sky lighting information, not a physical irradiance
measurement or a separate sampled-lightmap texture.

## Directional lighting

shadowLightPosition is registered by CelestialUniforms in the installed
iris-fabric-1.10.5+mc1.21.11.jar. Iris documents it as the highest celestial
body's VIEW-space position (sun in daytime, moon at night).
L = normalize(shadowLightPosition), using the same space as N.

NdotL = max(dot(N, L), 0)
lambert = AMBIENT_LIGHT + DIRECT_LIGHT * NdotL
skyWeight = skyLevel * (1 - blockLevel)
factor = mix(1, lambert, LIGHTING_STRENGTH * skyWeight)
outputRGB = originalSceneRGB * factor

Defaults: strength 1, ambient 0.65, direct 0.55. At full skylight with no block
light, the factor ranges from 0.65 to 1.20. No skylight or maximum block light
gives factor 1. Original Minecraft lightmap contribution is already in scene
color and is NOT multiplied a second time. Originally dark caves remain dark;
the new pass does not extinguish existing torch light.

This is LDR/display-space artistic modulation of prelit color. Existing
Minecraft face shading/AO remains, so some double shading is expected.
There are no occlusion shadows. Skylight attenuates the effect but is not a
shadow test. Moon uses the same teaching strength as sun; no day/night energy
model. Nether/End celestial behavior is unverified; strength 0 is a fallback.

## Settings

Iris Shader Pack Settings exposes:
- DEBUG_VIEW: 0 scene, 1 view normals, 2 block/sky levels, 3 NdotL.
- LIGHTING_STRENGTH: 0 restores the Milestone 1 lighting baseline.
- AMBIENT_LIGHT and DIRECT_LIGHT: Lambert factors.

Debug 1 remaps decoded view normals to RGB. Colors change with camera rotation;
lighting should stay attached to world surfaces.
Debug 2: red = block light, green = skylight, yellow = both.
Debug 3: white faces the light, black faces away.
Black invalid pixels are expected for sky and categories without normal data.
Debug buffers represent recorded surfaces, not the final transparency composite:
water/held items can disappear in debug, revealing recorded geometry behind.
Late translucent entities can overwrite metadata; inspect opaque blocks first.

Milestone 1 controls and defaults remain: exposure 0 stops, saturation 1,
contrast 1, temperature 0, tint 0, grayscale off. They apply only in debug 0.
Order remains exposure -> temperature/tint -> saturation -> contrast -> grayscale.
Temperature/tint are artistic channel offsets, not Kelvin white balance.
Strong settings/lighting may clip the LDR output.

## Files

- shaders/gbuffers_*.fsh: terrain/block/entities opt into shared surface output.
- shaders/lib/geometry/lit_vertex.glsl: model-to-view normal transform.
- shaders/lib/geometry/{lit,entity}_fragment.glsl: original shading plus metadata.
- shaders/lib/gbuffer_write.glsl: MRT layout, normal validity and lightmap encoding.
- shaders/lib/normal.glsl: guarded normal encode/decode helpers.
- shaders/lib/lighting.glsl: view-space Lambert term and cave-safe modulation.
- shaders/lib/lighting_settings.glsl: new options; existing settings.glsl unchanged.
- shaders/deferred.*: lighting pass and explicit metadata buffer formats/clears.
- shaders/final.fsh: normal grading or raw debug visualization.
- shaders/shaders.properties and lang/en_us.lang: controls and metadata blending.
- tools/validate.py: read-only structural checks for all debug/grayscale variants.

## Validation

Run: python -B tools/validate.py
Checks include resolution/cycles, the limited preprocessor syntax used here,
stage interfaces, MRT outputs, option references and numerical invariants.
This is NOT a GLSL compiler and does not emulate Iris patching or GPU execution.
glslangValidator/glslc were not found on PATH. The user separately confirmed successful Minecraft/Iris runtime testing.

## Minecraft acceptance checklist

1. Reload MyShader; check latest.log for compilation/link/framebuffer errors.
2. Set DEBUG_VIEW=0, LIGHTING_STRENGTH=0 and neutral color controls.
   Confirm the Milestone 1 look; compare screenshots at an unchanged viewpoint.
3. Set strength=1. At morning/afternoon, inspect opposite faces of a plain block
   outdoors away from torches. Light-facing surfaces should brighten.
4. Rotate the camera around a stationary block: illumination must not rotate
   with the camera. Check day/night and the sun-to-moon transition.
5. Debug 1: inspect distinct face colors and smooth camera-relative changes.
   Check sky is black, leaves/cutout holes do not produce filled rectangles.
6. Debug 2: outdoors green, torch contribution red, overlap yellow. Walk into
   a cave and compare with/without a torch.
7. Debug 3: light-facing surfaces bright, opposite faces dark; camera rotation
   must not change NdotL on the same surface at a fixed time.
8. Return to debug 0: test a torch-lit cave at strength 0 and 1. No new blackout.
9. Inspect entities, chests, hurt overlays, leaves, glass, water, held items,
   enchanted items and particles. Later/transparent categories stay baseline.
10. Change exposure/saturation/tint and grayscale in debug 0; confirm they work.
    Debug 1-3 must stay independent of those controls.
11. Test rain, Nether/End, resize and reload. Watch for flicker/stale normals.
12. Restore preferred normal settings and record results when testing future changes.

Known inherited limitations include incomplete vanilla distance fog and
Base-330 differences in sky/transparency/newer rendering categories.

Base-330 by Balint (retained Unlicense): https://github.com/shaderLABS/Base-330
References:
https://shaders.properties/current/reference/attributes/gl_normal/
https://shaders.properties/current/reference/uniforms/world/
https://shaders.properties/current/reference/programs/deferred/
https://shaders.properties/current/reference/shadersproperties/rendering/
