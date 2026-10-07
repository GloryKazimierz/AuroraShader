# Chapter 6: Color Spaces, Gamma, HDR and Tone Mapping

## 1. Why color space matters

RGB numbers are not automatically proportional to physical light.

Display images are commonly stored or presented with a non-linear transfer
function such as sRGB-like encoding.

Lighting math should generally operate in a linear-light representation.

## 2. Linear light versus display/gamma-encoded values

If two lights each contribute intensity 0.25 in linear space, their sum is 0.5.

Doing that arithmetic directly on gamma-encoded display values gives the wrong
physical relationship.

Therefore a common pipeline is:

```text
encoded texture color
-> decode to linear
-> lighting / blending / exposure
-> tone map
-> encode for display
```

## 3. sRGB textures

Color/albedo textures are often authored in sRGB-like space.

When marked correctly, GPU hardware can decode them to linear values on sampling.

But data textures such as:

- normals;
- roughness;
- metalness;
- depth;
- IDs;

should not receive sRGB decoding.

## 4. Gamma misconception

"Gamma correction" is often used loosely.

A better mental model is:

- input encoding/transfer function;
- linear-light rendering;
- output/display transfer function.

Using a single `pow(2.2)` approximation can be educational, but sRGB is actually a
piecewise transfer function.

AuroraShader Milestone 1 uses an approximate gamma conversion for exposure and
explicitly does not claim a full color-managed pipeline.

## 5. HDR

HDR rendering means the intermediate scene representation can store values beyond
the final display range.

Example:

```text
sun highlight = 20.0
white wall = 1.0
dark surface = 0.05
```

If the buffer clamps everything to [0,1] too early, information is lost.

Floating-point render targets such as FP16 are common for HDR scene color.

## 6. Tone mapping

Tone mapping compresses HDR scene-referred values into a displayable range while
trying to preserve useful contrast and appearance.

Simple operators include Reinhard-like compression. Filmic operators are designed
for more pleasing highlight rolloff.

Tone mapping is different from exposure:

- exposure scales scene intensity;
- tone mapping maps a large dynamic range into the display range.

## 7. Exposure

Exposure is often a multiplicative scale in linear light:

```text
linearColor *= 2^exposureStops
```

+1 stop approximately doubles intensity.

Automatic exposure estimates scene brightness and adapts this scale over time.

## 8. Why blending should usually be linear

Alpha blending color in encoded/gamma space can create incorrect dark or bright
results.

Conceptually, light/color contributions should be combined in linear space, then
encoded for display.

## 9. Premultiplied alpha

Two common alpha representations:

- straight alpha: RGB stores unassociated color;
- premultiplied alpha: RGB already multiplied by alpha.

Premultiplied alpha often behaves better for filtering/compositing and simplifies
some blend equations.

An interview may ask you to explain the difference rather than memorize API blend
factors.

## 10. Banding and precision

Low precision in smooth gradients can cause visible bands.

Solutions can include:

- higher precision render targets;
- dithering;
- carefully placed tone mapping;
- avoiding repeated quantization.

## 11. Common interview questions

### Why perform lighting in linear space?

Because physical light addition and multiplication correspond to linear values, not
display-encoded values.

### What is HDR rendering?

Keeping scene values in a range/format capable of representing intensities beyond
the final display range.

### Exposure versus tone mapping?

Exposure scales scene intensity; tone mapping compresses HDR dynamic range into a
displayable range.

### Why not apply sRGB decoding to normal maps?

Normals are numerical vector data, not encoded display color.

### What is premultiplied alpha?

RGB values are stored already multiplied by alpha, changing how interpolation and
compositing are interpreted.

## 12. AuroraShader connection

Milestone 1 demonstrates the topic but remains intentionally LDR:

- approximate gamma conversion for exposure;
- artistic temperature/tint;
- final clamp to [0,1];
- no HDR buffer or tone mapper.

A strong interview answer is to state both what you implemented and what remains
simplified.
