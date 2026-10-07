# Chapter 3: Rasterization, Interpolation, Depth and Precision

## 1. What rasterization actually does

After projection, the GPU has screen-space triangles. Rasterization determines
which samples are covered by each primitive and generates fragments.

A useful mental model is:

```text
triangle edges
-> coverage test
-> covered samples
-> interpolated attributes
-> fragment shader
```

Rasterization is the bridge between continuous triangle geometry and discrete pixels.

## 2. Barycentric coordinates

Inside a triangle, an attribute can be described using barycentric weights:

```text
P = a*A + b*B + c*C
a + b + c = 1
```

The same weights can interpolate colors, UVs, normals or other varyings.

This is the mathematical basis for interpolation across triangles.

## 3. Why naive interpolation breaks perspective

Screen-space linear interpolation of attributes such as texture UVs is wrong under
perspective projection.

Farther parts of a triangle shrink on screen. Therefore attributes need
perspective-correct interpolation.

Conceptually, the rasterizer interpolates attribute/w and 1/w, then reconstructs:

```text
attribute = interpolated(attribute / w) / interpolated(1 / w)
```

Modern GPUs normally do this automatically for default varyings.

## 4. Flat versus smooth interpolation

Not every value should be smoothly interpolated.

Examples:

- UV: normally smooth/perspective-correct;
- normal: normally interpolated then renormalized;
- material/object ID: usually flat;
- triangle ID: flat.

Using smooth interpolation for IDs creates meaningless fractional values.

## 5. Depth buffer

The depth buffer stores a depth value per sample/pixel.

Depth testing compares a candidate fragment with the existing depth value to decide
visibility.

With the common LESS test:

```text
newDepth < storedDepth -> pass
```

If it passes and depth writing is enabled, the new depth replaces the old depth.

## 6. Why draw order can become less important for opaque geometry

With depth testing, opaque geometry can often be submitted in many orders and still
produce correct visible surfaces.

However, order still matters for performance:

- front-to-back can reduce overdraw via early depth rejection;
- transparent blending often needs a specific ordering.

## 7. Early-Z

GPUs may perform depth testing before expensive fragment shading when safe.

This can reject hidden fragments early.

Certain shader behavior can inhibit or complicate early depth, such as writing
fragment depth or some forms of discard/side effects.

Interview lesson:

> Hidden geometry can still cost vertex/raster work, but early depth can save
> expensive fragment work.

## 8. Depth precision and z-fighting

Perspective depth is not distributed uniformly in world distance.

More precision is concentrated near the near plane.

When two surfaces produce nearly identical depth values, quantization can cause
unstable winners:

```text
z-fighting
```

It often appears as flickering or striped overlap.

## 9. Why the near plane matters so much

Moving the near plane unnecessarily close to zero can waste depth precision.

For perspective projection, the near/far ratio strongly influences useful depth
resolution.

Practical interview point:

> A farther near plane often improves depth precision much more than merely pushing
> the far plane slightly inward.

## 10. Reversed-Z

A common modern technique is reversed-Z:

- map near/far in the opposite depth direction;
- use a floating-point depth buffer;
- often use GREATER instead of LESS.

This can improve precision distribution because floating-point precision and
perspective mapping work more favorably together.

Exact setup depends on API conventions.

## 11. MSAA and samples

With multisample anti-aliasing, a pixel can contain multiple coverage/depth samples.

Rasterization tests coverage at multiple sample locations, while fragment shading
may or may not execute per sample depending on configuration.

MSAA mainly addresses polygon-edge aliasing. It does not automatically solve:

- shader aliasing;
- specular aliasing;
- texture minification;
- temporal aliasing.

## 12. Overdraw

Overdraw means the GPU shades or processes multiple fragments for the same final
screen region.

High overdraw is especially expensive when fragment shaders are heavy.

Typical causes:

- many overlapping objects;
- particles;
- foliage;
- transparent layers;
- poor draw ordering.

## 13. AuroraShader connection

- G-buffer metadata is read with exact texel addressing to avoid cross-surface
  interpolation in later passes.
- Shadow mapping relies on depth precision and comparisons.
- Shadow acne and z-fighting are related precision/comparison problems, though not
  identical.
- Cutout leaves use discard, which affects raster/depth behavior.

## 14. Common interview questions

### What are barycentric coordinates?

Weights relative to a triangle's vertices that sum to one and can interpolate
attributes over the triangle.

### Why is perspective-correct interpolation needed?

Because projected geometry is non-linear with depth; naive screen-linear attribute
interpolation distorts values such as texture coordinates.

### What causes z-fighting?

Two surfaces map to nearly indistinguishable depth values, so finite depth precision
causes unstable visibility results.

### How can depth precision be improved?

Use a sensible near plane, appropriate depth format, possibly reversed-Z, and avoid
unnecessary extreme near/far ratios.

### What is overdraw?

Multiple fragments are processed for screen regions where only the final visible
result matters.

## 15. What you must be able to explain

Explain the path:

```text
triangle -> coverage -> barycentric interpolation -> fragment -> depth test
```

Then explain why interpolation, depth precision and overdraw are three separate
issues.
