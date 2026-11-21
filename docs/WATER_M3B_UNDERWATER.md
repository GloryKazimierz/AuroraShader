# M3B: observed finite underwater exits

Status: opt-in development module. Final real OpenGL synthetic producer/composite tests, full CPU checks and targeted offline compilation passed. Minecraft/Iris runtime appearance has not been observed.

`WATER_UNDERWATER=0 [0 1]` requires Water Optics, its existing per-buffer blending capability, and screen reflections. The Reflections and Caustics water profiles enable finite exits. It adds **no image targets or new texture allocation**: `colortex7` retains the filtered upward view normal and raw depth, while `colortex8.a` uses byte 1 to identify a water exit. Red remains the independent additive layer/blocker counter. Existing above-water optics and foam reject this nonzero alpha. No 11/12 allocation.

## What the code owns

The real geometry producer accepts one visible, nearly horizontal top water interface, with the camera in water and the interface above the camera ray. It preserves native source color and alpha exactly. Unknown blending, real bottom faces, sides, glass, multiple layers, foreground overlays, missing depth, lava, ceiling dimensions and vision effects retain the prior rendering.

The installed Sodium 0.8.4 and Iris 1.10.5 binaries were inspected read-only. Sodium reverses vertex order for a top backface; Iris recomputes the normal from those vertices. The producer therefore first uses `0.5-at_midBlock.y/64` to exclude genuine bottom faces (height <= 1/16 block), then orients either top-face normal upward. A single additional active-only varying carries that height. This is essential: a positive-Y-only synthetic fixture would miss the actual reversed water top.

`scatterWaterInterface` evaluates Snell's law, exact unpolarized dielectric Fresnel, water-to-air total internal reflection, and the radiance index-squared factor. The shared IOR is 1.333 (critical angle about 48.6066 degrees). TIR never constructs an air transmission ray. At any nonzero reflection setting, confirmed TIR uses F=1; zero explicitly disables this path and retains native rendering. Ordinary non-TIR reflections retain the artistic strength control.

Air transmission and underwater reflection use the existing bounded scene tracer and matched W1 radiance/depth. A source must also have a valid directional-share sentinel and no ambiguous transparency. Air hits must lie above the observed interface. Reflected hits must lie below it, and every crossed pixel of the reflected segment's vertical projection must match the finite, captured exit footprint at the same plane height. This extra check is bounded to 128 cells. It is a screen-sample certificate, not a reconstruction of hidden pool walls or disconnected fluid volumes.

Only confirmed water segments receive Beer extinction and source-dependent bounded scatter. A black source cannot emit new radiance. The underwater camera's blue fog color is never repurposed as air fog. The unobserved incoming sunlight-water leg and air-path atmosphere are deliberately not invented. Native alpha is unchanged, foam history rejects exit ownership, and bloom still runs once in its existing position.

## Honest limits

This is **not complete underwater rendering or a reconstructed waterline**. When the near plane clips away the top interface, there is no observed exit to shade; those pixels keep native water. The test sweep records that transition rather than filling a guessed infinite plane. At -1 cm in the authored test, some raster exits remain but no complete optical path qualifies; at -1 mm the interface is fully near-clipped. Nothing is inferred from player feet alone. Unsubmitted cave backfaces, off-screen sources, screen-trace misses, side exits, steep flow and unsupported volumes all remain native. TIR missing data can therefore still display the native approximation; that is not a claim that the boundary was rebuilt.

This does not add hardware ray tracing, a fluid simulation, vertex displacement, full volumetric transport, or an independent underwater sky model. Cost is unmeasured; there can be two bounded scene traces plus the finite-footprint walk. Default stays off.

## Interfaces and evidence

- `water_underwater_settings.glsl`: active-only option gate.
- `water_exit_capture.glsl`: actual fragment producer using top-height evidence.
- `water_interface_scatter.glsl`: pure `scatterWaterInterface(incident, incidentSideNormal, incidentIOR, transmittedIOR)`.
- `water_underwater_resolve.glsl`: `resolveWaterUnderwater(nativeRGB, pixel, size)` plus finite exit/trace validation.
- `composite.fsh`: calls this after above-water optics and before foam; alpha is copied unchanged.
- `tools/validate_gpu_water_underwater.py`: independent angle-space reference, actual geometry readback, finite-pool compositor, exact fallback and eight camera-height checks.

[Cumulative native GPU report](validation/WATER_UNDERWATER_GPU.json) · [Underwater exit comparison](validation/WATER_UNDERWATER_views.png).

Run from the project directory:

```
python -B tools/validate_gpu.py --suite water-underwater --cxx C:/msys64/ucrt64/bin/g++.exe --report docs/validation/NEW_EXIT_REPORT.json --debug-plate docs/validation/NEW_EXIT_VIEW.png
```

The PNG is an authored synthetic room, not a Minecraft screenshot. The suite tests 72 directional/IOR cases plus six invalid inputs; near the critical angle it bounds Fresnel's sensitivity with eight FP32 unit roundoffs in normalized cosine, rather than using a global loose tolerance. Actual MRT records test both top normal signs and true-bottom rejection. The camera sweep spans -0.20 to +0.20 m.

Primary references: [Iris at_midBlock](https://shaders.properties/current/reference/attributes/at_midblock/), [Iris status uniforms](https://shaders.properties/current/reference/uniforms/status/), [Iris camera coordinates](https://shaders.properties/current/reference/uniforms/camera/), [matching Iris 1.21.11 normal encoder](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/vertices/sodium/terrain/XHFPTerrainVertex.java), [Sodium fluid renderer](https://github.com/CaffeineMC/sodium/blob/dev/common/src/main/java/net/caffeinemc/mods/sodium/client/render/chunk/compile/pipeline/DefaultFluidRenderer.java), [PBRT dielectric interfaces](https://pbr-book.org/4ed/Reflection_Models/Specular_Reflection_and_Transmission). The Sodium linked branch is context; the installed 0.8.4 bytecode was checked independently for reversed vertex order.
