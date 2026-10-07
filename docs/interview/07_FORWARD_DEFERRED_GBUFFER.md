# Chapter 7: Forward vs Deferred Rendering, MRT and G-buffer Design

## 1. Forward rendering

In a classic forward renderer, geometry is shaded as it is drawn.

Conceptually:

```text
for each object:
    transform vertices
    rasterize
    evaluate material + lights
    output final-ish color
```

Advantages:

- conceptually simple;
- works naturally with MSAA;
- transparent materials fit more naturally;
- less G-buffer memory bandwidth.

Potential disadvantage:

- many lights can cause repeated lighting work over objects/fragments.

## 2. Deferred rendering

Deferred shading splits geometry and lighting.

Geometry pass:

```text
write surface data to G-buffer
```

Lighting pass:

```text
read visible pixel data
evaluate lighting later
```

This can make many-light evaluation efficient because lighting operates over
screen-visible samples rather than re-shading every object for every light.

## 3. G-buffer contents

A full renderer may store:

- normal;
- albedo/base color;
- roughness;
- metallic;
- depth;
- material flags;
- emissive;
- motion vectors.

But every channel costs memory/bandwidth.

G-buffer design is a compression/layout problem, not simply "store everything."

## 4. MRT

Multiple Render Targets allow one fragment shader to write several attachments in
one geometry pass.

This is how a G-buffer is commonly produced.

AuroraShader writes:

- scene color;
- encoded normal/validity;
- block/sky light metadata.

## 5. Bandwidth trade-off

Deferred rendering can reduce repeated lighting work but increases memory traffic:

```text
geometry writes several G-buffer targets
+
lighting reads them again
```

At high resolution this bandwidth can be significant.

This is why "deferred is faster" is not universally true.

## 6. Transparency problem

Traditional deferred shading is awkward for transparency because a G-buffer normally
stores only one visible surface per pixel.

Transparent rendering can require multiple layers or ordering/compositing.

Many engines therefore render opaque geometry deferred and transparent objects
forward.

AuroraShader similarly leaves several later transparent categories outside the
deferred relighting path.

## 7. MSAA difficulty

Deferred rendering with MSAA can become expensive because each sample may need
surface attributes and potentially separate lighting decisions.

Forward rendering often integrates more naturally with hardware MSAA.

## 8. Forward+

Forward+ keeps forward material shading but first partitions the screen/view into
tiles or clusters and builds light lists.

Then each fragment considers only nearby/relevant lights.

It combines useful properties of forward shading with scalable many-light culling.

## 9. Clustered rendering

Clustered shading extends light culling into 3D screen/view-space clusters, often
including depth slices.

It improves light assignment for scenes with many lights distributed through depth.

## 10. Deferred lighting versus deferred shading

Terminology varies.

"Deferred shading" often means material/lighting evaluation is deferred after
writing a G-buffer.

"Deferred lighting" may refer to variants that defer only part of the lighting
pipeline.

In interviews, define what you mean instead of relying on labels.

## 11. Common interview questions

### Forward versus deferred?

Forward shades during geometry rendering; deferred first stores visible surface
data and evaluates lighting in later screen-space passes.

### Why deferred for many lights?

Lighting can be restricted to visible pixels and light volumes/tiles rather than
repeating full material-light work per object.

### Main deferred costs?

G-buffer memory, bandwidth, transparency complexity and MSAA complexity.

### What is MRT?

A fragment stage writing multiple render-target attachments in one pass.

### What is Forward+?

Forward shading combined with tiled/clustered light culling.

## 12. AuroraShader connection

Milestone 2 gives you a concrete small deferred example:

```text
geometry -> normal/light metadata -> deferred fullscreen Lambert
```

It is not a full deferred PBR renderer because colortex0 already contains Minecraft's
prelit color. State this limitation clearly in interviews.
