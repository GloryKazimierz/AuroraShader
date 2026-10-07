# Chapter 4: Normals, Normal Matrix and Tangent Space

## 1. What a normal represents

A surface normal represents orientation, not a location.

It is commonly used for:

- diffuse lighting;
- specular lighting;
- backface reasoning;
- normal mapping;
- geometric offsets and bias heuristics.

Normals should usually be unit length when used in lighting equations.

## 2. Why normals are not ordinary position vectors

A position tells where a point is.

A normal describes a plane orientation.

This distinction matters when transforms contain non-uniform scale.

Applying the same model matrix directly to a normal can make it no longer
perpendicular to the transformed surface.

## 3. The normal matrix

For a model/view linear transform M, normals are transformed using:

```text
NormalMatrix = transpose(inverse(M))
```

typically using the upper-left 3x3 linear portion.

Why?

Because normals must preserve the orthogonality relation with transformed tangent
vectors.

If scale is only uniform plus rotation, simpler transforms may appear to work, but
the inverse-transpose is the robust general rule.

## 4. Derivation intuition

Suppose a tangent T lies on the surface and normal N satisfies:

```text
N dot T = 0
```

After transforming the tangent by M, we need transformed normal N' such that:

```text
N' dot (M T) = 0
```

Using the inverse-transpose preserves this perpendicularity.

This is more useful to remember than memorizing the formula alone.

## 5. Why normals need renormalization

Even if vertex normals begin normalized, interpolation changes their length.

Therefore a fragment shader usually renormalizes interpolated normals before
lighting.

AuroraShader explicitly does this during encode/decode.

## 6. Normal encoding

A normal component naturally lies in [-1,1].

If stored in a normalized texture range [0,1]:

```text
encoded = N * 0.5 + 0.5
decoded = encoded * 2 - 1
```

Then normalize after decoding.

Higher precision formats reduce quantization error.

## 7. Face normal versus vertex normal

A face normal is constant for a flat triangle.

Vertex normals can be averaged across neighboring faces to produce smooth shading.

Therefore:

- geometry can remain faceted;
- lighting can appear smooth.

This is a key distinction between geometry and shading normals.

## 8. Tangent space

Tangent space is a local coordinate frame attached to a surface.

Common basis:

- T = tangent;
- B = bitangent;
- N = normal.

Together they form the TBN basis.

Normal maps usually store a normal in tangent space because this allows one texture
to work as an orientation perturbation over differently oriented surfaces.

## 9. From tangent-space normal to lighting space

A normal map produces a vector in tangent space.

To use it for lighting, transform it through the TBN basis into the chosen lighting
space, for example world or view space.

Conceptually:

```text
N_view = TBN_view * N_tangent
```

The exact handedness and bitangent construction must match how tangents were
generated.

## 10. Why normal maps look blue

A common tangent-space normal map stores a default flat normal near:

```text
(0,0,1)
```

Mapping [-1,1] to [0,1] gives approximately:

```text
(0.5,0.5,1.0)
```

which appears bluish.

## 11. Normal mapping does not change geometry silhouette

A normal map changes shading orientation, not actual geometry.

Therefore it does not:

- alter the real silhouette;
- produce true parallax;
- cast geometrically correct detailed shadows by itself.

This is a common interview distinction.

## 12. Common interview questions

### Why inverse-transpose for normals?

Because normals must remain perpendicular to transformed tangent planes, especially
under non-uniform scale.

### Why renormalize after interpolation?

Interpolation does not preserve unit vector length.

### What is tangent space?

A local surface basis formed around tangent, bitangent and normal directions.

### Why are normal maps usually blue?

A flat tangent-space normal points approximately +Z, encoded near RGB
(0.5,0.5,1).

### Does a normal map change geometry?

No. It changes the shading normal, not the actual mesh surface.

## 13. AuroraShader connection

Milestone 2 already transforms normals with `gl_NormalMatrix`, stores encoded
view-space normals and renormalizes them.

That is a concrete interview example of normal-space correctness.
