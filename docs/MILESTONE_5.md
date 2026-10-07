# Milestone 5: Poisson Disk PCF

Status: implementation on `milestone-5-poisson-pcf`. Minecraft/Iris runtime
testing and performance measurements are pending; static validation does not
establish either.

## What changed

Poisson Disk PCF is a fourth selectable shadow filter. It uses eight fixed,
irregular offsets inside a unit disk and the existing `compareShadow()` function.
No new control or debug view is needed: `SHADOW_SOFTNESS` sets the radius multiplier
and Debug 5 displays the resulting visibility.

| SHADOW_FILTER | Mode | Logical comparisons per filter evaluation |
|---:|---|---:|
| 0 | Hard | 1 |
| 1 | 3x3 PCF | 9 |
| 2 | 5x5 PCF | 25 |
| 3 | Poisson PCF | 8 |

Defaults remain 3x3 (`SHADOW_FILTER=1`), softness `1.0`, and bias `0.0002`.
Hard ignores softness. All three PCF modes match the center comparison at
softness zero.

## Why

Square grids place comparisons in repeated rows and columns. Their regularity can
appear as bands, repeated edge steps, or grid-like filtering. Irregular positions
offer a different distribution of the sampling error and may make that structure
less visible. Eight well-spaced taps can sometimes look competitive with a larger
grid, but this is a hypothesis to test in Minecraft, not a quality guarantee.
[NVIDIA's discussion of PCF sampling](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-17-efficient-soft-edged-shadows-using)

**Sample count** is how many comparisons the shader evaluates. **Sample
distribution** is where it puts those comparisons. Two filters with equal counts
can estimate visibility differently because their positions differ. This
milestone studies distribution rather than simply increasing the grid size.

## The fixed pattern

The eight literal offsets in `shaders/lib/shadow.glsl` are:

```text
(-0.6314, -0.5843)   ( 0.9208,  0.3354)
(-0.4122,  0.8516)   ( 0.5840, -0.7758)
( 0.0908,  0.0974)   (-0.8603,  0.1847)
( 0.4062,  0.8639)   (-0.0979, -0.9729)
```

They were selected offline using spaced candidates, recentered, and scaled into
the disk. After rounding, their centroid is zero, their minimum separation is
about 0.6600, and their largest radius is about 0.98. The near-center tap helps
cover the interior. Each lies within the unit disk. This is a small Poisson-style teaching pattern,
not an on-GPU Poisson disk generator or a claim of an optimal blue-noise pattern.
Poisson disk sampling is generally defined by irregular points with an exclusion
distance between neighbors. [Bridson's paper](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf)

For every literal offset:

```text
texelSize = 1 / shadowMapDimensions
offsetUV = poissonOffset * texelSize * SHADOW_SOFTNESS
visibility += compareShadow(centerUV + offsetUV, receiverDepth, mapSize)
result = visibility / 8
```

Each tap applies the existing depth bias and produces 0 or 1. The filter averages
these comparison results, never the stored depths. It has no rotation,
per-pixel randomization, frame seed, extra texture, or history buffer. Explicit
GLSL 330-compatible expressions keep the implementation easy to inspect.

The same softness value does **not** give every mode the same footprint:

| Mode | Footprint before discrete texel lookup, with softness S |
|---|---|
| Hard | Center only |
| 3x3 | Square: axis extent S, farthest corner sqrt(2) * S |
| 5x5 | Square: axis extent 2 * S, farthest corner sqrt(8) * S |
| Poisson | Disk: every offset has radius at most S |

Distances above are in shadow-map texels. Consequently the prescribed same-setting
comparison changes footprint as well as distribution and count; it is not a
matched-radius experiment. Poisson can look narrower than 5x5 without being a
worse implementation.

`compareShadow()` converts UVs to integer texels and uses `texelFetch`. Fractional
offsets can land on the same texel, so eight logical taps do not guarantee eight
unique depth texels, especially at small softness. Quantization can still produce
steps and shimmer. Reusing one fixed pattern does not solve temporal aliasing.

## Preserved pipeline and costs

Receiver reconstruction, player/view/light transforms, shadow-map generation,
caster scope, constant bias, lighting equation, ambient/block-light protection,
and Debug 0-5 retain the Milestone 4 behavior. Modes 0/1/2 keep their existing
code paths. Debug 4 remains raw depth; Debug 5 shows binary Hard visibility or
fractional filtered visibility. Only directional light receives the shadow factor.

The 1/9/25/8 counts describe comparisons for an eligible receiver, with that many
depth lookups when every tap is inside the map. Out-of-map taps return lit without
a depth read. Early receiver rejection skips filtering. Repeated texels,
compiler optimizations, cache behavior, other passes, CPU limits, and FPS caps
affect actual cost. Eight versus twenty-five taps is not a whole-frame speedup
prediction; do not call Poisson faster or better until measurements support it.

## This is not PCSS

```text
Poisson PCF = fixed user-selected radius + irregular sample locations
PCSS = blocker search + estimated blocker distance + variable penumbra radius
```

PCSS estimates how the filter radius should grow with receiver/blocker separation,
aiming for sharper contact and softer shadows farther from the blocker. This
Poisson mode has no blocker search and does not provide contact hardening or
physically correct area-light shadows. [Original PCSS paper](https://developer.download.nvidia.com/shaderlibrary/docs/shadow_PCSS.pdf)

PCSS, cascades, temporal filtering, ray tracing, and temporal accumulation remain
outside this milestone.

## Validation and runtime testing

Run `python -B tools/validate.py`. The structural/numerical checks cover option 3,
eight comparison taps and their pattern, visibility bounds, all-lit/all-shadowed
inputs, softness zero, existing grid modes, preserved transforms and lighting,
and valid UI references. This script is not a GLSL compiler or an Iris/GPU test.

Use [the Milestone 5 benchmark and runtime checklist](MILESTONE_5_BENCHMARK.md).
First comparison: shadows enabled, Debug 0, softness `1.0`, bias `0.0002`, neutral
color grading, and otherwise unchanged defaults. Switch only the filter through
Hard, 3x3, 5x5, and Poisson. Repeat in Debug 5 for visibility inspection, then
return to Debug 0 for timing. Record actual results before claiming runtime success.

The checkout is `D:\MinecraftShaders\MyShader-pcf-kernels`. The existing
`MyShader` junction still points to the separate sky experiment. See the benchmark
setup before choosing a pack; no test instance or junction is created by this
milestone.
