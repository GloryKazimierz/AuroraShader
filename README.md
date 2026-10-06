# MyShader

Milestone 4 development is on `milestone-4-pcf-kernels`: it extends the tested
Milestone 3B shadow path with a selectable 5x5 PCF kernel for quality/cost
comparison. See [Milestone 4](docs/MILESTONE_4.md) and the
[Shadow Mapping Study Guide](docs/SHADOW_MAPPING_STUDY_GUIDE.md).

Milestone 3B adds Hard/3x3 PCF selection and shadow softness and has passed
user-confirmed Minecraft runtime testing. See [Milestone 3B](docs/MILESTONE_3B.md).

Milestone 3A (basic hard shadows) has passed Minecraft runtime testing with Iris.
See [Milestone 3A](docs/MILESTONE_3A.md) for the current pipeline, controls,
limitations and acceptance checklist. Milestone 3A remains the runtime-tested baseline.

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
