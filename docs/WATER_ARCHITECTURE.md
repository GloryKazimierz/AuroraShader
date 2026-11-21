# Aurora water architecture: contracts before effects

The implementation following M0 is documented in [Water M1](WATER_M1_OPTICS.md), including its actual attachment formats, ownership guards and memory cost. The compact typed layout described below remains a design alternative.

Updated: 2026-11-21. [中文](WATER_ARCHITECTURE.zh-CN.md) · [Water roadmap](WATER_ROADMAP.md).

AuroraShader organizes water rendering into five layers, with A–L modules defining
inputs, outputs and limits. This is a target architecture, not a completed feature list. W1 matched capture, W2 filtered normals and W3
bounded SSR have recorded automated/native evidence; [W3](WATER_03_SCREEN_REFLECTIONS.md)
still has native-alpha and reflected-segment-fog limitations. The original **water M0 /
W4A** establishes shared parameters and observable surface capture. Complete historical CPU,
focused offline and native checks passed. Water M0–M7 below are a new sequence, not historical pack M1–M19.

## M0 implementation and observable data

Branch: `codex/water-04a-optics-foundation`. WaterParams has three live fields:
`reflectionF0=0.02` feeds the existing production Fresnel function;
`worldBlockMeters=1.0` and `debugGapRangeMeters=16.0` feed the ray-gap view.
There are no unused absorption/IOR/biome placeholders. F0 retains the existing
artistic water-like approximation. `water_debug_capture.glsl` records the surface
in the water program; `water_debug_view.glsl` displays it in final. Existing
position reconstruction remains shared; no new water composition pass is introduced.

| DEBUG_VIEW | Meaning | Not established by this view |
|---|---|---|
| 7 | Accepted water is white, otherwise black | Full water volume or hidden water layers |
| 8 | Filtered view normal mapped as N×0.5+0.5; +Z is blue | Displaced geometry, waterfall flow or roughness simulation |
| 9 | Same-pixel water-to-background ray gap, grayscale over 0–16 m; invalid background magenta | Physical water thickness, refracted path or implemented absorption |

Capture covers classified water faces; only the original upward-face eligibility
permits wave-normal perturbation. Modes 7/8/9 use full-resolution colortex7 RGBA32F:
signed unit view normal in RGB and raw window depth in A; a zero normal is invalid.
A is metadata, not color alpha. Only this data attachment disables blending.
Water writes its main side and final reads that side; no M0 fullscreen pass writes
colortex7, so no explicit flip override is added. It clears every frame.

Final maps bounded window UV to a source texel and uses that texel's center for
reconstruction, so final and source resolutions need not match. It compares
capture depth to depthtex0 within one D24 quantization unit
(1/16777215); invalid size, finite/unit-normal or depth checks display black.
View 9 reconstructs depthtex2 at the same pixel and transforms the separation to
world space before measuring the gap. One block is modeled as one meter for this
display. Coplanar surfaces and later depthless overlays remain ambiguous; depthtex2
names capture timing, not a measured water-volume exit. Existing normal/debug 0–6
behavior must be preserved. Focused M0 numerical/native checks passed; actual
Iris binding/flip, Minecraft appearance and performance remain unobserved.

### M0 evidence

The [native report](validation/WATER_M0_GPU_final.json) and
[three diagnostic views](validation/WATER_M0_views.png) use shader SHA-256
32c6b201618664bc4405f76cd31677bb92cfb3da6ab060a720886003e504f448.
They are authored synthetic inputs on Intel Iris Xe OpenGL 3.3, not Minecraft images.

| Check | Observed result |
|---|---|
| Focused CPU/source | 104 W3 files pinned through seven scoped edits; 672 legacy 0–6 stages equivalent after narrow F0-accessor normalization; 144 live-debug program pairs |
| Capture and independent gap math | 216 face/wave cases, 768 analytic world-ray cases (maximum grayscale error 1.91513e-13), 36 different viewport mappings passed |
| Offline compilation | All 186 focused compile/link configurations passed |
| Native diagnostic views | 13,408 water pixels per view; 13,407 filtered normals differ from the flat normal; maximum gap grayscale error 3.55e-5 (about 0.00057 m at the 16 m scale) |
| Native preservation / resolution | 1,027 Fresnel samples exactly match W3; 50,343 output pixels across 173×97 / three views checked nearest source selection including ties |
| Native rejection | Glass, nearer final depth and invalid background cases passed |
| Full historical CPU regression | Passed all M1–M19/W1–W3/M0 checks |
| Actual Iris / Minecraft / GPU time | Unobserved / unmeasured |

Current files: [parameters](../shaders/lib/water_params.glsl),
[capture](../shaders/lib/water_debug_capture.glsl),
[debug decode](../shaders/lib/water_debug_view.glsl),
[water fragment plumbing](../shaders/lib/geometry/lit_fragment.glsl) and
[final display](../shaders/final.fsh). The new three labels bring the bilingual
language count to 194; the 60 controls and existing profile ownership stay intact.

## Five owners and actual render order

| Layer | Owns | Must not hide |
|---|---|---|
| Common / WaterParams / optics | Units, finite parameters, color space, interface Fresnel, extinction and shared coordinate helpers | Artistic multipliers versus physical quantities; which fields are actually consumed |
| Simulation | Height/displacement, slope, variance, velocity, Jacobian and optional persistent state | Stable world anchors, update cadence, boundaries, seed, capability and memory limits |
| Surface capture | Classified water coverage, surface depth, normal, material/medium and valid background relation | Glass/particles/order, hand depth, side faces and missing layers |
| Composite optics | Reflection/transmission, validated ray hits, path attenuation, scattering, foam and medium composition | Each path segment and light contribution has one owner; invalid data has a fallback |
| Post | Temporal reconstruction when implemented, bloom, exposure, display transform | History rejection and pre-exposure scale; no second application of water extinction |

Iris ordering is not interchangeable:

```text
setup (load/resize; compute only, optional)
begin (before shadows; optional simulation needed by casters)
shadow -> shadowcomp -> prepare (after shadows, before world gbuffers)
world gbuffers -> deferred / W1 snapshot -> later translucent gbuffers
composite chain (future owned water optics, then post stages)
final -> window backbuffer
```

[Setup](https://shaders.properties/current/reference/programs/setup/) is not an
every-frame update. [Begin](https://shaders.properties/current/reference/programs/begin/)
can supply waves to shadow casters; [prepare](https://shaders.properties/current/reference/programs/prepare/)
cannot retroactively change the current shadow geometry.
[Composite](https://shaders.properties/current/reference/programs/composite/) follows
gbuffers. [Final](https://shaders.properties/current/reference/programs/final/) writes
the window, not a persistent color attachment.

Today, W3 shading remains in the water fragment helper; moving it to composite is
future work. Current composite/composite1/composite2/composite3 perform bloom
extraction, horizontal blur, vertical blur and HDR addition; final alone applies
exposure/tone/display/grading. There is no FFT, compute-wave simulation or TAA.
A future water compositor must precede bloom extraction, with explicit pass
renumbering and preserved output behavior. Final cannot be the history writer.

## Shared data and interface rules

- Model world-space **1 block as 1 meter** for optical coefficients and wave scales.
  State every space explicitly; view-z difference is not ray length, and a vertical
  gap is not a refracted water path. Keep large world anchors separate from local floats.
- Radiance and transport use scene-linear HDR. Encode display color once at the end.
  Absorption/scattering coefficients are nonnegative inverse meters; IOR is positive;
  wind has direction and speed. Reject nonfinite data and version the parameter contract.
- Target WaterParams derives absorption, scattering, IOR, turbidity, wind, sea state
  and roughness from verified biome/weather inputs. A declared default is preferable
  to claiming an unavailable biome or physical river velocity has been measured.
- Resolve filtered-wave variance and foam roughness **before** sampling reflected
  radiance. SSR confidence describes missing/reliable data, never Fresnel reflectance.
  Do not count a reflected sun disc and a separate sun highlight twice.
- Keep a cheap analytic path and a bounded scene-data path. Missing SSR data falls
  back to the available environment; a cave without sky access must not receive an
  outdoor sky merely because tracing failed. W3's palette does not contain actual
  aurora, clouds, glow or discs yet.
- gbuffers_water also draws non-water translucent terrain. A global blend override
  or post-hoc correction cannot by itself preserve layered glass/water/particles.
  Define coverage, ordering, source alpha and unsupported-case fallbacks before
  replacing the native composition. [Iris gbuffers](https://shaders.properties/current/reference/programs/gbuffers/),
  [blend controls](https://shaders.properties/current/reference/shadersproperties/rendering/).

## Planned composite flow

M0 does not execute this compositor. The target order makes ownership explicit:

```text
validate front-water record + overlap policy; invalid -> declared fallback
-> resolve eye/near-plane medium + first interface; branch above/below water early
-> load WaterParams, filtered normal variance, foam coverage and effective roughness
-> depth-validate refraction/receiver; reject foreground, missing and unsupported layers
-> bottom direct light: incoming-water transmittance × bounded caustic flux × direct light
   (requires separated direct-light inputs; do not re-attenuate already-lit snapshot RGB)
-> outgoing transmitted radiance + illumination-driven in-scatter / bounded crest response
-> roughness-aware reflected radiance: SSR -> available probe/sky; transport hit-to-interface once
-> Fresnel reflection/transmission partition; foam coverage blends its own bounded response
-> remaining interface-to-eye medium/atmosphere segment exactly once
-> owned linear-HDR resolve -> optional future TAA -> existing bloom -> final display
```

Reflection confidence mixes data sources inside the reflected branch; it does not
replace Fresnel or create a second full-strength sun. The medium branch assigns
every air/water segment before transport. Unsupported layered input returns to an
explicit approximation/fallback, not a fabricated water exit. The receiver's
inbound direct-light leg and the view/outgoing leg are different responsibilities.

## A–L module contracts

These are targets, with the implemented subset named explicitly.

| Module | Inputs -> owned output | Dependency / limit |
|---|---|---|
| A Parameters | Biome/weather/sea state -> shared WaterParams | M0 baseline first; environmental mapping must use available inputs |
| B Waves | Time/world anchor/wind -> height, normal, variance, Jacobian | W2 currently provides filtered normal detail only; noise/Gerstner/FFT and mesh motion are distinct paths |
| C Capture | Classified surface + matched scene depth -> valid water record | M0 diagnostic capture first; a single visible layer cannot describe all transparent overlaps |
| D Refraction | Interface/IOR + background depth -> depth-validated transmitted sample | SSR refraction must reject foreground crossings and screen misses; UV distortion is a separately labeled approximation; dispersion optional |
| E Transport | Incoming-light leg + outgoing-view leg -> attenuated radiance and in-scatter | Use each water-filled segment once; crest SSS is a bounded approximation, not free emissive brightness |
| F Reflection | Roughness/normal + scene/probe/sky -> reflected radiance | W3 SSR exists; probes/shared sky/Cox–Munk statistical sea slopes are planned, with measured matching to wave variance |
| G Foam | Compression Jacobian/contact/history -> foam coverage and roughness | Shore depth is not turbulence; history needs advection, decay and rejection, no permanent white bank outline |
| H Caustics | Water/light mapping + receiver -> focused bottom direct lighting | Area-ratio/shadow-space method needs footprints and flux normalization; broaden with depth and avoid singular gains |
| I Underwater | Eye medium + per-sample near-plane/first interface -> waterline, Snell window and volume | Camera flag alone cannot split the image; opaque occlusion, winding and local wave height matter |
| J Interaction | Verified event/flow inputs -> ripples, wakes, rain and directional flow | Distinguish supplied velocity/events from inferred scrolling; no game-physics or event access is assumed |
| K Stability | Normal variance, motion, depth/material -> LOD, roughness and accepted history | Reprojection alone is insufficient; reject disocclusion, medium/normal/depth changes and stale simulation |
| L Fantasy | Explicit optional controls -> bioluminescence, tides, rainbows, lens droplets | Separate artistic emission from scattering; lens state is camera-local, tides need a world/geometry policy |

Two-leg transport requires light ownership: caustics modify bottom **direct light
before outgoing attenuation**. W1 RGB is already lit; multiplying it by inbound
absorption again would also alter ambient/other components. Isolate direct lighting
or label the resulting approximation; do not silently apply the inbound leg twice.
[Transmittance](https://www.pbr-book.org/4ed/Volume_Scattering/Transmittance).

Perspective rays share the eye. A per-pixel waterline concerns the medium at each
near-plane sample and the first crossed interface, not a different camera medium
for every ray. A valid surface/opaque-depth relation and consistent interface side
must precede refraction and total internal reflection.
[Dielectric reflection/transmission](https://www.pbr-book.org/4ed/Reflection_Models/Dielectric_BSDF).

## Buffer ownership, flipping and lifetime

| Resource | Current owner -> reader | Resolution / lifetime |
|---|---|---|
| colortex0, RGBA16F | Scene/deferred/late blend/bloom-add -> later scene stages/final | Display; HDR scene, not water history |
| colortex1 RGBA16 / 2 RG16 | Supported opaque material writers -> deferred/debug | Display; encoded normal/validity and light levels; clear each frame |
| colortex3 / 4 RGBA16F | Existing bloom passes -> next bloom pass | Half width and height; transient scratch, not reusable as persistent water history |
| colortex5 RGBA16F / 6 R32F | W1 deferred -> W3 water consumer | Display; matched pre-fog lit RGB/validity and depth; clear each frame |
| depthtex1 / depthtex2 | Iris depth capture -> guarded consumers | Display; timing-dependent; no interchangeable meaning or writable ownership here |
| M0 colortex7 RGBA32F | Water diagnostic capture -> final debug | Modes 7–9 only; display size, zero clear; normal xyz + raw depth w, not persistent |
| Future simulation/history | One declared producer -> explicit later consumers | Dedicated world-grid or screen resolution; never alias live bloom/snapshot data |

Gbuffers write the main side; fullscreen stages normally read main, write alternate
and publish it by flipping. Document every override, producer/consumer side and
clear boundary; do not sample the same image being written. W1's actual Iris flip
integration remains unobserved despite native fixture checks.
[Iris buffers](https://shaders.properties/current/reference/buffers/colortex/),
[flip rules](https://shaders.properties/current/reference/shadersproperties/rendering/).

Nominal allocation is width × height × bytes/texel × physical sides, plus mip chains
and each cascade/history field. W1's 8+4 bytes/texel on two full-size sides is
47.46 MiB at 1920×1080. M0's RGBA32F debug attachment would add 63.28 MiB if
both sides are allocated. These exclude scene/depth/shadow/bloom and driver overhead;
actual Iris allocation outside debug mode is unmeasured. A simulation grid scales with its own resolution, not window size. No measured
VRAM total is claimed. Allocate additional fields only after a resource ledger.

### Future resource ledger — proposed, bindings unassigned

The examples below are allocation arithmetic, not selected grid sizes or measured
VRAM. N=256 illustrates one simulation cascade; S=1024 illustrates one light-space
map; screen estimates use 1920×1080. Reserve concrete attachment/image bindings
only after liveness and capability checks.

| Proposed field / format | Producer -> consumers | Lifetime / size / nominal example |
|---|---|---|
| Displacement.xyz + scalar Jacobian, RGBA16F per cascade | Simulation before required shadow/capture -> mesh, shadow, foam/caustic inputs | N², two states if previous geometry is needed: 1.00 MiB at N=256 per cascade |
| Encoded normal.xy, RG16F per cascade | Simulation derivatives -> capture/shading | N², two-state budget 0.50 MiB; reconstruct the unit normal; optional variance R16F adds 0.25 MiB |
| Foam, R8 or R16F ping-pong | Compression/contact + prior foam -> shading/next update | Persistent N² field, 0.125 / 0.25 MiB at N=256; advection/decay/reset required |
| Ripple height/velocity, RG16F ping-pong | Bounded interaction update -> wave merge/next update | Persistent N² field, 0.50 MiB at N=256; declared event/edge/cell-size limits |
| Caustic flux, R16F or RGBA16F shadowcolor/custom image | Water/light mapping -> bottom direct lighting | Per-frame S²; 2 / 8 MiB per side at S=1024; extra filtering/history storage counted separately |
| Reflection RGB/confidence, half-resolution RGBA16F | Bounded SSR pass -> water composition | Transient half-width/half-height, two-side budget 7.91 MiB at 1080p; W3 currently has no such buffer |
| Motion, RG16F | Current/previous actual geometry transforms -> temporal rejection | Full-screen, one side 7.91 MiB; camera-only motion cannot describe animated water |
| HDR history RGBA16F + depth R32F + normal RG16F + flags R8 | Composite history owner -> next-frame temporal stage | Full-screen ping-pong, example total 67.24 MiB; exposure/medium/material validity travels with history |

One RGBA16F cannot hold displacement3 + normal2 + Jacobian1 simultaneously.
The split above is 12 bytes/texel before variance and physical sides. Reconstructing
normals from derivatives is an alternative with a different fetch/filter cost.
A scalar determinant also does not replace a full Jacobian matrix when a later
algorithm needs its components. FFT complex spectra/scratch, mip chains, probes,
voxel data and volumetric grids are additional allocations, not included above.
No live resource may be silently aliased with bloom 3/4 or snapshot 5/6.
The tested native context reports eight simultaneous draw buffers/color attachments;
that is not proof that the entire proposed ledger fits one pass or the Iris loader.
Check live outputs, sampler/image units and format support before assigning bindings.

No temporal water history exists today. A future history owner must invalidate on
pack reload, resize/scale change, dimension/world switch, camera cut/teleport,
simulation-origin/seed/grid changes, incompatible settings and time discontinuity.
Reject individual samples on depth/normal/material/medium mismatch, disocclusion
and out-of-bounds reprojection. Initialize both sides before reads; store previous
transforms, exposure convention and world origin. Decay is time-based, not frame-count based.

### Candidate storage for the first optical resolve

Store the fraction of the pack's directional lighting at each eligible opaque
receiver. If `L` is the existing lit RGB, `q` its modeled directional share,
and `Ti` / `Tv` the incoming and outgoing RGB transmittances, the bottom
contribution is `Tv * (L * (1-q) + Ti * L * q)`. The scattering source needs
its own illumination. At `q=0` the incoming solar leg has no effect on torch-lit
color. The outgoing water still attenuates the light reaching the viewer.

A candidate layout uses an RG32UI record for the octahedral normal and original
depth bits, an R8 overlap counter, and an R16F fraction with −1 for missing data
and 0 for a valid unlit receiver. At 1080p, two sides at 11 bytes per pixel cost
43.51 MiB beyond W1. This estimate assumes the water draw can reuse colortex2
after deferred for its light levels. Before enabling it, test typed initialization,
exact depth readback, late writers in both draw orders and native fallback at
blocked pixels. The M0 diagnostic attachment keeps its separate format.


## Water M0–M7 implementation order

| Stage | Deliverable | Current status / acceptance question |
|---|---|---|
| M0 / W4A | Common helpers, WaterParams baseline, debug water mask/filtered normal/ray gap | Implemented; complete historical CPU, focused offline and native checks passed; default scene preservation and observable capture remain the contract |
| M1 | Two-leg extinction/in-scatter with depth and sun response | Planned; define direct/ambient ownership, water path and composition before adding color |
| M2 | Variance/LOD/environment fallback | Planned; calm distant water and no outdoor sky in covered pools |
| M3 | Depth-validated refraction and per-pixel waterline/Snell window | Planned; test foreground/overlap/near-plane/inside-outside cases |
| M4 | Projected caustics, sharp shallow to broader deep patterns | Planned; finite flux and correct bottom direct-light stage |
| M5 | Jacobian/contact/history foam with decay | Planned; supported compression/contact and temporal lifecycle |
| M6 | Multiple FFT cascades and sea-state controls | Planned; capabilities, cascade overlap/energy, world anchoring and memory first |
| M7 | Interaction and optional fantasy features | Planned; add only supported event inputs and independently configurable effects |

This sequence refines the earlier W4–W8 roadmap; W1–W3 records and historical
milestone numbers remain intact. Physical, artistic and debug controls should be
separate groups. M0 only extends the existing debug selector; it does not invent
unused sliders or ship the future quality tiers.

## Proposed quality paths and budgets

| Proposed tier | Target path | Required capability / bounded work |
|---|---|---|
| Low | Analytic sky, noise normals, optional UV distortion and simple fog | Baseline raster path; zero SSR queries; UV distortion is not validated refraction |
| Medium | Gerstner, SSR, stepped refraction, programmatic caustic, Jacobian foam | Start from current 64 processed-cell SSR cap; refraction/caustic budgets need measurement |
| High | Two FFT cascades, probes, dispersion, shadow-space caustic, history, volumetrics | Verified compute/image support, persistent storage and measured bandwidth; current 128 SSR cap is a candidate, not a tier implementation |
| Ultra | Three/four FFT cascades, voxel or supported RT path, dispersion caustics, wakes | New scene representation or verified acceleration backend; no hardware RT exists in this GLSL330 pack |

Configuration has one precedence: **capability limits > water master disable >
selected tier with explicit per-module overrides**. A tier supplies defaults; an
explicit override replaces its module default only within the first two limits.
Thus effective enable = supported AND master-enabled AND requested. Unsupported
FFT/probe/RT paths stay disabled with a named fallback; selecting Ultra never
installs a backend or silently enables unavailable modules. Show effective values
and fallback reasons. Debug instrumentation remains distinct from normal-view
feature enablement.

Compute capability must be checked separately from the current GL3.3 validation
context. FFT grid sizes, refraction steps, probe update cadence and temporal buffers
remain budget decisions, not implemented defaults. Hardware RT cannot be enabled
by a label or by adding a compute shader. [Khronos ray-tracing requirements](https://docs.vulkan.org/guide/latest/extensions/ray_tracing.html).

A **provisional project goal**, not a result, is ≤2.0 ms median / ≤3.0 ms p95 added
water GPU time at 1920×1080 Medium on the named Intel Iris Xe test GPU. Measure the
difference against a documented matching baseline, declaring whether snapshots
are included; record driver, clocks, resolution, coverage and all settings. Warm
the workload and use GPU timings, not validator wall time. Revise this goal from
measurements before advertising a tier. Existing Balanced/Light/Soft Shadows
profiles remain seven-option presets; they are not the four tiers above.

## Fixed observation scenes

Keep one reproducible seed, camera paths, FOV, exposure, time/weather and resource
pack per comparison. Blank results mean unobserved.

| Scene | Required observation | Observed result |
|---|---|---|
| Shallow shoal | Bottom readability, depth/sun response, shore contact | |
| Open ocean at top/oblique/grazing angles | Wave coherence, distant LOD, sky fallback and horizon | |
| Covered cave with local light | No invented skylight or self-lit scattering | |
| River step and waterfall | Flow direction, top/side join and impact localization | |
| Underwater and waterline crossing | Near-plane medium, Snell window, total internal reflection | |
| Glass/particles/hand near water | Occlusion, layering, alpha and unsupported-case fallback | |
| Moonlit / aurora night | Own sky identity, restrained highlights, readable darkness | |
| Rain and changing weather | Ripples, roughness, fog continuity and performance | |

Current synthetic pictures are explicitly labeled [W3 visual tests](validation/W3_visual_final/README.md);
they do not fill this Minecraft observation table.
