# Milestone 1: Color Grading

Status: user-confirmed Minecraft runtime testing passed.

Milestone 1 establishes the simplest post-processing stage in AuroraShader:
modify the final scene color without changing geometry, lighting, depth, or the
Minecraft lightmap.

## Goal

Learn how a fullscreen post-process changes an already-rendered image.

This milestone exposes:

- Exposure
- Saturation
- Contrast
- Temperature
- Tint
- Optional grayscale

The neutral defaults reproduce the incoming scene as closely as possible.

## Pipeline

The important data flow is:

```text
Minecraft renders the scene
        |
        v
colortex0 contains scene color
        |
        v
final.fsh samples colortex0
        |
        v
gradeColor(scene.rgb)
        |
        v
final display color
```

Milestone 1 does not change object positions, normals, depth, shadows, or scene
lighting. It is a final color transformation.

## Exposure

Exposure is measured in stops.

Conceptually:

```text
+1 stop = about 2x linear light
-1 stop = about 0.5x linear light
```

The implementation approximately converts display-gamma RGB to linear space,
applies `exp2(EXPOSURE)`, then converts back:

```glsl
color = pow(max(color, vec3(0.0)), vec3(2.2));
color *= exp2(EXPOSURE);
color = pow(color, vec3(1.0 / 2.2));
```

This is educational gamma handling, not a full HDR color pipeline.

## Temperature and tint

The project uses artistic RGB channel scaling.

Temperature:

- negative -> cooler
- positive -> warmer

Tint:

- negative -> greener
- positive -> more magenta

This is not a calibrated Kelvin white-balance transform. It is intentionally a
simple artistic control.

## Saturation

The shader first computes luminance:

```text
gray = dot(color, (0.2126, 0.7152, 0.0722))
```

Then interpolates between grayscale and the original color:

```text
result = mix(gray, color, saturation)
```

Therefore:

- 0 = grayscale
- 1 = unchanged saturation
- >1 = more saturated

## Contrast

Contrast is adjusted around display mid-gray:

```text
result = (color - 0.5) * contrast + 0.5
```

Values above 1 increase contrast; values below 1 reduce it.

## Grayscale

The optional grayscale mode applies the luminance weighting after the other color
controls.

This makes it useful both as an artistic feature and as a simple shader-option
exercise.

## Processing order

The current order is:

```text
Exposure
-> Temperature / Tint
-> Saturation
-> Contrast
-> Grayscale
-> Clamp to [0,1]
```

Order matters because these transformations are not generally commutative.

## Important limitation: LDR

The final result is clamped to:

```text
[0, 1]
```

So aggressive exposure or contrast can clip highlights.

There is no HDR buffer, tone mapper, filmic curve, auto exposure, or color
management pipeline yet.

## What this milestone teaches

1. Fullscreen post-processing.
2. Reading a rendered color buffer.
3. Shader-pack settings exposed through `#define` options.
4. Simple color-space reasoning.
5. Why operation order matters.
6. The difference between artistic controls and physically calibrated transforms.
7. Why LDR clipping becomes a limitation.

## Files to read

Recommended order:

1. `shaders/lib/settings.glsl`
2. `shaders/lib/color.glsl`
3. `shaders/final.fsh`
4. `shaders/shaders.properties`
5. `shaders/lang/en_us.lang`

## Interview questions

### What is a post-process?

A fullscreen operation applied after the scene has already been rendered, usually
by sampling one or more render targets and producing a modified final image.

### Why apply exposure in linear space?

Light intensity is physically additive/multiplicative in linear space. Applying
exposure directly to gamma-encoded display values produces less meaningful results.

### What does one exposure stop mean?

A one-stop increase approximately doubles linear light; one stop down halves it.

### Why does processing order matter?

Operations such as contrast, saturation, and channel scaling do not generally
commute, so changing their order can change the final image.

### What is the limitation of clamping to [0,1]?

Values above the display range are lost, so bright details can clip instead of
being preserved for later tone mapping.

## One-minute explanation

> Milestone 1 is a fullscreen color-grading pass. I sample the rendered scene
> color and apply exposure, temperature/tint, saturation, contrast, and optional
> grayscale. The neutral settings preserve the input. Exposure is applied with an
> approximate gamma-to-linear conversion, while temperature and tint are artistic
> channel adjustments rather than calibrated white balance. The output is still
> LDR and clamped to [0,1], so strong grading can clip highlights.
