# Water M2: reflection footprint and known-occlusion fallback

Status: independently staged prerequisite, native OpenGL tested. This is a partial reflection-quality improvement, not a completed water renderer or a Minecraft runtime acceptance result.

## Behavior and scope

The existing opt-in `WATER_OPTICS=1` path now distinguishes a known reflection obstruction from an unresolved screen-space ray. The default remains off. Existing style/mode/debug/capability gates still apply; no new menu option, render target, pass, history or hardware ray-tracing dependency is introduced. The old W3 path remains selected when optical transport is inactive. Reflection strength zero, native alpha and camera-fog behavior are preserved.

A hit uses a unit-pixel radiance footprint only when neighboring matched scene records describe a continuous local plane. This softens moving bright edges while refusing depth steps, surface creases and invalid metadata. It does not solve unresolved wave/highlight variance, temporal aliasing or a material roughness lobe.

| Evidence | Result |
| --- | --- |
| An opaque roof has depth but no valid W1 radiance | Blocked: no analytic sky fallback through the roof. |
| A geometric hit has invalid directional-share metadata or zero color confidence | Known obstruction: return reflected energy to transmission instead of exposing sky. |
| Malformed payload/dimensions | Invalid: reject the sky replacement conservatively. |
| An intervening clear sky-depth pixel is followed by a valid wall | Continue tracing; the wall can still be hit. |
| Ray exits the image, exhausts its budget/range, or sees only clear depth | Unresolved, not proof of open sky. The existing local-sky-access approximation remains. |

The last row is a real limitation: off-screen geometry and unrecorded layers cannot be recovered from the available snapshot. Local sky light is an approximate fallback input, not a visibility oracle. SSR is screen-space ray traversal, not hardware RT or path tracing.

## APIs and bounded reads

`traceWaterSceneClassified(originView, directionView, hitPixel, hitView, hitRGB, hitDistance, hitConfidence, stepsTaken, outcome)` adds `UNRESOLVED=0`, `HIT=1`, `OCCLUDED=2`, `INVALID=3` under the active optical-transport gate. The original `traceWaterScene` API remains available. Traversal, hit positions and the previous confidence/depth conventions are unchanged.

`waterFilteredReflectionRadiance(hitPixel, hitView, nearestRadiance)` caches the hit and four axial controls, plus at most one diagonal. Each record checks color/validity, matching scene depth, stable opaque depth and directional-share validity. The bound is **six unique matched records, 24 explicit texture fetches**. Four one-sided tangent normals must agree (dot >= 0.99). Accepted contributions stay within the local plane tolerance `clamp(0.0005 * eyeDepth, 0.025, 0.15)` blocks. Missing/unsafe support falls back to the original hit color. There are no mip chains, large dynamic arrays or temporal feedback.

Reflection color is filtered before the existing water-to-reflector air-fog operation; surface-to-camera fog is still applied once. The filter does not mix pre-fog and camera-fogged snapshots.

## Verification

The retained [native report](validation/WATER_M2_reflections.json) records every staged shader SHA256 and the Intel Iris Xe / OpenGL 3.3 driver. It covers eight 64-phase footprint scenes, eight classified-ray fixtures, and the actual full-resolution composite against a synthetic roof/open pair.

- Horizontal, vertical and slanted bright edges: nearest RMS error 2.03225; filtered RMS 0.00000712–0.00001034 against an independently integrated pixel box. Largest frame step fell from 8 to 0.705185.
- Corner detail: nearest lost all subpixel coverage (RMS 1.32066); filtered RMS 0.00000525. This is recovered detail, not a claim that its frame step is smaller than a constant-zero nearest sample.
- Depth step, crease, invalid neighbor and constant-color controls: exact expected output.
- Known opaque roof: 1,399 owned pixels; contaminated-hit share: 154 pixels; both had exactly zero sky-leak error against transmission-only output. 1,326 corresponding unresolved/open pixels retained a distinguishable sky fallback.

Run the integrated suite and generate a fresh comparison plate with:

```powershell
python -B tools/validate_gpu.py --suite water-stability --debug-plate docs/validation/NEW_ROOF.png
```

Tests are synthetic native-driver evidence. Iris execution, gameplay appearance, whole-frame performance, other vendors and arbitrary resource packs remain unobserved. A separate performance pass owns miss-traversal cost; no FPS claim is made here.

## Deferred slope/highlight work

For the fixed affine pixel footprint, the six-mode tile/phase mean unresolved slope covariance is

`C = 0.5 * strength^2 * sum(A_i^2 * kappa_i * transpose(kappa_i) * (1 - F_i^2))`, with `kappa_i = 2*pi*k_i/128`.

Its trace is unresolved mean slope variance. This is exact for the full periodic phase/tile average with that fixed footprint; it is **not** exact instantaneous per-pixel variance. Independent 37-by-41 direct-gradient quadrature checks six footprint/strength combinations; [the audit](validation/WATER_M2_slope_variance.json) records the numerical error. Full unresolved variance at strength 1 is 0.00131016468374505. Strength enters quadratically. The test helper can reproduce this via `slope_variance_audit()` and future full native runs include it.

Mapping that variance to a specular/highlight lobe requires a declared BRDF, finite base roughness and directional treatment. It has not been implemented in M2. Neither the normal filter nor this radiance filter alone proves stable glints. No ownership alpha channel is repurposed in this change.

Compare the [roof, contaminated depth and open control](validation/WATER_M2_roofs.png) from left to right: previous output, filtered output and a 12× display difference. The [native driver report](validation/WATER_M2_GPU.json) records the source digest and measured pixel counts.

## Skipping empty reflection paths

An optional deferred pass records the nearest positive view depth in each 8×8 tile in an R32F image. A pixel with inconsistent color and depth invalidates the tile. Missing radiance on a known opaque surface still bounds the ray. The trace visits tiles until the furthest possible fine sample. It can return an unresolved miss only if the entire prefix passes strictly in front of every opaque sample. Ambiguous corners, uncovered edge tiles and possible hits use the original fine search. The additional full-HD double-buffered storage is approximately 0.25 MiB.

In the [720p timer fixture](validation/WATER_M2_BOUNDS_720p.json) on Intel Iris Xe, the 64-step composite fell from 32.780 to 16.268 ms with 1.465 ms for the tile pass. The full output matched byte for byte. This flat pool stresses missed rays. A dry scene can still pay for the tile pass when the option is on. These separate draw medians exclude the game frame, and other synthetic GPU work may affect timing. The [native comparison](validation/WATER_M2_BOUNDS_GPU.json) checks actual hits, thin or unknown blockers and viewport edges. Switch **Reflection Depth Bounds** off to compare the original traversal.

Iris supplies opaque depth at the deferred stage. [Iris depth buffer reference](https://shaders.properties/current/reference/buffers/depthtex/)
