# Chapter 5: Textures, Filtering, Mipmaps and Anisotropy

## 1. Texture sampling is a reconstruction problem

A texture is a discrete grid of texels, but shaders sample it using continuous UV
coordinates.

The texture unit must decide how to reconstruct a value from nearby texels.

Two common filters:

- nearest;
- linear/bilinear.

## 2. Nearest filtering

Nearest selects one texel.

Advantages:

- cheap/simple;
- sharp pixel-art look;
- no mixing across texels.

Disadvantages:

- blocky magnification;
- unstable minification.

AuroraShader uses `texelFetch` in several metadata/shadow paths precisely because
it wants exact discrete texels rather than filtered values.

## 3. Bilinear filtering

Bilinear filtering blends the four nearest texels within one mip level.

It improves magnification smoothness, but does not by itself solve texture
minification.

## 4. Minification is harder than magnification

When a texture is far away, one screen pixel may correspond to many texture texels.

Sampling only a few base-level texels can miss high-frequency information and create:

- shimmer;
- moire;
- crawling patterns;
- aliasing.

This motivates mipmaps.

## 5. Mipmaps

A mip chain stores progressively lower-resolution versions of the texture.

Example:

```text
1024x1024
512x512
256x256
...
1x1
```

The GPU selects a level of detail appropriate to the projected texture footprint.

Mipmaps are both:

- an anti-aliasing technique;
- often a performance/cache improvement.

## 6. Trilinear filtering

Trilinear filtering blends between two neighboring mip levels in addition to
bilinear filtering within each level.

This reduces visible transitions between mip levels.

## 7. Texture derivatives and LOD

Fragment shaders can estimate how quickly UV changes across neighboring fragments
using derivatives such as `dFdx` and `dFdy`.

Texture hardware uses related information to estimate the footprint and choose a
mip level.

This is why implicit texture sampling is naturally tied to fragment quads.

## 8. Anisotropic filtering

When viewing a textured surface at a grazing angle, the projected footprint can be
long and narrow rather than roughly square.

Ordinary isotropic mip selection can overblur or alias.

Anisotropic filtering samples a more appropriate elongated footprint, improving
oblique surfaces such as roads/floors viewed into the distance.

## 9. Wrap modes

Common addressing modes:

- repeat;
- clamp;
- mirror;
- border.

Incorrect wrap behavior can create visible seams or repeated shadow artifacts.

AuroraShader explicitly guards shadow-map boundaries instead of allowing unwanted
wrapping.

## 10. Color texture versus data texture

Not every texture contains color.

Examples of data textures:

- normals;
- roughness;
- depth;
- shadow maps;
- object IDs;
- light levels.

Data textures often should not receive color-space decoding such as sRGB.

This is a common interview and implementation pitfall.

## 11. Texture atlas issues

Minecraft heavily uses atlases.

Atlases can introduce:

- bleeding between neighboring tiles;
- mipmap edge contamination;
- padding requirements;
- derivative/LOD complications around tile boundaries.

Understanding atlases is useful for game rendering work.

## 12. Common interview questions

### What is a mipmap?

A prefiltered lower-resolution representation of a texture used to better match
the screen-space sampling footprint during minification.

### Why do mipmaps reduce aliasing?

They prefilter high-frequency detail before sampling many texels into a small
screen footprint.

### Bilinear versus trilinear?

Bilinear filters within one mip level; trilinear also blends between adjacent mip
levels.

### What does anisotropic filtering solve?

Quality loss when the texture footprint is highly elongated at grazing viewing
angles.

### Why use texelFetch?

When exact integer texel access is desired without normalized coordinates or
filtering.

## 13. AuroraShader connection

- G-buffer reads use exact texels to avoid mixing unrelated metadata.
- Shadow PCF intentionally implements filtering at the comparison-result level
  rather than simply bilinear-filtering raw depth.
- Shadow boundary checks prevent wrap artifacts.

These are practical texture-sampling design decisions.
