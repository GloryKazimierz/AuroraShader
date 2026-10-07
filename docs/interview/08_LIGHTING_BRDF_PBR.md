# Chapter 8: Lighting, BRDF and PBR Fundamentals

## 1. Lighting is geometry plus material response

A lighting model answers how incoming light becomes outgoing light toward the camera.

Important directions:

- N: surface normal;
- L: direction toward light;
- V: direction toward viewer;
- H: halfway direction between L and V.

## 2. Lambert diffuse

Lambertian diffuse uses:

```text
max(N dot L, 0)
```

This captures foreshortening: a surface receives less irradiance as light arrives
at a grazing angle.

A physically normalized Lambert BRDF includes:

```text
albedo / pi
```

AuroraShader uses an artistic Lambert-like modulation rather than a physically
normalized BRDF.

## 3. Specular reflection

Specular depends strongly on view direction and surface microstructure.

Older models include Phong/Blinn-Phong.

Modern PBR commonly uses microfacet BRDFs.

## 4. What a BRDF is

BRDF stands for Bidirectional Reflectance Distribution Function.

It describes how much light arriving from one direction is reflected toward another
direction at a surface.

Conceptually:

```text
f_r(L, V)
```

A physically plausible BRDF should respect properties such as energy conservation
and reciprocity under appropriate assumptions.

## 5. Microfacet model

A common Cook-Torrance-style microfacet specular BRDF is built from:

```text
D * F * G
------------
4 (N dot L)(N dot V)
```

Where:

- D: normal distribution function;
- F: Fresnel term;
- G: geometry/masking-shadowing term.

Do not memorize only the formula. Know what each factor means.

## 6. Roughness

Roughness controls the distribution of microfacet orientations.

Low roughness:

- narrow, sharp specular highlight.

High roughness:

- broad, dimmer-looking highlight spread over more directions.

Roughness should not simply be interpreted as "specular intensity."

## 7. Fresnel

Reflectance depends on viewing angle.

Even many dielectric materials become highly reflective at grazing angles.

Schlick's approximation is widely used:

```text
F = F0 + (1 - F0)(1 - cosTheta)^5
```

## 8. Metallic workflow

In a common metallic-roughness PBR workflow:

Dielectric:

- base color mostly represents diffuse albedo;
- F0 is around a low material-specific reflectance.

Metal:

- little/no diffuse component;
- base color affects colored specular reflectance.

This is a workflow model, not a law that every engine encodes identically.

## 9. Energy conservation

A material should not reflect more energy than it receives.

In PBR, increasing specular reflection generally reduces available diffuse energy.

This is one reason physically based shading couples terms rather than independently
adding arbitrary diffuse and specular values.

## 10. Direct versus indirect lighting

Direct lighting arrives from explicit light sources without intermediate bounces.

Indirect lighting arrives after bouncing from other surfaces/environment.

Examples:

- ambient approximation;
- lightmaps;
- irradiance probes;
- environment maps;
- global illumination;
- path tracing.

AuroraShader's ambient term is an artistic approximation, not computed GI.

## 11. Image-based lighting

IBL uses environment maps to approximate incident light from many directions.

PBR IBL often uses:

- irradiance convolution for diffuse;
- prefiltered environment maps for specular;
- BRDF lookup integration.

This is a common next-level interview topic.

## 12. Common interview questions

### What is Lambert diffuse?

A cosine-weighted diffuse response based on max(N dot L,0), with normalized Lambert
BRDF commonly albedo/pi.

### What is a BRDF?

A function describing directional reflection from incoming light direction to
outgoing/view direction.

### What do D, F and G mean?

Microfacet distribution, Fresnel reflectance, and geometric masking/shadowing.

### Roughness versus metallic?

Roughness controls microfacet spread; metallic selects a different material
reflection behavior where colored specular dominates and diffuse is greatly reduced.

### Direct versus indirect light?

Direct comes from a light without scene bounces; indirect has interacted with the
environment/other surfaces.

## 13. AuroraShader connection

Milestone 2 gives you the simplest part of this ladder:

```text
N dot L -> Lambert-like directional modulation
```

A useful interview statement is:

> My current shader is intentionally not PBR. It uses a deferred educational
> Lambert term over Minecraft's already-lightmapped scene. I understand the next
> step would require separating material/albedo data and adding a BRDF rather than
> simply layering arbitrary specular terms.
