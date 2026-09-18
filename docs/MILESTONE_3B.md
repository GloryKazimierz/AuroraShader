# Milestone 3B: 3x3 PCF shadows

Implemented on milestone-3b-pcf-shadows; user-confirmed Minecraft runtime testing passed.

Confirmed: Hard matches Milestone 3A, PCF softens edges, softness behaves as
expected, zero softness matches Hard, and Hard ignores softness. Debug 5 shows
gray transitions. Shadows stay attached during camera movement and follow
sun/time changes. Ambient/block lighting remains visible; no major runtime
rendering issues were observed.

The Milestone 3A coordinate transforms, map format/resolution, caster scope,
constant bias, G-buffer layout, and direct-only lighting equation are unchanged.

## Filtering

Both modes call the same compareShadow helper:
C(uv,z) = (z - SHADOW_BIAS <= depth(uv)) ? 1 : 0.
Hard uses C at the existing receiver coordinate.
PCF uses sum(C(uv + vec2(x,y) * softness / mapSize, z)) / 9,
for x,y in {-1,0,1}. It averages comparison RESULTS, never depth values.
texelFetch reads nearest discrete depth texels without hardware filtering.

mapSize comes from textureSize(shadowtex1, 0), currently 2048 x 2048.
texelSize = 1 / mapSize. Softness scales the sample spacing and kernel radius:
0 collapses all taps to center; 1 gives one texel spacing; 2 gives two.
Values: 0, 0.5, 1, 1.5, 2. Default: 3x3 PCF, softness 1.
Hard ignores softness. Fractional spacing can hit the same texel repeatedly;
this is intentionally simple point-sampled PCF, not smooth bilinear filtering.

The existing bounds check still treats receivers outside the map as lit.
Each out-of-bounds neighbor is also treated as lit; all nine weights remain.
This prevents invalid reads/wrapping but can brighten the coverage boundary.

## Lighting and debug

Only the direct-light visibility changes; ambient, block lighting and skylight
protection retain Milestone 3A behavior. Shadow Bias is unchanged at 0.0002.
Shadows Enabled off retains the existing bypass.

Modes 0-4 are unchanged. Debug 5 uses the same filtered visibility as deferred:
white fully lit, black fully shadowed, gray partial kernel coverage.
Invalid receiver pixels remain black. Raw shadow-depth mode 4 is untouched.
Visibility has discrete steps of 1/9 with point-sampled equal weights.

## Performance and limitations

Hard: one shadow-depth fetch/comparison per eligible in-bounds receiver.
PCF: nine comparison evaluations; in-bounds taps each fetch one depth texel.
Out-of-map taps return lit without a fetch. No additional render pass or buffer.
This is up to 9x the shadow lookup work, NOT 9x total frame time.
Debug 5 also evaluates visibility in final in addition to deferred; benchmark
normal mode 0 for ordinary rendering cost. No performance claims were measured.

Fixed-radius filtering softens edges but is not physical contact hardening.
Possible artifacts: stepped gray bands, shimmer, repeated taps at fractional
softness, larger-radius light bleeding/haloing, map-edge brightening, and
constant-bias acne at grazing angles. Increasing bias may detach shadows.
No 5x5, PCSS, rotated kernels, noise, temporal filtering or other new effects.

## Validation

python -B tools/validate.py
Covers all 19 program pairs, six debug modes, grayscale/shadows on/off, Hard/PCF
and five softness settings. Checks partial coverage, all-lit/all-dark regions,
zero-radius equivalence, boundary behavior, includes/interfaces/options, and
preservation of the tested position, lighting, G-buffer and caster code.
These are structural/numerical checks, not GPU compilation or runtime proof.

## Minecraft checklist

1. Reload the pack; check for compiler errors.
2. Use debug 0, shadows enabled, neutral color controls, bias 0.0002.
3. Select Hard; confirm the previous tested pillar/overhang shadows.
4. Switch to 3x3 PCF, softness 1, at the same viewpoint: edges should soften.
5. Debug 5: compare Hard's binary edge with PCF's gray transition. Solid lit and
   shadowed interiors should remain white and black.
6. Try softness 0, 0.5, 1, 1.5 and 2. Zero should match Hard; larger values should
   generally widen transitions. Fractional values may change in discrete steps.
7. Change softness in Hard mode; it should have no visible effect.
8. Walk/rotate around the caster and change world time. Shadows must stay
   attached to geometry; note any shimmer without assuming filtering fixes it.
9. Inspect shadowed/torch-lit regions. Ambient and block light must remain.
10. Confirm Shadows Enabled off, debug modes 1-4, and color controls still work.
11. Check leaves, map boundaries, grazing surfaces, reload and window resizing.
12. Compare FPS/frame time in mode 0 between Hard and PCF at the same scene.
    Restore PCF/softness 1/bias 0.0002 and record future regression-test results.

Changed files: shadow.glsl, shadow_settings.glsl, deferred.fsh, final.fsh,
shaders.properties, en_us.lang, tools/validate.py, README.md.
Added: this document. The junction and historical projects were not touched.
