# Water 01: Matched scene color and depth snapshots

Date: 2026-11-21. Branch: `codex/water-01-scene-snapshot`.
Base: M19 commit `74c7164874e446ebd8e763f146286c2c6908b820`.
[中文学习版](WATER_01_SNAPSHOT.zh-CN.md) · [Water roadmap](WATER_ROADMAP.md).

W1 prepares inputs for future water reflection and transmission. The existing
deferred pass now saves eligible lit color and its corresponding screen depth.
**No current water shader consumes these snapshots.** Water appearance, waves,
alpha and reflection algorithms have not been redesigned in this stage.
W1 is implemented and CPU, offline compilation and native OpenGL checks have
passed. No Minecraft or Iris integration pass is claimed.

## 1. Capture at one defined point

The snapshot call runs after `lightScene` and `applyCelestialPalette`, immediately
before this deferred pass applies camera-to-surface atmospheric fog:

```text
colortex0 + recorded surface normal/light levels
    -> existing lighting and celestial palette
    -> snapshot lit RGB + matching depthtex1 sample
    -> existing deferred camera-path fog -> original colortex0 output
```

This separates the color available at the captured surface from this pass's
camera-path fog. A later reflected/refracted path must decide its own attenuation;
simply sampling already fogged pixels and fogging again can count an inappropriate
path twice. “Pre-fog” here means **before this deferred fog call**, not proof that
every earlier draw category was free of fog or transparent contributions.

The producer only enters the existing `surface.a > 0.5` branch. That flag describes
the pack's recorded normal/light G-buffer coverage, not a universal material or
opaque-visibility identifier. Sky and unrecorded surfaces remain invalid. Existing
metadata/ordering assumptions still need real Iris observation.

## 2. Buffer contract

| Output location | Iris attachment | Format | Payload / invalid value |
|---|---|---|---|
| 0 | `colortex0` | Existing format | Original scene output, including original coverage alpha |
| 1 | `colortex5` | `RGBA16F` | Eligible lit linear RGB and validity alpha 1; invalid `(0,0,0,0)` |
| 2 | `colortex6` | `R32F` | Matching nonlinear screen depth from `depthtex1`; invalid 1 |

`/* RENDERTARGETS: 0,5,6 */` maps the three output locations in that order; location
1 does not mean attachment 1. Format identifiers remain in a multiline comment
for Iris to parse. Both new attachments explicitly clear to their invalid values.
[Output mapping](https://shaders.properties/current/reference/constants/rendertargets/).

Snapshot alpha is a validity bit, independent of the scene's coverage alpha.
Snapshot depth is still device/screen depth; future consumers must reconstruct
positions before measuring distances. `R32F` retains more depth precision than a
half-float channel, but does not recover information absent from the source depth.
RGBA16F color is quantized when stored; the validity endpoints 0 and 1 are exact.

Formats and responsibilities of buffers 0–4 remain unchanged: scene color,
surface metadata and the two half-resolution bloom intermediates keep their roles.
Only `deferred` writes 5/6 in this stage, and no later shader samples or overwrites
them. There is no new pass, water option, scene-color lookup or tracing algorithm.

Iris documents scene-color samplers 0–3 as atlas aliases inside gbuffers programs,
which is why a future water consumer needs suitable separate attachments.
[Color attachments](https://shaders.properties/current/reference/buffers/colortex/).

## 3. Depth agreement and conservative hand rejection

The inspected Iris source copies `depthtex2` before opaque hands, then copies
`depthtex1` before running deferred at the main-translucency transition.
The latter is the depth paired with the deferred-time scene color. Earlier draw
categories may already be represented; neither label proves universally opaque-only
content. [Pinned copy order](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java#L948-L975),
[depth sampler overview](https://shaders.properties/current/reference/buffers/depthtex/).

The helper rejects `depthtex1 < depthtex2`. A newly nearer depth can be an opaque
hand in front of stale terrain metadata. Rejection leaves an explicit miss instead
of pairing that foreground color/depth with an assumed terrain surface.
This is conservative depth comparison, not semantic hand identification: other
new nearer writes can also be rejected. It does not prove every unsupported draw
or stale-metadata case can be detected. Equal or farther accepted depths still
must pass the other validity checks.

`encodeWaterSceneSnapshot` starts with invalid outputs and accepts a sample only
when all these conditions hold:

- Linear scene mode with debug view 0; legacy/debug paths keep invalid snapshots.
- Finite surface-validity value greater than 0.5.
- Finite, nonnegative RGB, each component at most 65504.
- Finite `depthtex1` in `[0,1)` and finite `depthtex2` in `[0,1]`.
- The matching depth is not nearer than the pre-hand depth.

The helper never repairs an invalid source, linearizes depth or modifies the
original scene. These rules define what a future ray may consider; they do not
establish actual water thickness, off-screen geometry or a complete scene model.

## 4. Ownership, flipping and storage cost

No size or flip overrides are added. Under documented defaults, the buffers use
display resolution and two sides; deferred writes the alternate side and flips it
for subsequent readers. A future gbuffers-water reader must read that published
side without writing to the same snapshot. W1 does not execute that consumer.
[Flip and size rules](https://shaders.properties/current/reference/shadersproperties/rendering/#flip),
[sampler selection implementation](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/samplers/IrisSamplers.java#L48-L64).

Nominal uncompressed storage for the new attachments is:

```text
RGBA16F (8 bytes) + R32F (4 bytes) = 12 bytes / pixel / side
1920 * 1080 * 12 * 2 sides = 49,766,400 bytes = 47.46 MiB
```

This estimate excludes driver alignment/metadata and other buffers. It is not a
measured allocation or FPS result. W1 adds two full-resolution writes to an existing
pass and a pre-hand-depth fetch for the captured branch. Invalid snapshots in
legacy/debug modes do not imply that the attachments or write cost disappear.
There is no measured performance improvement or quality-tier claim.

## 5. Files and evidence

| File | Responsibility |
|---|---|
| [`deferred.fsh`](../shaders/deferred.fsh) | Declares the two formats/clears and outputs; captures eligible lit color before its fog call |
| [`water_scene_snapshot.glsl`](../shaders/lib/water_scene_snapshot.glsl) | Encodes finite valid RGB/depth or explicit misses |

| Evidence layer | Status |
|---|---|
| Structural/numerical checks and historical preservation | M1–M19 regressions and W1 passed; 99 historical files pinned after exact W1 restoration |
| Standalone option/program compilation | All 1,622 program-pair configurations passed |
| Native mixed-format MRT, snapshot data and original-output comparison | Passed on synthetic inputs; details below |
| Native driver program compilation | 1,622 expanded program pairs passed; Iris transforms absent |
| Actual Iris clear/flip/sampler binding and Minecraft world appearance | Unobserved |
| In-game GPU time and actual VRAM allocation | Unmeasured |

### CPU, preservation and whitespace checks

The existing [validator](../tools/validate.py) passed all M1–M19 regressions and W1
with exit code 0. The [W1 validator](../tools/validate_water_snapshot.py) pinned all
99 M19 shader/property/language files after removing only the exact approved W1
deferred additions in memory; the snapshot helper is the only new shader file.
Restoration rejection checks, Python syntax parsing and whitespace checks passed.
This restoration is a test adapter, not a rollback of files on disk.

### Offline compilation check

The existing [offline compiler](../tools/compile_glsl.py) passed all 1,622 expanded
vertex/fragment program-pair configurations. This does not execute Iris transforms.

### Native snapshot check

[Snapshot report](validation/W1_GPU_snapshot.json): 8 helper configurations covered
224 samples (9 eligible and 215 invalid). The actual deferred program covered
5 configurations / 105 pixels, including 51 eligible samples; 34 samples
distinguished pre-fog radiance from the fogged original scene output. Five positive
MRT routing/clear comparisons and 10 malformed-manifest rejection cases passed,
alongside the original harness controls.

Original `colortex0` output matched the pinned M19 reference exactly, and R32F depth
comparisons were exact for these inputs. The largest RGBA16F color error was
0.000244140625 for the helper and 0.00048828125 for actual deferred; both stayed
within one half-float ULP at the compared value. These are synthetic comparisons,
not evidence of identical pixels in a Minecraft world.

### Native compilation check

[Driver compilation report](validation/W1_GPU_compile.json): 1,622 expanded
vertex/fragment program-pair configurations passed. Both native reports used
Intel Iris Xe, OpenGL 3.3 compatibility, with 8 supported draw buffers and
8 color attachments. Their common shader SHA-256 is
`62032419c636d3021860e1a173b623b0600958f8ea94199f845061f45077cbe9`.

### Remaining integration and performance checks

These tests execute real RGBA16F/R32F attachments and shader source logic. They do
not reproduce Iris preprocessing, allocation, flips, camera/hand ordering or world
rendering. Actual Iris binding/flip behavior, all-view water scenes, GPU time and
VRAM allocation remain unobserved/unmeasured. Passing the CPU, offline and native
checks does not change those integration or performance statuses.

## 6. Learning points and next step

1. **Why save color and depth together?** A ray hit needs the color of the same captured surface.
2. **Why before this fog call?** The future optical path differs from the current camera path.
3. **Why separate validity from alpha?** Coverage is not evidence that a trace sample is supported.
4. **Why reject some hand pixels?** A plausible-looking invalid hit is worse than a documented miss.
5. **Why keep a memory estimate now?** Infrastructure has a cost before it adds a visible effect.

W1 establishes a producer contract. The next water work builds filtered surface
normals and guarded ray consumers, while reflection/transmission composition,
underwater optics and scene validation follow the [water roadmap](WATER_ROADMAP.md).
