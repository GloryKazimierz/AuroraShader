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

## 13. Interview questions you should be able to answer

### What is shadow mapping?

Render depth from the light, then compare a receiver's light-space depth with the
stored depth to determine visibility.

### Why is shadow mapping view-independent?

The occlusion test is performed in the light's coordinate system, not from the
camera's perspective.

### What is PCF?

Multiple neighboring shadow comparisons averaged into a fractional visibility.

### Why does PCF soften an edge?

Near an edge, some taps are lit and some are blocked, so their average lies between
0 and 1.

### Why not just increase to a huge kernel?

Sampling cost grows quickly, blur can become excessive, and fixed-radius PCF still
does not produce physically correct contact hardening.

### What are shadow acne and peter-panning?

Acne is false self-shadowing from depth precision/comparison error. Bias reduces it.
Too much bias separates the shadow from the caster, producing peter-panning.

## 14. One-minute explanation of your implementation

> I first render a depth shadow map from the sun's viewpoint. During my deferred
> lighting pass, I reconstruct each opaque receiver's view-space position from the
> camera depth buffer, convert it into the coordinate system expected by the shadow
> matrices, project it into the shadow map, and compare its depth against the stored
> light depth. I apply the result only to the direct Lambert component, so ambient
> and Minecraft block lighting remain visible. I started with hard shadows, then
> implemented 3x3 PCF, and now I am comparing a 5x5 kernel to understand the
> image-quality versus sampling-cost trade-off.

If you can explain that paragraph naturally, you understand the important part of
this milestone.
