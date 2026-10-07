# Chapter 9: Advanced Shadow Mapping

## 1. The shadow map baseline

Shadow mapping answers visibility with a light-space depth comparison:

```text
receiverDepth <= storedDepth + tolerance
```

AuroraShader already covers hard shadow mapping, PCF, Poisson sampling and bias
fundamentals.

This chapter organizes the interview-level extensions.

## 2. Resolution and projection trade-offs

A finite shadow map allocates a finite number of texels over a finite region.

If coverage increases while resolution stays fixed:

> texel density decreases.

This creates blockier/jaggier shadows.

If coverage shrinks:

> nearby quality improves but distant casters may disappear.

This is a spatial allocation problem.

## 3. Perspective aliasing

For directional lights, a large orthographic shadow map often spends too many
texels far from the camera and too few near the viewer.

This mismatch between camera perspective and light-space allocation causes
perspective aliasing.

Cascaded Shadow Maps address this.

## 4. Cascaded Shadow Maps (CSM)

CSM splits the camera frustum into depth ranges:

```text
near cascade
mid cascade
far cascade
```

Each range receives its own shadow map or light projection.

Near cascades get high texel density; far cascades trade resolution for coverage.

Challenges:

- cascade split selection;
- transition seams;
- temporal stability;
- light-space snapping;
- memory and draw cost.

## 5. Stable cascades

If a light projection moves continuously with the camera, tiny camera movement can
shift shadow texels and cause shimmering.

Stabilization techniques quantize/snap the projection to the shadow texel grid.

This trades some flexibility for temporal stability.

## 6. Bias families

Common approaches:

- constant depth bias;
- slope-scaled depth bias;
- normal offset bias;
- receiver-plane depth bias.

No single method is perfect.

Bias solves self-shadowing robustness, not filtering quality.

## 7. PCF

Percentage-Closer Filtering:

```text
average(compare(receiverDepth, storedDepth_i))
```

Important:

- compare first;
- average visibility second.

Kernel size and sample distribution control quality/cost.

## 8. Poisson and stochastic patterns

Irregular patterns reduce obvious grid structure.

But randomizing patterns can convert structured spatial error into temporal noise.

Therefore stochastic sampling is often paired with temporal accumulation or
denoising.

## 9. PCSS

Percentage-Closer Soft Shadows add a blocker-search stage.

High-level process:

1. search nearby shadow samples for blockers;
2. estimate average blocker depth;
3. estimate penumbra width;
4. perform PCF with a variable radius.

Goal:

```text
contact -> sharp
farther from blocker -> softer
```

PCSS is still an approximation and costs more than fixed-radius PCF.

## 10. Variance Shadow Maps

Variance Shadow Maps store statistical moments of depth and estimate visibility
using a probability bound.

Potential advantages:

- filterable with ordinary linear filters;
- large soft kernels can be efficient.

Potential problems:

- light bleeding;
- numerical/variance issues.

Knowing the idea is often enough for interviews unless the role specifically
focuses on shadow techniques.

## 11. Exponential techniques

Exponential Shadow Maps and EVSM modify depth/moment representations to improve
filterability and reduce some variance-shadow artifacts.

They introduce their own precision/tuning trade-offs.

## 12. Ray-traced shadows

Ray tracing can test visibility directly along rays toward a light.

Advantages:

- natural geometric visibility;
- area-light sampling can create physically meaningful soft shadows.

Costs/challenges:

- traversal cost;
- sample count/noise;
- denoising;
- temporal stability;
- acceleration-structure management.

Raster shadow maps remain widely used because they are efficient and predictable.

## 13. Contact shadows

Screen-space or short ray techniques can add fine contact detail missing from a
low-resolution shadow map.

They usually complement, not replace, large-scale shadow maps.

## 14. Common interview questions

### Why CSM?

To allocate more shadow resolution near the camera while retaining distant coverage.

### Why do cascades shimmer?

Small camera/light-projection movement changes texel alignment in light space.

### PCF versus PCSS?

PCF uses a fixed sampling footprint; PCSS estimates blockers and varies filter
radius to approximate contact hardening.

### Why can VSM bleed light?

Its statistical bound can overestimate visibility when depth distributions contain
separated surfaces.

### Raster shadows versus ray-traced shadows?

Raster methods reuse projected depth maps; ray tracing directly queries geometric
visibility but has different performance/noise costs.

## 15. AuroraShader roadmap connection

Your learning sequence is now:

```text
Hard
-> 3x3 PCF
-> 5x5 PCF
-> Poisson PCF
-> better bias
-> PCSS
-> possibly CSM / temporal stability
```

That is a coherent progression from basic visibility to quality, robustness and
large-scene scalability.
