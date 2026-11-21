# Water M4: shadow-space caustics with M3 refraction

This opt-in effect runs on observed sunlit beds beneath water. The shadow pass includes translucent terrain while caustics are active. Ordinary terrain shadows continue sampling the opaque depth copy.

## What the effect computes

The shadow pass captures only classified upward-facing water, using the shared world-anchored filtered wave normal. The consumer solves a bounded local Snell mapping onto a horizontal opaque receiver. The inverse finite-area Jacobian redistributes only the recorded custom directional-light share q times lit radiance. Ambient light, lamps, and the bounded scatter source are unchanged. Incoming-water Beer attenuation and the eye-water Beer attenuation each occur once.

The same-ray fallback reads its actual opaque position, normal and directional share. M3 reads each refracted hit's position, fitted receiver normal, sampled radiance and directional share. RGB dispersion evaluates its three independently selected endpoints and uses the matching channel IOR for the caustic light path. A failed target retains the existing conservative fallback; it never borrows the screen source's q for a displaced hit.

## Storage and ownership

The selected shadowcolor0 format is RGBA16 UNORM. R/G contain signed horizontal slopes with an exact flat-normal code; B/A contain two 16-bit halves of a captured raw depth word. All-zero metadata is invalid. The actual shadowtex0 depth supplies reconstructed geometry; the packed depth only establishes ownership within one D24 step. The shader rejects overflow, nonfinite values, opaque replacement, missing water, unmatched dimensions, invalid normals, map borders, inconsistent receiver height, and inconsistent source-footprint bed height. The conditional shadow pass preserves original depth and alpha cutout behavior.

At 2048 square, two RGBA16 sides cost a nominal 64 MiB. RGBA8 would cost 32 MiB but failed the declared gain/temporal-residual quality tests; RGBA32F is retained only as a 128 MiB test reference. Actual Iris allocation is not measured. No new colortex is used. The shared water_shadow_bindings.glsl header is compatible with the separate M5 foam integration.

## Filtering and bounds

Four inverse-map refinements are followed by one landing check and four finite-area samples. Worst-case extra shadow reads are 109 before GPU cache reuse. Invalid/folded mappings return gain 1; valid flux is capped at 4. Depth fades from 8 to 24 meters. The receiver's camera footprint is reconstructed analytically, without divergent fragment derivatives. A conservative shortest-wave Nyquist fade suppresses unresolved distant or grazing detail before shadow lookup. It is not the full refracted ray-bundle Jacobian.

WATER_CAUSTICS defaults to 0. WATER_CAUSTICS_STRENGTH zero, WATER_WAVES zero, and WATER_WAVE_STRENGTH zero preserve the unmodified optical result. The active path also requires optics, HDR/debug0, supported per-buffer blending, water style and enabled shadows. Existing debug modes remain unchanged.

## Honest limits

This is a locally normalized single-interface finite-beam approximation, not a globally energy-conserving photon map or RTX implementation. Only the visible front top surface and an observed horizontal opaque bed are proven. Buried transparent layers and a second invisible interface cannot be inferred from the shadow buffers. Bed normals fitted from M3 depth neighborhoods remain approximate. The depth blur is an artistic bounded diffusion approximation. The world remains geometrically undisplaced by this feature.

## Validation entry point

`python -B tools/validate_gpu.py --suite water-caustics --report NEW_REPORT.json`

Use the separate suite `water-caustics-time` to collect 25 native timer queries on the same full-pool view with caustics off and on.

The public caustics_tests(runner) exercises real RGBA16 packing, actual D24/D32F ownership, actual shadow fragment capture, analytic flat/curved Snell mappings, torch/shadow/deep/edge rejection, finite camera footprints, real composite output, and the four refraction0/2 by caustics0/1 combinations. Displaced targets have deliberately different q values. Target-only q zero must disable caustics exactly; source-only q/normal edits must not control the traced result. Separate RGB endpoint checks cover dispersive transport. The comparison with full-float shadow storage is recorded in the release evidence.

Iris references: [shadow depth](https://shaders.properties/current/reference/buffers/shadowtex/), [shadow color](https://shaders.properties/current/reference/buffers/shadowcolor/), [feature flags](https://shaders.properties/current/reference/shadersproperties/flags/).

Intel Iris Xe, 512 × 288 with a full-screen pool and 2048² shadow textures: the composite median changed from 0.419 ms to 3.283 ms. Figures exclude the caster pass and reflect this fixture only. [25 GPU time queries per setting](validation/WATER_CAUSTICS_TIMING.json).

The [three-metre sand bed](validation/WATER_CAUSTIC_WAVES_views.png) uses the production shadow fragment shader and the actual analytic surface spectrum, then the full composite and final programs. With the camera held still, 16,002 of 19,968 pixels changed by at least two display codes between 17 and 19 seconds. [Native rendering data](validation/WATER_CAUSTIC_WAVES_GPU.json).
