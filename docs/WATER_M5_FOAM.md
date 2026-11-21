# Foam and sunlit water

[中文](WATER_M5_FOAM.zh-CN.md)

## Controls and rendering

`WATER_FOAM=0` is off, `1` is local evidence, `2` adds persistent high-quality coverage. Both active choices require the existing Water Optics capability/style/HDR/debug gates. Profiles do not change this option. The compositor applies foam after M1/M3 optical transport and before the unchanged bloom passes. It preserves scene alpha exactly. Underwater/lava views, invalid fronts, multiple water layers and overlay blockers fall back conservatively. M3B can later own underwater optics independently; M5 does not invent a submerged foam layer.

Local coverage has two sources:

- Compression of a declared horizontal material-flow map, not height or normal steepness masquerading as compression.
- Nearby known visible opaque geometry at approximately the water surface's height. Four projected samples around a 0.45-block ring must have matched W1 depth/color, a valid source share, zero transparent ownership and matching final/opaque depth. The measured XZ distance is a local supported-contact estimate, not a world shoreline distance field. A same-pixel bottom gap alone cannot create shore foam; hidden/off-screen shorelines remain unknown.

The flow map is `X(q,t)=q+1.5*s*sum(A_i*khat_i*cos(phi_i))`, using W2's six modes with fixed-footprint filtering. Its analytic 2-by-2 Jacobian and material velocity are evaluated directly. `1.5*sum(A_i*|kappa_i|)=0.1778662224`, so the map cannot fold; the determinant lower bound exceeds 0.675. Three bounded Newton steps find material coordinates at a visible surface point. Foam creation thresholds are artistic surrogates for compression, not a simulation of air entrainment. Minecraft vertices remain unchanged.

## Illumination

Foam uses diffuse albedo divided by pi, with separate sky, directional and local-lamp irradiance estimates. Directional light has a stable 2-by-2 shadow comparison evaluated at the water surface. Lamps and ambient sky survive directional shadowing. Light levels are an authored illumination approximation using existing Minecraft metadata; they are not reconstructed physical lumens. There is no emission or unconditional white term: zero sky/lamp illumination produces exactly zero foam radiance.

The foam color receives the same surface-to-camera atmospheric segment before mixing with the already resolved water color. The blend therefore does not apply camera fog twice. `water_shadow_bindings.glsl` shares all seven shadow uniforms and the bias helpers with optional M4 receivers, avoiding duplicate declarations. Each consumer includes it only inside its active gate.

## Persistent foam history

Only mode 2 declares/writes `colortex13` and `colortex14`:

| Target | Format | Payload |
| --- | --- | --- |
| 13 | RGBA16F | coverage, age, world-normal octahedral XY |
| 14 | RG32F | full-float window depth, exact `frameCounter+1` |

At 1920x1080, their two sides add **63.28125 MiB**, excluding all existing buffers and any driver overhead. Local mode adds neither attachment. An initial RGBA32F metadata design would have used about 95 MiB; normal/coverage quantization and removing redundant viewport fields save storage while preserving full-depth precision.

Every unsupported current pixel writes explicit zero invalid history. A nonzero consecutive-frame stamp rejects cleared, stale or skipped data, including the documented frame-counter wrap. Additional checks cover texture-size mismatch, finite values, age, camera translation/rotation cuts, changed projection, world-normal agreement and full-float previous depth against the current water plane at the historical pixel center. The footprint is point sampled; this is coverage persistence, not color TAA or a general temporal denoiser.

The modeled material point is moved to the previous wave phase and projected through the previous camera. Decay has a 0.65-second half-life and a 2.5-second age limit. Fresh local evidence always remains available when history fails. Age and advection use Iris's `frameTime`, which describes the previous frame duration; at varying cadence this is a constrained approximation, not exact simulation time. Half-float age/coverage quantization is measured in the tests.

Iris 1.10.5 for Minecraft 1.21.11 was inspected read-only with `javap`. Its render targets request a full clear at construction and resize. Upstream matching-branch code shows that this full clear ignores ordinary per-frame clear suppression and clears both sides: [RenderTargets](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/targets/RenderTargets.java), [ClearPassCreator](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/targets/ClearPassCreator.java), [pipeline ordering](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java). The zero-invalid stamp plus `textureSize` checks rely on that allocation/resize behavior; texture dimensions alone would not prove old content was cleared.

Persistent flipped targets are also copied from alternate to main at frame end in this Iris implementation. That adds full-screen bandwidth beyond storage and the shader itself: [FinalPassRenderer](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/pipeline/FinalPassRenderer.java). This is another reason to reserve persistence for the highest quality. Native tests exercise payloads and a readback-fed next frame, not Iris's actual allocation, copies or gameplay timing.

## Sunlight and moonlight

Enable **Sun and Moon Glints** under Water. The directional light reflects from a Beckmann distribution of small water facets. Its roughness includes the variance of wave slopes lost below pixel resolution. In clear weather this gives a narrow reflection; rain broadens the highlight and reduces its intensity. The moon uses a cooler source and changes with lunar phase. The shared surface shadow sample and camera-to-water atmosphere attenuate the glint. Foam then covers the corresponding share. A visible water surface can show glints even if its bed is unavailable.

Compare [the sun, full moon and rain](validation/WATER_GLINT_views.png) and [local foam and shadow](validation/WATER_FOAM_views.png). These are synthetic native GPU images. The [glint tests](validation/WATER_GLINT_GPU.json) measure BRDF reciprocity, normal-incidence Fresnel, lobe broadening and retained alpha. The [foam suite](validation/WATER_FOAM_GPU.json) covers independent finite differences, shoreline ownership, lighting, quantized history and camera motion. The [shared surface functions](validation/M5_interface_refactor.json) gave identical color, alpha and history in 14 before/after checks on the preceding integration. Repeat with `tools/validate_gpu.py --suite water-glints` or `--suite water-foam`.

In [three combined frames](validation/WATER_FOAM_GLINT_OVERLAP.json), foam attenuated 1,870 illuminated RGB channel samples and preserved alpha.
