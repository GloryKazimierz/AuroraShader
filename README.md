# MyShader

Milestone 1: a small Iris shader pack with neutral-by-default color controls.
All project files and Git history live in D:\MinecraftShaders\MyShader.
Minecraft discovers this directory through the MyShader directory junction in
C:\Users\Wang\AppData\Roaming\.minecraft\shaderpacks.

## Features and controls

Select MyShader in Iris, then open Shader Pack Settings.

| Control | Default | Meaning |
| --- | --- | --- |
| Exposure | 0 | Brightness in stops, using approximate gamma 2.2 |
| Saturation | 1 | 0 removes color, above 1 intensifies it |
| Contrast | 1 | Display-space contrast around 0.5 |
| Temperature | 0 | Negative cool, positive warm; not Kelvin |
| Tint | 0 | Negative green, positive magenta |
| Grayscale | Off | Weighted grayscale applied last |

Order: exposure -> temperature/tint -> saturation -> contrast -> grayscale.
Alpha is preserved. Neutral settings bypass all grading operations; the final
clamp is an identity for the default normalized scene buffer.
Settings are declared in shaders/lib/settings.glsl and exposed through
shaders.properties. Iris may save user option overrides beside the junction in
its existing C: Minecraft installation; that is launcher configuration, not a
second project copy.

## Rendering pipeline

1. Base-330 gbuffers programs draw opaque/cutout and translucent geometry.
   They use Minecraft textures, vertex colors and lightmaps. Entities retain
   their color overlay, and the sky retains Base-330's sky gradient.
2. Every geometry fragment program targets colortex0, the scene color buffer.
3. final samples the complete scene, applies optional grading, and writes to
   Minecraft's main output framebuffer. The HUD normally renders afterward.

There is no deferred or composite pass because no intermediate full-screen
operation is needed. There is no custom lighting, shadow map, bloom, SSR,
volumetric lighting, PBR or custom water.

## Structure

- shaders/gbuffers_*.vsh and .fsh: small Iris entry points; keep category names.
- shaders/lib/geometry/: shared Base-330 stage implementations. Identical
  stages share a file, while entity and sky behavior remain distinct.
- shaders/final.vsh and final.fsh: fullscreen output stage.
- shaders/lib/settings.glsl: editable defaults and allowed option values.
- shaders/lib/color.glsl: the color grading implementation.
- shaders/shaders.properties and lang/en_us.lang: settings UI and labels.
- LICENSE: retained Base-330 public-domain license.

## Baseline and compatibility

Geometry derives from shaderLABS/Base-330 by Balint:
https://github.com/shaderLABS/Base-330
Iris architecture and options:
https://shaders.properties/current/

Target: Iris on Fabric, with the locally installed Iris 1.10.5 / MC 1.21.11
as the first runtime test target. Uses GLSL 330 compatibility and Iris includes.
No external assets, libraries, build step or shader compiler installation.

Neutral color grading preserves the Base-330 input; Base-330 is not guaranteed
pixel-identical to vanilla. In particular its geometry shaders do not implement
vanilla distance fog, and sky/transparency or newer render categories can
differ. Test these before claiming full vanilla parity. Strong settings can
clip highlights in the LDR buffer. No HDR tone mapping or calibrated color
management is included. Other rendering mods and dimensions are unverified.

## Minecraft acceptance checklist

- Select MyShader; verify the shader loads without errors.
- Reset options: compare shaders-off versus MyShader in the same location.
- Inspect terrain, leaves, mobs, hurt overlays, held items, water/glass,
  enchanted items, clouds, sun/moon, rain, distance fog and underwater views.
- Check day/night, Nether and End, resize the window and reload the pack.
- Change each slider separately; confirm its direction and reset it.
- Enable grayscale; verify world colors disappear and HUD remains readable.
- Restore neutral defaults; verify no unwanted tint or brightness change.
- If loading fails, inspect Minecraft's latest.log for the first shader error.

Static checks do not replace the above in-game acceptance test.
The old MyFirstShader and composite-tutorial projects are historical and
must not be edited or deleted as part of this project.
