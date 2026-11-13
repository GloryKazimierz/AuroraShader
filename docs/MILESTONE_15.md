# Milestone 15: Native GPU validation

Date: 2026-11-13. Branch: `codex/milestone-15-gpu-validation`.
Base: M14 commit `e8007b21b8e0c4f13d44312b3c62959dbac1b326`.
[中文学习版](MILESTONE_15.zh-CN.md).

M15 adds a Windows driver-validation tool. It changes no shader behavior.
The tool can compile/link pack variants and draw selected synthetic inputs on a
real OpenGL driver without launching Minecraft. It is not an Iris runtime test
or a performance benchmark.

## 1. Three different kinds of evidence

| Layer | What it can establish | What it cannot establish |
|---|---|---|
| Existing CPU/structural and standalone GLSL checks | Mathematical invariants, source contracts and syntax under the offline compiler | Execution on the installed GPU driver |
| M15 native OpenGL checks | Driver compilation/linking and selected actual framebuffer results under explicit synthetic inputs | Iris patching, Minecraft draw scheduling, native resource/state setup or complete gameplay appearance |
| Minecraft with Iris | Integrated rendering, camera motion, world geometry, resource packs and interaction with the game | Broad correctness across every GPU, setting and scene from one observation |

These layers complement each other. Passing a newer layer does not retroactively
turn earlier milestones' unobserved Minecraft results into passes. Likewise,
a renderer found in the Windows device inventory is not proof that a particular
test actually used it; the current OpenGL context must identify itself.

## 2. A hidden window supplies a real OpenGL context

The C++ harness creates a small, never-shown Win32 window with its own device
context. It chooses and sets a pixel format, creates a temporary WGL context,
loads the modern context entry point, then requests OpenGL 3.3 compatibility.

The pixel format must be set before context creation, and a window's format is
set only once. The modern WGL extension specifies the requested version/profile.
[Microsoft pixel-format contract](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-setpixelformat),
[WGL context/profile specification](https://registry.khronos.org/OpenGL/extensions/ARB/WGL_ARB_create_context.txt).

Compatibility matters because the pack uses `#version 330 compatibility` and
compatibility built-ins. A hidden native window is just the context host:
test pixels are written to explicitly created framebuffer objects, not displayed
on screen. The harness does not show/focus a window or launch the game.

The successful initial context probe reported:

| Field | Observed value |
|---|---|
| Vendor / renderer | Intel / Intel(R) Iris(R) Xe Graphics |
| OpenGL | 3.3.0 - Build 31.0.101.3962 |
| GLSL | 3.30 - Build 31.0.101.3962 |
| Profile | Compatibility, mask 2 |
| Maximum texture size / fragment texture units | 16384 / 32 |

This is evidence for the Intel context that answered the probe. It is not evidence
for the machine's other installed GPU, and it is not a Minecraft/Iris observation.
The probe alone says nothing about shader compilation or rendered-pixel agreement.

## 3. What the two tools do

| File | Responsibility |
|---|---|
| `tools/gpu_harness.cpp` | Own the hidden WGL context, driver compile/link calls, FBO draw/readback and structured errors |
| `tools/validate_gpu.py` | Build the helper with the existing C++ compiler, prepare cases, compare results and optionally write a report |
| Existing validators / shader sources | Supply source variants and independent CPU reference calculations |

Generated binaries, expanded shaders, manifests and pixel data use fresh project
scratch storage beside the project on D:. Compiler subprocesses also receive
`TMP`, `TEMP` and `TMPDIR` pointing at that fresh directory. The runner does not
download a compiler, install graphics libraries, modify the Minecraft profile/
world/junction or alter shader settings.
The optional report is a deliberate retained artifact; scratch cleanup and report
creation have separate responsibilities.

Run from the project root on Windows with Python and the installed MinGW compiler:

```powershell
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --suite probe
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --suite compile
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --suite render
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --report docs/validation/M15_GPU.json
```

The default suite is `all`; `compile` and `render` each also probe the context.
If `--cxx` is omitted, the runner searches PATH for an installed `g++`.
No report is written unless requested. A successful report records the suite,
driver, normalized shader-source digest, fixture comparisons and their tolerances.
The source digest is checked again before success so a mid-run shader change
invalidates the result.
The runner rejects known software-renderer names rather than labeling them as
hardware GPU success. Failures raise an error; the runner still cleans its verified
fresh scratch directory and does not create a success report.

An existing report path is refused rather than overwritten. Select a new report
name for a later observation so its driver, inputs and result stay reviewable.
Do not infer a successful run from the mere presence of a JSON file: inspect its
status and reported stage/results.

## 4. Compile and link are separate checks

The runner prepares the supported shader-option variants and submits each
vertex/fragment pair to the real driver. Compilation checks each stage's GLSL;
linking checks whether the stages form one usable program.

This uses the pack source and test preprocessing. It does not execute Iris's
Java patcher or reconstruct every built-in alias/state that Iris supplies.
A successful driver link is useful evidence, but it cannot establish complete
in-game shader-pack compatibility.

The option matrix comes from the existing `compile_glsl.py` generator, rather
than a second manually maintained variant list. Include expansion and option
overrides are shared. Its render-stage constants are compile-only placeholders;
Iris supplies the actual values in the game. This matrix is a selected coverage
set, not every possible cross-product of all shader settings.

## 5. Rendering synthetic pixels into an FBO

A framebuffer object (FBO) connects a rendering destination to texture storage.
The harness checks that the attachment configuration is complete, sets explicit
viewport/uniform/texture state, draws, then reads the resulting pixels back.
An incomplete FBO is an error, not a black-image comparison.
[OpenGL 3.3 compatibility specification, sections 4.3–4.4](https://registry.khronos.org/OpenGL/specs/gl/glspec33.compatibility.pdf).

The draw disables blending, depth/stencil, dithering and automatic framebuffer
sRGB conversion for these isolated tests. That makes the supplied shader math and
storage choices easier to inspect. It deliberately does not imitate Minecraft's
full translucent composition or framebuffer lifecycle.

| Fixture family | Input contract and checked behavior |
|---|---|
| Harness controls | Asymmetric rows/channels, two unequal-weight samplers and a nontrivial matrix check coverage, orientation, bindings and matrix upload; deliberately invalid inputs must fail |
| Bloom | Actual extraction, horizontal blur, vertical blur and combine programs; 7x5, 3x3 and 8x6 inputs, bright last pixel, varying alpha, selected threshold/knee/strength combinations and bypasses |
| Water normals | The actual `waterWaveNormal` helper in a synthetic wrapper; negative/large/integer-limit anchors, time loops/static/invalid time, strength/eligibility gates and rotated/scaled/singular matrices |
| Final display | Actual final program with synthetic linear colors, selected highlight mapping/exposure settings, optional grayscale and alpha preservation |

Bloom uses `RGBA16F` source and intermediate storage. Each stage is checked
against a CPU reference using the preceding GPU output, and the full chain is
also compared against a separately propagated CPU result. The fixture explicitly
feeds pass outputs into later texture inputs; it does not test Iris's automatic
buffer flipping. The isolated 2x1 combine-bypass fixture does not establish
one-pixel-window support for Iris's half-resolution allocation.

Water tests write normal components to `RGBA32F`. They do not render real water
geometry, prove the material classifier's game integration or exercise the entire
M13 reflection/fog/blend path. Final-display tests use controlled `RGBA32F`
inputs/output, not a monitor or operating-system color profile.

Readback is RGBA float32, bottom row first. Optimized-away bindings must be
explicitly allowed for the corresponding bypass; unexpected inactive bindings
are rejected; a deliberately misspelled sampler verifies that rejection.
Every target starts with a finite negative clear sentinel. An all-discard control
must retain it, and comparing that unwritten target with expected zeros must fail.
This prevents a missing draw from silently passing an expected-black test.
Positive controls exercise the data path; malformed GLSL, link interfaces,
uniform types, raw-image lengths and output-file conflicts exercise other failures.

Synthetic inputs are a contract: dimensions, texture formats, uniforms, matrices,
coordinates, time and expected output are all chosen by the fixture. A test can
expose a driver/compiler or implementation error for those inputs. It cannot
prove that Iris will supply the same values at the same moment in a real frame.

## 6. Half-float storage and comparison tolerance

An `RGBA16F` attachment stores four half-precision floating-point components.
Reading it into a 32-bit floating-point array does not recover precision already
lost on the write. Multi-pass bloom can round at multiple intermediate storage
boundaries, so comparing against unlimited-precision CPU arithmetic bit for bit
would test the wrong contract.

The reference rounds bloom storage boundaries to half precision. For each channel:

```text
error = abs(gpu - expected)
allowed = absolute + relative * abs(expected) + halfUnits * halfULP(expected)
pass only when both values are finite and error <= allowed
```

`halfULP` estimates spacing at the expected half-float magnitude, including a
minimum subnormal step of `2^-24`. Current fixture limits are:

| Comparison | Allowed error |
|---|---|
| Each bloom stage | 2 half ULPs + 0.000002 |
| Bloom end-to-end | 4 half ULPs + 0.000004 |
| Bloom bypass, representable harness controls | Exact |
| Active water-normal cases | Absolute 0.00006 |
| Water bypass cases | Exact |
| Final display | 0.000003 + 0.00002 * abs(expected) |

Bloom alpha and final alpha receive additional exact checks. The report records
maximum absolute error and the largest fraction of the allowed tolerance.
The water reference models relevant float32 phase arithmetic; it is not an
unlimited-precision ideal compared blindly against hardware.

A useful comparison distinguishes a small expected numerical difference from a
structural error such as wrong dimensions, swapped channels, broken alpha,
misbound textures or a changed pass order. NaN/Infinity must not silently count
as agreement. Tolerance is tied to a fixture and its formats; it is not an artistic
threshold or a substitute for checking the formulas.

Readback waits for the relevant rendering work and transfers data back to the CPU.
The harness is designed to check correctness, not to measure a normal game frame.
Its build/compile/run duration is not shader FPS or a valid GPU benchmark.

## 7. Reading failures without changing the graphics feature

| Failure stage | First thing to inspect |
|---|---|
| Compiler discovery/build | Compiler path, installed headers/libraries and the C++ build output |
| WGL setup/probe | Exact Windows error, available context version/profile and reported renderer |
| Shader compile | Variant name, vertex/fragment stage and complete driver log |
| Program link | Stage interface and link log |
| FBO/texture setup | Dimensions, formats, attachment completeness and OpenGL error |
| Pixel comparison | Fixture inputs, per-stage storage precision, tolerance and maximum error |
| Report creation | Destination existence and the original successful/failed execution record |

Keep the fixture label/input contract and driver identity with the result. Do not respond to a
numerical failure by blindly widening tolerance, or to a driver failure by
silently labeling a skipped test as passed.

## 8. Evidence record and limits

The native compile suite completed successfully on the Intel context above:
**1,272 option configurations covering 24 vertex/fragment program pairs** compiled
and linked. The retained [compile report](validation/M15_GPU_compile.json) records
the run ending at 2026-11-13 07:56:58 UTC, with empty C++ build diagnostics.
The shader-source digest was externally confirmed unchanged:

```text
f750a7ae27b40729ffe45624bf4ade728d0eaf2b73695561454c0ed1cf799c1a
```

The final [synthetic-render report](validation/M15_GPU_render.json) completed at
2026-11-13 07:59:23 UTC on the same Intel driver:

| Executed group | Recorded result |
|---|---|
| Harness controls | 5 exact comparisons passed; 7 deliberately invalid/unsafe-result cases were correctly rejected |
| Bloom | 9 four-pass graphs (36 passes), 4 combine bypasses and 49 comparisons including 9 complete CPU-chain comparisons passed |
| Water normals | 35 cases, totaling 735 normal samples, passed |
| Final display | 5 selected cases passed |

The largest recorded bloom difference was **0.0078125 in linear HDR channel units**,
with every comparison inside its stated half-float tolerance. Around magnitude
8, that difference is one half-float spacing; it is not an error percentage of
a normalized display image. Across bloom comparisons, the largest fraction of
the allowed tolerance was about 0.8842. Maximum water-normal component error was
about `5.42e-7`; maximum final encoded-channel error was about `4.62e-7`.
Harness control differences were zero. The JSON retains per-case values.

Both reports and the current shader tree have the same digest shown above.
Shader contents remain unchanged from M14. The existing M1–M14 CPU/structural
validator and whitespace checks passed, and no generated GPU scratch directories
remained after completion. These results establish native-driver evidence for
the stated cases, not Minecraft/Iris success or a performance measurement.

| Remaining observation | Status |
|---|---|
| Minecraft/Iris visual integration for the newer milestones | Unobserved here |
| Native checks on another GPU/driver | Unobserved here |
| Full Iris preprocessing, render scheduling and resource binding | Outside this harness |
| Actual translucent-world overlap and camera behavior | Requires integrated observation |
| GPU timings/FPS | Not measured by this correctness tool |

The next graphics question remains water depth/transmission. M15 provides stronger
validation before that work; it does not create an opaque-scene copy, add a depth
sampler to water or implement refraction.

## 9. Six practical rendering questions

1. **Why keep CPU tests after GPU tests exist?** They cheaply isolate equations and
   broad parameter invariants; the GPU checks a different execution layer.
2. **Why can GLSL compile but fail to link?** Individual stages can be valid while
   their interfaces or combined program requirements are incompatible.
3. **Why use an FBO instead of a screenshot?** Controlled texture storage and
   numerical readback permit precise comparisons without desktop/UI differences.
4. **Why is the active renderer string important?** Hybrid systems can expose
   multiple GPUs; only the created context tells us which implementation ran.
5. **Why allow a numerical tolerance?** Storage precision and floating-point
   evaluation differ, while the intended computation should remain within a
   justified, small bound.
6. **Why is this still not Iris testing?** The game/mod supply transformations,
   patching, draw order and resources that a small synthetic harness does not own.

Related notes: [M14 wave normals](MILESTONE_14.md),
[M10 bloom](MILESTONE_10.md), [M8 scene color](MILESTONE_8.md),
[roadmap](AURORA_ROADMAP.md).
