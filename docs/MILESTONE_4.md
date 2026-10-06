# Milestone 4: PCF kernel-size experiment

Status: implementation branch. Runtime testing in Minecraft is still required.

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

## Performance model

This milestone teaches an important graphics-engineering habit: estimate cost before
optimizing.

For one shaded receiver:

```text
Hard       ~  1 shadow depth lookup
3x3 PCF    ~  9 shadow depth lookups
5x5 PCF    ~ 25 shadow depth lookups
```

This does NOT mean 5x5 makes the whole game 25x slower. It means this particular
shadow lookup portion can require up to 25 samples per eligible pixel.

## Minecraft runtime checklist

1. Reload the shader pack and check the log for compile/link errors.
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
