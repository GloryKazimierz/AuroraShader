# Milestone 2: Deferred Lambert Lighting

Status: user-confirmed Minecraft runtime testing passed.

Milestone 2 introduces the first real lighting pipeline in AuroraShader. Instead
of changing only final color, geometry passes now record extra per-pixel surface
information into a small G-buffer, and a later fullscreen deferred pass uses that
data to apply directional Lambert lighting.

## Goal

Learn these real-time rendering concepts:

- Multiple render targets (MRT)
- G-buffer design
- Normal encoding / decoding
- View-space lighting
- Deferred shading
- Lambert diffuse lighting
- Debug visualization
- Preserving Minecraft's existing lightmap behavior

## Pipeline

The high-level flow is:

```text
Geometry pass
  |
  +-> colortex0 = original scene color
  +-> colortex1 = encoded view-space normal + validity
  +-> colortex2 = block-light level + sky-light level
  |
  v
Deferred fullscreen pass
  |
  +-> read scene color
  +-> read normal
  +-> read light levels
  +-> compute N dot L
  +-> modulate directional lighting
  |
  v
Final pass
  |
  +-> normal scene or debug visualization
  +-> Milestone 1 color grading
```

## Why use a G-buffer?

A later fullscreen pass needs information that was available during geometry
rendering but would otherwise be lost.

For example, to compute directional lighting after geometry has already been
drawn, the shader still needs the surface normal.

So the geometry pass writes extra render targets.

Current contract:

| Attachment | Meaning |
|---|---|
| colortex0 | Existing scene color |
| colortex1 | Encoded view-space normal + valid flag |
| colortex2 | Block-light and sky-light levels |

This is a deliberately small educational G-buffer, not a full PBR deferred renderer.

## Multiple render targets

The geometry fragment shader writes several outputs in one pass:

```text
location 0 -> scene color
location 1 -> normal data
location 2 -> lightmap metadata
```

This is called MRT: Multiple Render Targets.

The important benefit is that one geometry rasterization can produce several
per-pixel buffers.

## View-space normals

The geometry vertex path transforms the normal into view space using:

```text
gl_NormalMatrix * gl_Normal
```

Normals are stored in view space so the directional light vector can also be
used in view space.

This avoids mixing coordinate systems during `dot(N, L)`.

## Why normalize normals again?

Vertex normals are normalized before interpolation, but interpolation across a
triangle does not preserve vector length.

Therefore the fragment normal should be normalized again before use or storage.

## Encoding normals

A normal contains signed values in approximately:

```text
[-1, 1]
```

The render target stores normalized positive values, so the shader maps:

```text
encoded = normal * 0.5 + 0.5
```

Decoding reverses it:

```text
normal = encoded * 2 - 1
```

Then normalize again.

## Validity flag

The alpha channel of `colortex1` marks whether a pixel contains valid surface
normal data.

This matters because sky/background pixels do not represent a normal-bearing
surface.

The deferred pass checks validity before applying lighting.

## Lightmap metadata

Minecraft already provides block-light and sky-light information.

Milestone 2 stores normalized versions of these two levels in `colortex2`.

Conceptually:

```text
R = block light
G = sky light
```

These are metadata for controlling the new lighting effect. They are not a new
physical irradiance buffer.

## Lambert lighting

The core diffuse term is:

```text
NdotL = max(dot(N, L), 0)
```

Interpretation:

- N points away from the surface.
- L points toward the light.
- dot product near 1 -> surface faces the light.
- dot product near 0 -> light is grazing the surface.
- negative -> light is behind the surface, clamped to 0.

Then:

```text
lambert = AMBIENT_LIGHT + DIRECT_LIGHT * NdotL
```

## Why preserve Minecraft lighting?

The scene color in `colortex0` is already affected by Minecraft's lightmap.

If the shader multiplied the lightmap again, it would double-apply that lighting.

Instead Milestone 2 treats the new Lambert term as an educational modulation of
the already-lit color.

The sky/block levels determine how strongly that modulation applies.

## Cave / torch protection

The project computes:

```text
skyWeight = skyLevel * (1 - blockLevel)
```

This means directional sunlight modulation is strongest where skylight is strong
and block light is weak.

Inside caves or near torches, the original Minecraft lighting is preserved more
strongly.

This prevents the new directional pass from making torch-lit caves incorrectly
black.

## Lighting equation

Conceptually:

```text
lambert = ambient + direct * NdotL
factor = mix(1, lambert, lightingStrength * skyWeight)
output = originalScene * factor
```

This is not a physically based BRDF. It is an educational deferred-lighting stage.

## Debug views

Milestone 2 provides debug modes for understanding the buffers.

### View-space normals

Displays normal direction as RGB.

Useful for checking:

- whether normals are valid;
- whether different faces have different directions;
- whether normal data moves correctly with the camera.

### Block / sky light

Shows:

```text
R = block light
G = sky light
```

Useful for understanding where the new lighting modulation should apply.

### NdotL

Shows the Lambert orientation term as grayscale.

White means the surface faces the light strongly; black means it faces away.

## texelFetch vs texture

Metadata buffers use `texelFetch` in the deferred pass.

Why?

Because interpolating normals across object silhouettes would mix unrelated
surfaces.

For a G-buffer, each screen pixel should generally retrieve the exact metadata
stored for that pixel.

## Important limitations

Milestone 2 is intentionally simple:

- no PBR material model;
- no albedo separation;
- no specular;
- no roughness/metalness;
- no shadows yet;
- no SSAO;
- no SSR;
- no HDR lighting;
- no physically correct sun/moon energy;
- some transparent/later-rendered categories stay on the baseline path.

## Files to read

Recommended order:

1. `shaders/lib/normal.glsl`
2. `shaders/lib/gbuffer_write.glsl`
3. geometry vertex/fragment shared code
4. `shaders/lib/lighting.glsl`
5. `shaders/deferred.fsh`
6. `shaders/final.fsh`
7. `shaders/lib/lighting_settings.glsl`

## Interview questions

### What is a G-buffer?

A set of screen-space render targets storing per-pixel geometric/material data for
later shading passes.

### Why use deferred lighting?

It separates geometry rendering from lighting, allowing a later pass to shade
pixels using stored surface data.

### Why must N and L use compatible coordinate spaces?

The dot product has geometric meaning only when both vectors are expressed in the
same coordinate basis.

### Why re-normalize interpolated normals?

Linear interpolation changes their magnitude, so the result is generally no
longer unit length.

### What is Lambert diffuse?

A simple diffuse model proportional to `max(dot(N,L),0)`.

### Why avoid filtering G-buffer normals across silhouettes?

It can blend unrelated surfaces and create incorrect directions near edges.

## One-minute explanation

> Milestone 2 adds a small deferred-rendering pipeline. During geometry rendering
> I keep the original scene color and also write view-space normals plus Minecraft
> block/sky light metadata into extra render targets. A later fullscreen deferred
> pass reads those buffers, computes a Lambert N dot L term using the celestial
> light direction in the same view space, and modulates the already-lightmapped
> scene. I preserve torch/cave lighting by reducing the new directional modulation
> where block light dominates. Debug views expose normals, light levels, and N dot L.
