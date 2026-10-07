# Shadow Mapping Study Guide

This note is written for learning, code review, and graphics/rendering interviews.

## 1. What problem are we solving?

For a point on screen, we already know how bright it would be from Lambert lighting:

```text
NdotL = max(dot(N, L), 0)
```

But that does not answer a second question:

> Is the light actually able to reach this point?

A wall may face the sun while another wall blocks the sunlight.

Shadow mapping solves this by rendering the scene once from the light's viewpoint.

## 2. The core idea

Imagine the light is a camera.

It renders a depth image:

```text
shadow map = closest surface depth seen by the light
```

Later, when shading a visible pixel, transform that pixel into the light's coordinate
system and ask:

```text
receiver depth <= stored shadow-map depth ?
```

If yes, the receiver is visible to the light.
If no, something closer to the light blocked it.

## 3. The two passes

### Pass A: shadow pass

Render geometry from the light.

The important output is depth.

In this project, `shadow.fsh` is intentionally depth-only. Cutout textures such as
leaves may discard transparent fragments so their holes can appear in shadows.

### Pass B: camera/deferred lighting pass

For each visible receiver:

1. Read camera depth.
2. Reconstruct the receiver position.
3. Convert it into player/world-relative coordinates.
4. Transform it into light view space.
5. Transform it into light clip space.
6. Divide by w.
7. Convert NDC from [-1,1] to [0,1].
8. Compare against the shadow map.

That is the heart of `shadowVisibility()`.

## 4. Why coordinate spaces matter

Graphics bugs often come from mixing spaces.

The normal and light direction must be in compatible spaces before taking a dot
product.

Likewise, a receiver must be expressed in the coordinate system expected by the
light matrices before projecting it into the shadow map.

A strong interview habit is to say exactly which space each vector is in.

## 5. Why shadow acne happens

Depth values have finite precision.

The receiver's reconstructed depth may become microscopically greater than the stored
depth even when both describe the same surface.

That can self-shadow the surface and create dark speckles/stripes called shadow acne.

A simple fix:

```text
receiverDepth - bias <= storedDepth
```

But too much bias pushes the visible shadow away from the object. That artifact is
often called peter-panning.

This project currently uses a constant normalized-depth bias.

## 6. Hard shadows

Hard shadowing performs one comparison:

```text
visibility = compareShadow(uv)
```

Result:

- 1 = lit
- 0 = shadowed

It is cheap but exposes the discrete resolution of the shadow map.

## 7. Percentage-Closer Filtering (PCF)

PCF does not blur depth.

Instead, it performs multiple binary depth comparisons and averages the results.

For a 3x3 kernel:

```text
visibility =
    (C1 + C2 + ... + C9) / 9
```

A result such as 5/9 means five taps are lit and four are shadowed.

That creates a gray transition near the shadow boundary.

This distinction matters:

Correct:
```text
average(compare(receiverDepth, storedDepth_i))
```

Not the same:
```text
compare(receiverDepth, average(storedDepth_i))
```

## 8. 3x3 versus 5x5

3x3:

```text
9 samples
radius = 1 tap from center
```

5x5:

```text
25 samples
radius = 2 taps from center
```

5x5 usually smooths a wider area but costs substantially more shadow texture reads.

This is an example of a standard rendering trade-off:

```text
quality <-> bandwidth / texture samples / GPU time
```

## 9. What SHADOW_SOFTNESS means here

In this project, softness controls tap spacing:

```text
tapStepUV = texelSize * softness
```

It does not increase the number of samples.

For 5x5 with softness 1:

```text
-2 -1 0 +1 +2 texels
```

For softness 2:

```text
-4 -2 0 +2 +4 texels
```

So a larger softness samples a wider area, but it can introduce more light bleeding,
shimmer, and detached-looking edges.

## 10. Why this is not physically correct soft shadowing

Real area-light shadows depend on blocker distance and receiver distance.

Objects touching the ground should usually have sharp contact shadows; farther away,
the penumbra can widen.

Fixed-radius PCF does not model that geometry. It applies roughly the same filter
pattern everywhere.

Techniques such as PCSS try to estimate blocker distance and vary the filter radius.

## 11. Debugging checklist

When shadows look wrong, isolate the pipeline.

### Shadow does not appear

Check:

- shadow pass actually renders casters;
- shadow texture contains useful depth;
- receiver reconstruction is correct;
- light matrices are correct;
- SHADOWS_ENABLED is on;
- the receiver lies inside the shadow map.

### Shadow moves when camera rotates

Likely a coordinate-space/reconstruction error.

### Surface covered in dark stripes

Likely insufficient bias or precision issues.

### Shadow floats away from object

Likely excessive bias.

### Shadow edge shimmers

Possible causes:

- limited shadow-map resolution;
- unstable light projection;
- discrete PCF taps;
- camera/light movement;
- sampling pattern.

## 12. Files to read in this repository

Recommended order:

1. `shaders/shadow.vsh`
2. `shaders/shadow.fsh`
3. `shaders/lib/position.glsl`
4. `shaders/lib/shadow.glsl`
5. `shaders/lib/lighting.glsl`
6. `shaders/deferred.fsh`
7. `shaders/lib/shadow_settings.glsl`
8. `shaders/shaders.properties`

Do not try to memorize every line. Follow the data:

```text
geometry -> light depth
camera depth -> reconstructed receiver
receiver -> light coordinates
depth comparison -> visibility
visibility -> direct lighting
```

## From Brute Force PCF to Better Sampling

The Milestone 4 experiment deliberately uses a square grid so its cost and behavior
are easy to inspect. For an in-bounds receiver whose taps stay inside the map,
Hard evaluates one comparison, 3x3 evaluates nine, and 5x5 evaluates twenty-five.
Thus 5x5 has about 2.78 times the shadow-depth lookups of 3x3. This is a local
sampling-cost comparison, not a prediction that the whole game becomes 2.78 times
slower. Out-of-bounds taps return lit without fetching depth; compiler optimization
and GPU caching also affect actual work.

An N-by-N grid grows quadratically: 7x7 needs 49 taps, 9x9 needs 81, and 11x11 needs
121. Increasing tap spacing instead preserves the count but leaves wider gaps.
Neither approach creates missing geometric detail or estimates physical penumbra
width. Larger grids can hide aliasing while blurring contact shadows and putting
more pressure on texture sampling. The next learning question is therefore how
to distribute a limited sample budget more effectively. [NVIDIA's discussion of
PCF sampling and bandwidth](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-17-efficient-soft-edged-shadows-using)

### Poisson disks, rotation, and noise

Poisson disk sampling places irregular samples while enforcing a minimum separation
between them. Think of scattered points that cannot crowd too closely together:
the pattern covers an area without obvious rows and columns. The word "disk"
describes the exclusion neighborhood; a shadow filter can also choose a circular
sampling footprint. [Bridson's Poisson disk paper](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf)

Varying a kernel's rotation or sample locations between pixels can break up repeated
grid-like bands. It redistributes approximation error into noise rather than
eliminating that error. A carefully distributed small pattern can consequently
look better than a similarly sized grid, but sparse samples can still look grainy.
[NVIDIA's explanation of randomized PCF](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-17-efficient-soft-edged-shadows-using)

An engineering consequence is that changing the pattern every frame can turn
spatial noise into visible temporal shimmer. Even a fixed screen-space pattern
changes its relationship to moving geometry. Stability must be evaluated while
moving, not just in screenshots; randomization is not automatically an improvement.

### Three different problems beyond kernel size

**PCSS** searches for blockers, estimates their average distance, estimates the
penumbra from blocker/receiver/light geometry, then performs PCF with a varying
radius. It aims for sharper contact and broader distant shadows. It remains an
approximation and adds blocker-search cost. [NVIDIA's original PCSS paper](https://developer.download.nvidia.com/shaderlibrary/docs/shadow_PCSS.pdf)

**Slope-scaled bias** changes the depth offset according to how quickly surface
depth changes across the light's image. It helps slanted surfaces avoid false
self-shadowing without applying one large offset everywhere. Excessive bias still
detaches shadows; clamping and tuning remain necessary. This project retains its
constant bias. [Microsoft's depth-bias explanation](https://learn.microsoft.com/en-us/windows/win32/direct3d11/d3d10-graphics-programming-guide-output-merger-stage-depth-bias)

**Cascaded shadow maps** split the camera's viewing range and give each interval
its own shadow map. Near geometry receives denser shadow texels while distant
geometry retains coverage. This addresses resolution allocation and perspective
aliasing, not physical softness, and introduces cascade-transition and stability
concerns. [Microsoft's cascaded shadow-map guide](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/cascaded-shadow-maps)

Milestone 5 implements a fixed Poisson-style pattern. Rotation, PCSS,
slope-scaled bias and cascades remain study topics, not implemented features.

## Interview notes: ten concise answers

1. **How does shadow mapping work?** Render nearest depth from the light, project
   each visible receiver into that map, and compare its depth to determine whether
   another surface blocks the light.
2. **What coordinate systems are involved?** Here: camera UV/depth, camera NDC,
   reconstructed view space, Iris player-relative space, light view, light clip,
   light NDC, then shadow UV/depth. The homogeneous divide matters; adding absolute
   camera position would violate this pipeline's player-relative convention.
3. **What causes shadow acne?** Precision and sampling mismatches can make a
   surface fail its own visibility test. Bias supplies a tolerance.
4. **What causes peter-panning?** Excessive bias makes a shadow appear separated
   from its caster, particularly at contact points.
5. **What does PCF average?** Binary depth-comparison outcomes, not stored depths;
   the result is fractional visibility.
6. **Why does a larger kernel soften shadows?** It mixes lit and blocked
   comparisons across a wider neighborhood, widening the transition.
7. **What is the 3x3 versus 5x5 cost?** Nine versus twenty-five in-bounds depth
   lookups per filter evaluation, about 2.78 times as many; whole-frame timing
   requires measurement.
8. **Why isn't fixed-radius PCF physically correct?** Its footprint does not adapt
   to blocker separation and light size, so it does not reproduce contact hardening.
9. **Why might Poisson sampling need fewer samples?** Better distribution reduces
   structured artifacts, potentially trading recognizable bands for less obvious
   noise; quality and temporal stability are not guaranteed.
10. **When are cascades useful?** In large scenes with directional sunlight, where
    one map cannot provide both detailed nearby shadows and sufficient far coverage.

# Regular Grid vs Poisson Sampling

Sample count and sample distribution answer different questions: how many
comparisons are evaluated, and where those comparisons are placed. Moving the
same number of samples changes which portions of a shadow edge contribute to the
average, so equal counts do not imply equal images.

### Grid PCF

```text
x x x
x x x
x x x
```

Advantages: simple, predictable, easy to implement, and a useful educational
baseline. A 3x3 grid has nine taps; 5x5 has twenty-five.

Disadvantages: repeated rows and columns can create recognizable rectangular
structure. Increasing grid density while expanding the kernel quickly increases
the sample count: an N-by-N grid uses N squared taps.

### Poisson PCF

Conceptual illustration, not the exact shader offsets:

```text
    x      x

 x      x

       x       x

   x       x
```

Poisson disk sampling distributes points irregularly while maintaining a minimum
separation, avoiding excessive clustering. The exclusion disk between neighbors
and the overall filter footprint are separate ideas. [Bridson's paper](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf)

Milestone 5 uses eight fixed, separated offsets inside a unit disk with a
zero centroid after rounding, minimum separation about 0.6600, and maximum
radius about 0.98. It is a small Poisson-style pattern, not a runtime generator
or proof of an ideal distribution. Each tap uses:

```text
offsetUV = poissonOffset * texelSize * SHADOW_SOFTNESS
visibility = sum(compareShadow(center + offsetUV)) / 8
```

Advantages: a less regular pattern can hide structured artifacts and may give
pleasing results with relatively few taps. Disadvantages: it remains an
approximation with a fixed radius; it can still show noise, repeated artifacts,
or shimmer, and does not produce physically correct area-light shadows.
Irregular sampling changes how error appears; it does not remove that error.
[NVIDIA's PCF sampling discussion](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-17-efficient-soft-edged-shadows-using)

This implementation has no randomization or rotation between pixels or frames.
Its fixed pattern does not automatically decorrelate artifacts or improve motion
stability. Camera/light movement and integer texel selection can still cause
abrupt visibility changes, perceived as temporal shimmer.

### Compare both footprint and count

| Filter | Logical taps | Footprint at softness S, in shadow-map texels |
|---|---:|---|
| Hard | 1 | Center |
| 3x3 PCF | 9 | Axis extent S; corner radius sqrt(2) * S |
| 5x5 PCF | 25 | Axis extent 2 * S; corner radius sqrt(8) * S |
| Poisson PCF | 8 | Radius at most S |

Softness is grid spacing for 3x3/5x5 and a disk-radius multiplier for Poisson.
The same slider value gives different footprints, so the default comparison
changes more than distribution. Poisson may be narrower than the grids.

The shared comparison uses `texelFetch` after integer conversion. Several
fractional offsets can select the same texel, particularly with a small radius.
Eight calls therefore need not mean eight unique depth texels. At softness zero
all offsets collapse to the same center, preserving Hard's result.

Eight taps cost less logical sampling work than twenty-five, but are not
automatically faster for the whole frame. Cache reuse, repeated texels, compiler
optimization, screen coverage, CPU limits and other passes affect measured cost.
Use the blank Milestone 5 benchmark and inspect motion as well as still images.

### Why this is not PCSS

```text
Poisson PCF:
fixed filtering radius + irregular sample locations

PCSS:
blocker search + estimated blocker distance + variable penumbra radius
```

PCSS uses blocker/receiver separation and light size to estimate a filter radius,
aiming for sharper contact and softer shadows farther from a blocker. It adds
work and remains an approximation. Poisson PCF alone cannot infer contact
hardening. Poisson offsets could be used within PCSS, but the sample pattern is
not the penumbra model. [Original PCSS paper](https://developer.download.nvidia.com/shaderlibrary/docs/shadow_PCSS.pdf)

### Milestone 5 interview preparation

1. **What is Poisson Disk sampling?** An irregular distribution with a minimum
   separation between samples; it reduces clustering without imposing grid rows.
2. **Why can irregular samples reduce visible grid artifacts?** They break up
   repeated alignments, making sampling error less obviously structured. A fixed
   small pattern still has artifacts.
3. **Is Poisson sampling automatically faster than grid PCF?** No. Count,
   memory/cache behavior and the rest of the frame determine cost; measure it.
4. **Why might 8 Poisson samples sometimes look competitive with 25 grid samples?**
   Their distribution can hide structured errors with fewer taps. Quality is
   scene-dependent, and this project's same-softness footprints differ.
5. **What does PCF average?** Independent binary depth-comparison results, giving
   fractional visibility. It does not average stored depths before comparing.
6. **Why does changing sample distribution matter?** It changes which parts of
   the visibility neighborhood contribute, and therefore the filter's error and
   directional appearance, even at an equal count.
7. **What is temporal shimmer?** Visible flicker or crawling when motion changes
   discrete shadow samples between frames. Irregular positions alone do not fix it.
8. **Why does Poisson PCF not create physically correct soft shadows?** Its radius
   does not follow light size or blocker/receiver geometry; it filters one depth
   map rather than evaluating visibility over an area light.
9. **What would PCSS add on top of this?** A blocker search, average blocker-depth
   estimate, and distance-dependent filter radius for approximate contact hardening.
10. **What would temporal filtering potentially improve?** Reusing valid history
    could reduce noise and flicker, but needs reprojection and rejection to avoid
    ghosting. It is not implemented here.

## Updated one-minute implementation explanation

> I render a depth shadow map from the light. During deferred lighting I
> reconstruct each opaque receiver from camera depth, transform it through view,
> player-relative and light space, then compare its depth with the map. The
> visibility scales only direct Lambert light, preserving ambient and block
> lighting. Hard uses one comparison; grid PCF averages nine or twenty-five.
> Milestone 5 adds eight fixed irregular disk offsets to study distribution
> separately from count. Every tap uses the same bias and compares before
> averaging. I retain fixed-radius filtering and test quality, cost and camera
> motion rather than assuming Poisson is better or faster.
