# Chapter 2: Coordinate Spaces and Matrices

## 1. Why spaces exist

The same point can be described relative to different coordinate systems.

Common spaces:

- local/model space;
- world space;
- view/camera space;
- clip space;
- NDC;
- screen/window space;
- tangent space;
- light space.

A rendering bug often happens because a vector is mathematically valid but is
interpreted in the wrong space.

## 2. Model space

Model-space coordinates are defined relative to the object itself.

A mesh can be authored around its local origin. The model transform places it
into the scene.

```text
worldPosition = Model * localPosition
```

## 3. World space

World space places all objects into one common scene coordinate system.

This is convenient for reasoning about absolute scene relationships, physics and
many lighting calculations.

Some engines use camera-relative/world-relative coordinates to improve precision
or fit engine conventions. Iris uses player-relative conventions in parts of the
shader pipeline, which is why AuroraShader must follow Iris's matrix contract.

## 4. View space

The view matrix transforms the scene so the camera becomes the reference frame.

Conceptually:

```text
viewPosition = View * worldPosition
```

After transformation, the camera is effectively at the origin looking along the
engine/API's view direction.

AuroraShader stores normals in view space and uses Iris's celestial light direction
in the same space.

## 5. Projection and clip space

Projection transforms the camera-space viewing volume into homogeneous clip space:

```text
clip = Projection * viewPosition
```

Perspective projection encodes depth-dependent scaling in `w`.

Then:

```text
ndc = clip.xyz / clip.w
```

This divide is essential. Forgetting or misusing it causes incorrect projection.

## 6. NDC and screen space

NDC is a normalized post-projection coordinate system.

The exact z range depends on graphics API conventions, but x/y are normalized
around the visible viewport.

Viewport mapping converts NDC into screen/window coordinates.

In shaders, texture UVs commonly use [0,1], so mappings such as:

```text
uv = ndc.xy * 0.5 + 0.5
```

are common.

## 7. Matrix order

Matrix multiplication is not commutative:

```text
A * B != B * A
```

The order expresses which transform happens first.

With the common column-vector convention:

```text
clip = P * V * M * local
```

means local is transformed by M first, then V, then P.

Do not memorize order without knowing the math convention used by the API/library.

## 8. Inverse matrices

An inverse reverses a transform.

If:

```text
clip = P * view
```

then conceptually:

```text
view = inverse(P) * clip
```

AuroraShader uses inverse projection and inverse model-view matrices to reconstruct
positions from camera depth.

## 9. Positions versus directions

Positions use homogeneous `w=1`; pure directions use `w=0`.

Why?

Translation should affect a point but not a direction.

```text
M * (position,1)  -> translation applies
M * (direction,0) -> translation cancels
```

This is a useful interview concept.

## 10. Light space

Shadow mapping introduces a second "camera": the light.

The receiver must be transformed into the light's view/projection space before it
can be compared against a shadow map.

AuroraShader:

```text
camera depth
-> reconstructed view position
-> player-relative position
-> light view
-> light clip
-> light NDC
-> shadow UV/depth
```

## 11. Why shadows can follow the camera

If the reconstructed receiver is in one convention while the shadow matrix expects
another, moving the camera changes the mismatch.

This often produces a classic symptom:

> shadows appear to slide or follow camera motion.

That is a space-consistency bug, not a filtering bug.

## 12. Common interview questions

### Why do we need multiple coordinate spaces?

Different operations are simplest or best defined relative to different frames:
object authoring, scene placement, camera viewing, projection, surface tangent
frames and light projection.

### What does the view matrix do?

It transforms world coordinates into the camera's coordinate frame.

### Why divide by w?

Perspective projection uses homogeneous coordinates; dividing by w converts clip
coordinates to normalized device coordinates.

### What is an inverse projection matrix used for?

Among other uses, reconstructing a view-space position from depth/NDC.

### Position versus direction in homogeneous coordinates?

Positions typically use w=1; direction vectors use w=0 so translation does not
affect them.

## 13. AuroraShader connection

Milestone 3A is your strongest coordinate-space interview example. You can explain
a receiver traveling through multiple spaces before the depth comparison.

## 14. What you must be able to draw

On paper, draw:

```text
Model -> World -> View -> Clip -> NDC -> Screen

Camera depth -> inverse Projection -> View
             -> inverse View/ModelView -> world-relative
             -> Light View -> Light Clip -> Shadow UV
```

If you can explain why each arrow exists, you understand the core topic.
