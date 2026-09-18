# Milestone 3A: basic hard shadow mapping

Status: static checks and user-confirmed Minecraft runtime testing passed.
Implementation branch: milestone-3-shadow-map.
No Milestone 3B work is included.

The user confirmed correct hard shadows, attachment to world geometry during
camera movement/rotation, direction changes with sun/time, preserved ambient
lighting in shadow, working visibility debug, and no major rendering issues.

## Pipeline

1. Iris renders terrain/cutouts and block entities through shadow.vsh/.fsh.
   In this pass ftransform uses Iris's LIGHT model-view/projection matrices.
   The depth-only fragment shader discards texture alpha below 0.1 and otherwise
   lets rasterization write gl_FragCoord.z automatically. No shadow-color
   outputs are written or sampled.
2. Iris's shadowtex1 holds caster depth without translucent geometry.
3. Existing gbuffers preserve scene color, view normals and block/sky levels.
4. deferred reads depthtex1, reconstructs each recorded receiver's position,
   transforms it into the shadow map, and performs ONE raw depth comparison.
5. Visibility multiplies only Milestone 2's direct Lambert term.
6. final applies existing color controls or displays the selected debug view.

No new G-buffer or position attachment is allocated. colortex0/1/2 keep their
Milestone 2 layout and formats, including the commented RGBA16/RG16 directives.

## Verified Iris interface

Installed environment inspected: iris-fabric-1.10.5+mc1.21.11.jar.
MatrixUniforms registers the gbuffer/shadow matrix families;
IrisSamplers registers depthtex1 and shadowtex1; ShaderProperties supports
shadowTerrain, shadowTranslucent, shadowEntities and shadowBlockEntities.

Receiver uniforms:
- depthtex1: camera depth before transparent geometry (valid in deferred).
- gbufferProjectionInverse: camera NDC -> homogeneous camera/view position.
- gbufferModelViewInverse: view -> Iris player/feet-relative world-oriented space.
- shadowModelView: that player-relative space -> light view.
- shadowProjection: light view -> light clip.
- shadowtex1: raw opaque/cutout shadow depth (sampler2D, not sampler2DShadow).
- shadowLightPosition: existing view-space sun/moon vector for Lambert lighting.

Caster built-ins:
- ftransform(), using the light model-view/projection bound by Iris.
- gl_MultiTexCoord0 / gl_TextureMatrix[0], gl_Color, and gtexture for alpha cutout.

References:
https://shaders.properties/current/reference/programs/shadow/
https://shaders.properties/current/reference/buffers/shadowtex/
https://shaders.properties/current/reference/buffers/depthtex/
https://shaders.properties/current/reference/uniforms/matrices/
https://shaders.properties/current/guides/your-first-shaderpack/4_shadows/
https://shaders.properties/current/reference/shadersproperties/ordering/

## Coordinate-space contract

The G-buffer normal stays in VIEW space. Position is reconstructed separately:

screenUV = (pixel + 0.5) / depthTextureSize
cameraNDC = vec3(screenUV, cameraDepth) * 2 - 1
viewH = gbufferProjectionInverse * vec4(cameraNDC, 1)
viewPosition = viewH.xyz / viewH.w
playerPosition = (gbufferModelViewInverse * vec4(viewPosition, 1)).xyz
lightClip = shadowProjection * shadowModelView * vec4(playerPosition, 1)
lightNDC = lightClip.xyz / lightClip.w
shadowCoord = lightNDC * 0.5 + 0.5

playerPosition is world-oriented but relative to Iris's player origin, NOT an
absolute world coordinate. Do not add cameraPosition before shadowModelView.
Both caster and receiver use the same undistorted light projection.

A sky depth of 1, nonpositive light clip w, or any shadow coordinate outside
[0,1) returns visibility 1. This avoids repeated/wrapped shadows outside the
single map; there is deliberately a hard coverage boundary and no fade.

## Map and comparison

Fixed shadowMapResolution = 2048 (2048 x 2048).
Fixed shadowDistance = 64.0 (Iris projection radius in blocks).
shadowHardwareFiltering = false. No cascades, distortion, mipmaps or PCF.
texelFetch selects exactly one raw texel:
storedDepth = shadowtex1[floor(shadowUV * shadowTextureSize)]

bias = SHADOW_BIAS
visibility = receiverShadowDepth - bias <= storedDepth ? 1 : 0

Default bias: 0.0002 in normalized shadow-depth units, NOT blocks.
Options: 0, 0.00005, 0.0001, 0.0002, 0.0005, 0.001, 0.002.
No normal offset or receiver-plane correction is applied.

lambert = AMBIENT_LIGHT + DIRECT_LIGHT * NdotL * visibility
weight = LIGHTING_STRENGTH * skyLevel * (1 - blockLevel)
sceneRGB *= mix(1, lambert, weight)

Ambient is not shadowed. Existing Minecraft lightmap color remains in sceneRGB
and is not applied again. Torch-dominated/no-skylight pixels keep the previous
cave-protection behavior. Already-black scene color is not artificially lifted.

Shadows Enabled = off returns visibility 1, restoring Milestone 2 lighting.
Raw depth debug can still request/render the map while application is disabled.
No new resolution or distance menu controls were added.

## Debug modes

0. Normal rendering, with existing grading.
1. View-space normals (unchanged).
2. Block/sky light levels (unchanged).
3. NdotL (unchanged; deliberately independent of shadow occlusion).
4. Entire raw shadowtex1 depth map stretched over the display. Grayscale depth
   [0,1], white = cleared/no caster. This is light-view imagery, not camera-view
   imagery. An orthographic depth map may look low-contrast; values are not
   normalized per frame or color graded. The map can shift as Iris follows the
   player; judge world attachment in modes 0 and 5.
5. Shadow visibility at reconstructed receiver positions: white lit, black
   shadowed. Invalid G-buffer surfaces are also black (no receiver). Turning
   shadows off makes valid receivers white. Out-of-map receivers are white.

Debug modes bypass Milestone 1 grading. Mode 5 uses pre-translucency depth;
late entity metadata may not match that snapshot, an inherited scope limitation.

## Files

Added:
- shaders/shadow.vsh: light-space caster transform, fixed map constants.
- shaders/shadow.fsh: alpha-cutout, depth-only caster.
- shaders/lib/position.glsl: reusable depth-to-view/player reconstruction.
- shaders/lib/shadow.glsl: light projection, bounds checks, one comparison,
  and raw-depth debug sampling.
- shaders/lib/shadow_settings.glsl: Shadows Enabled and Shadow Bias.
- docs/MILESTONE_3A.md: this document.

Changed:
- shaders/deferred.fsh: calculate receiver visibility for lighting.
- shaders/lib/lighting.glsl: multiply only direct diffuse by visibility.
- shaders/final.fsh: debug 4 and 5.
- shaders/lib/lighting_settings.glsl: extend DEBUG_VIEW values to 0-5.
- shaders/shaders.properties: expose controls and restrict caster categories.
- shaders/lang/en_us.lang: option labels and explanations.
- tools/validate.py: 19 programs, 6 debug states, shadows on/off, shadow-specific
  contracts, buffer-format regression and coordinate math checks.
- README.md: link to current milestone and distinguish the tested M2 baseline.

## Scope and likely limitations

- Priority is opaque terrain/blocks and straightforward block entities.
- Translucent terrain, entities and the player are disabled as CASTERS.
  Existing opaque entities can still RECEIVE shadows in deferred.
- Cutout terrain uses binary alpha; leaves may look harsh. No glass/water
  transmission, colored shadows or translucent shadow rendering.
- Hands, particles, water and other post-deferred draws remain baseline.
- Hard 2048 sampling gives jagged edges and possible temporal shimmer.
- No stabilization beyond Iris's own matrices; no filtering is implemented.
- Small bias causes acne; large bias causes detached shadows/light leaks.
  Grazing angles may need a larger bias than flat surfaces.
- A 64-block single orthographic map has limited coverage; missing off-map
  casters and hard transitions to unshadowed lighting are expected.
- Existing face shading/AO and LDR clipping from Milestone 2 remain.
- Night uses Iris's main moon direction; no physically based moon brightness.
  Sun/moon handoff may pop. Nether/End behavior remains unverified.

## Minecraft acceptance checklist

1. Reload MyShader. Check latest.log for shader compilation, missing uniforms
   or framebuffer errors. Static checks do not prove runtime success.
2. Use debug 0 and neutral color controls. Toggle Shadows Enabled off: confirm
   the Milestone 2 look. Toggle it on with bias 0.0002.
3. In an open daytime area, build a plain solid pillar and overhang above a
   flat surface. Confirm a crisp CAST shadow on the receiving ground, not
   merely darker block faces.
4. Strafe, walk forward/back, rotate, and change height around that scene.
   The shadow must stay attached to the same ground/caster relationship.
5. Observe changing world time and night. Shadows should follow the sun/moon.
6. Debug 4 should show the light-view scene in grayscale, not uniform white,
   garbage or the ordinary camera color scene. Empty areas may be white.
7. Debug 5 should show white lit ground and a black pillar/overhang shadow.
   Sky/invalid surfaces may be black; compare only valid solid receivers.
8. Verify debug 1-3 still work. NdotL may stay bright inside a cast shadow:
   it measures orientation, while mode 5 measures occlusion.
9. In normal mode inspect shadowed surfaces with/without nearby torches.
   Ambient must remain visible; caves must not become newly black.
10. Adjust bias down/up to distinguish acne from detachment, then reset to
    0.0002. Do not expect one value to solve every grazing-angle artifact.
11. Inspect cutout leaves, chests, glass/water and held items. Check documented
    caster exclusions, then resize/reload and walk toward the map boundary.
12. Test Nether/End separately; report issues rather than assuming support.
    Keep these checks for future regression testing; Milestone 3B is separate.

Failure clues: all white depth -> no casters/map; all black visibility -> bad
depth/space/bias; shadows following camera -> transform mismatch; stripes ->
acne; floating shadows -> excessive bias; edge cutoff -> finite map bounds.
