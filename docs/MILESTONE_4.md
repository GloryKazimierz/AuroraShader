# Milestone 4: PCF kernel-size experiment

Status: implementation reviewed and structural/numerical validation extended.
Minecraft/Iris runtime testing and measured benchmarks remain pending.

This milestone keeps the tested Milestone 3B shadow pipeline and adds one focused
experiment: compare Hard shadows, 3x3 PCF, and 5x5 PCF using the same receiver
reconstruction, shadow map, depth comparison, bias, caster scope, and lighting
equation.

## Goal

Understand the real trade-off between shadow quality and sampling cost.

- Hard: 1 comparison per eligible receiver.
- 3x3 PCF: up to 9 comparisons.
- 5x5 PCF: up to 25 comparisons.

The larger kernel does not create physically correct soft shadows. It only averages
more neighboring binary shadow tests, so edges become smoother/wider while the
shader performs more texture reads and comparisons.

## Implementation

`SHADOW_FILTER` now supports:

- 0 = Hard
- 1 = 3x3 PCF
- 2 = 5x5 PCF

The filter uses one shared loop:

```glsl
#if SHADOW_FILTER == 1
    const int kernelRadius = 1;
#else
    const int kernelRadius = 2;
#endif
```

For each tap:

```text
offset = (x, y) * texelSize * SHADOW_SOFTNESS
visibility += compareShadow(center + offset)
```

Then:

```text
finalVisibility = visibleTapCount / totalTapCount
```

For 3x3, x and y are -1..1, giving 9 samples.
For 5x5, x and y are -2..2, giving 25 samples.

## What stays unchanged

- 2048 x 2048 shadow map.
- Shadow coordinate reconstruction.
- Constant normalized-depth bias.
- Shadow caster scope.
- Ambient/block-light preservation.
- Debug shadow-visibility view.
- Out-of-bounds samples are treated as lit.

Keeping these fixed means the experiment isolates one variable: PCF kernel size.

## Expected visual result

At the same viewpoint:

1. Hard should have a sharp, stair-stepped edge.
2. 3x3 should produce a narrow gray transition.
3. 5x5 should produce a wider/smoother transition.
4. Increasing softness increases tap spacing, not tap count.
5. Softness 0 collapses every tap onto the center sample, so all modes should
   converge toward the hard result.

## Performance-learning section

| Mode | Logical taps | Shadow-depth lookups when all taps are inside the map |
|---|---:|---:|
| Hard | 1 | 1 |
| 3x3 PCF | 9 | 9 |
| 5x5 PCF | 25 | 25 |

These counts describe one filter evaluation on an eligible shaded pixel. They
exclude shadow-map rendering, camera depth/G-buffer reads and the rest of the
frame. Out-of-map taps return lit before fetching; early receiver rejection skips
filtering entirely. Softness zero still expresses 9/25 comparisons at one texel
in the source, although a driver may optimize repeated work.

This does **not** make the whole game 9x or 25x slower. Even the 25/9 ~= 2.78 ratio
between filters is a sampling-work ratio, not a frame-time prediction. CPU limits,
resolution, visible receivers, GPU cache reuse and other rendering passes affect
the measured result. FPS caps and VSync can hide differences.

Texture reads use sampling throughput and memory bandwidth, and their latency
must be hidden by other GPU work. Nearby PCF reads can benefit from texture caches,
but more taps still add comparison/accumulation work. At millions of pixels per
frame, a small per-pixel cost can consume a meaningful part of the frame budget.
At 60 FPS, the whole frame has approximately 16.7 ms; at 144 FPS, about 6.9 ms.
Measure stable frame time as well as FPS before trading performance for softer
edges. [NVIDIA's PCF discussion](https://developer.nvidia.com/gpugems/gpugems/part-ii-lighting-and-shadows/chapter-11-shadow-map-antialiasing)

Use the blank [benchmark worksheet](MILESTONE_4_BENCHMARK.md); no measurements
have been invented or collected by static validation.

## GLSL/Iris review and validation

No shader rewrite was needed. The GLSL 330 compatibility path uses integer loop
variables and a const integer radius selected by `#if SHADOW_FILTER`. Inclusive
bounds produce 9 or 25 comparisons. Hard compiles to one comparison and contains
no softness-dependent filter logic. There are no kernel arrays or dynamic kernel
bounds. `textureSize(sampler2D, 0)` provides integer dimensions; `texelFetch` reads
one depth texel at mip zero after the bounds guard. Visibility is averaged after
each binary comparison. [GLSL 3.30 specification](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.3.30.pdf)

The earlier numeric oracle still used 3x3 for every nonzero mode. It now tests all
three modes, the 1/9/25 tap counts, five softness values, lit/dark interiors, a
partial shadow edge (including 2/5 and 3/5 for 5x5), all map corners, and boundary
reads. Both filtered modes equal Hard at softness zero. Actual shader loop bounds
and accumulation are checked structurally against this contract.

Preservation checks use the fixed runtime-tested 3B commit
`5aa154dbce823e954f63d25f91f3acbb9566c9c9`, not a moving HEAD. They compare complete
shadow reconstruction/comparison functions, lighting, caster shaders/scope,
G-buffer writing, final/deferred stages and debug modes 0-5. UI values/defaults and
19 shader stage pairs across all filter/debug/softness combinations are checked.
The validator is **not** a GLSL compiler and does not run Iris or measure the GPU.

## Minecraft runtime checklist

1. Load the PCF branch checkout (see the benchmark worksheet setup), then reload
   the shader pack and check the log for compile/link errors.
2. Use normal rendering and keep bias at 0.0002.
3. Find a clear pillar/overhang shadow in daylight.
4. Screenshot Hard, 3x3, and 5x5 from exactly the same position.
5. Confirm 5x5 has a broader filtered edge than 3x3.
6. Test softness 0, 0.5, 1, 1.5, 2.
7. Confirm softness changes nothing in Hard mode.
8. Walk and rotate the camera; shadows must stay attached to geometry.
9. Change world time; shadows should track the light.
10. Check leaves, grazing surfaces, map boundaries, caves, and torch-lit areas.
11. Compare FPS/frame time for Hard vs 3x3 vs 5x5 in the same scene.
12. Record screenshots and approximate performance numbers.

## Interview connection

A good short explanation:

> A shadow map stores depth from the light's point of view. At shading time I
> transform the receiver into light space and compare its depth against the stored
> depth. Hard shadows use one comparison. PCF performs multiple nearby comparisons
> and averages the binary visibility values. A larger kernel improves filtering but
> increases texture-sampling cost.

## Next likely milestone

After this comparison, the next useful step is not automatically a larger kernel.
Better directions are:

- Poisson/rotated sampling to reduce grid-like patterns.
- Slope-scaled bias to reduce acne without excessive peter-panning.
- PCSS/contact hardening for distance-dependent softness.
- Cascaded shadow maps for larger outdoor scenes.
