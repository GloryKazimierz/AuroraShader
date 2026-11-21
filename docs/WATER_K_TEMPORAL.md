# K — Water-only temporal stability

K is an opt-in, unjittered temporal filter for confirmed water. It runs inside the existing full-resolution `composite5`, before that pass adds current-frame bloom. It is **not full TAA**: there is no projection jitter, subpixel reconstruction, object motion vector, or new render pass. The optical transport, foam, waves and final display transform are unchanged.

## Use and cost

`WATER_TEMPORAL = 0 [0 1]` appears under Water → Reflection & Refraction. It requires the existing Water Optics/capability, water style, HDR scene and normal display gates. Defaults and quality profiles do not enable it. Bloom can be on, off, or zero strength; the filter still runs before the bloom bypass. Disabling any prerequisite preserves the previous expanded stage and image.

One new double-buffered **colortex12 RGBA32F** stores pre-bloom RGB and full FP32 raw depth. At 1920×1080 its two sides consume **63.28125 MiB**, before driver overhead. Its clear value is zero and `Clear=false`; startup, stale records and unsupported pixels fail closed. This deliberately pays for accurate depth rather than putting raw depth in a half-float channel. The isolated GPU measurements are reported below.

## Confirmed ownership and reprojection

The current surface must have exactly one water layer, no overlay/blocker, unit filtered normal, matching captured/front depth, and finite color. A positive saved raw depth is an above-water top; negative depth is an observed underwater exit with the exact `colortex8.a` byte marker. The sign preserves every depth mantissa bit. Unobserved/clipped exits are never inferred. Without M3B, this code simply receives no exit records.

Integer/fractional camera positions and current/previous matrices reproject the same world point. A nearest prior pixel is accepted only when its signed side agrees and its full raw depth matches the old pixel-center ray's intersection with the current physical horizontal plane, within 4/16777215. This avoids comparing two different ray centers as if they were identical. The current shaders have optical normal waves, not displaced geometry. Sloping/unsupported interfaces can lose history and use current color.

History is rejected for out-of-screen reprojection, invalid matrices/metadata, missing old water, foreground depth, changed projection, more than 4 blocks of camera movement, a forward-direction dot below .9, long frames above .1 s, blindness/darkness, unsupported medium/dimension, or expired headers. Current nonwater is never filtered and never gets valid history. The two reserved header pixels keep their normal current image color.

## Cached dimensions and frame state

Iris caches dimension pipelines. Allocating/resizing render targets clears storage, but returning to a cached dimension must **not** be assumed to clear it. Creating a new pipeline resets global frameCounter/frameTimeCounter, so frame number alone is insufficient.

History texels (0,0) and (1,0) store consecutive frame tag, viewport, medium properties, timer, wall-clock second and date. K requires consecutive frame and timer values, wall-clock age 0–1 second, matching date/dimensions/medium, and a 2.1-second warm-up after the global timer resets. Under a normally advancing system clock, a cached numerical counter collision following reset is therefore too old to pass. Date/clock discontinuities reject where observable. These are observed continuity signals, not a unique engine world/dimension identity; arbitrary clock rollback is not a supported identity proof. Timer wrap also causes warm-up.

Primary sources: [Iris 1.21.11 PipelineManager](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/pipeline/PipelineManager.java), [SystemTimeUniforms](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/uniforms/SystemTimeUniforms.java), [camera uniforms](https://shaders.properties/current/reference/uniforms/camera/), [system/date uniforms](https://shaders.properties/current/reference/uniforms/system/).

## Filter and limits

The center and four cardinal, same-plane current water neighbors bound the reprojected RGB. History is clamped into that current neighborhood. A relative color change smoothly suppresses history from 10% to 30%; strong moving highlights immediately retain current color. Otherwise the history weight is `min(.9, exp(-frameTime/.08))`. Small animations can still have roughly an 80 ms filter response; this is a deliberate flicker/latency tradeoff. No previous normal, water velocity or object motion is stored, and subtle moving reflections can lag. This first K step does not solve all temporal aliasing or recover information outside the frame.

History contains no bloom. Current bloom is added exactly once after filtering; current alpha is unchanged. Tone mapping/exposure stay in final. No temporal emissive feedback or additional camera fog is introduced.

## Validation and integration

Frozen shader digest: `a3ef48d5c462682935ef891da4773e659acdbe7dc6b0d5816219d5f3ee341b3e`.

- Full CPU: 1,200 old live-stage comparisons, 1,296 refraction-off comparisons, 127 historical source pins, existing water/foam/contact/world checks, and 64 new temporal gates passed.
- Nine targeted offline program pairs passed, including disabled capability, legacy/debug/style and bloom off/zero.
- Final formal-entry native suite passed 29 exact reset/disabled controls, three positive camera motions and an adjacent moving highlight. The highlight's old location would remain red 3.304 without reactivity; the tested reactive result retains current red .3.
- Eighteen feedback frames measured 4,008 water pixels: raw red-channel noise RMS .00864334, filtered .00316408, ratio .366071. This is a seeded synthetic static-noise fixture, not an in-game quality percentage.
- Observed upward exit test: 154 pixels retain exact negative FP32 depth and match the independent color equation.
- Final formal-entry evidence is `docs/validation/K_final_native.json`; the diagnostic PNG is a synthetic input/output/error plate, not Minecraft.

Commands: `python -B tools/validate.py`; `python -B tools/compile_glsl.py --water-temporal-only`; `python -B tools/validate_gpu.py --suite water-temporal --report docs/validation/K_final_native.json --debug-plate docs/validation/K_temporal.png` (reports require new paths).

K adds two libraries and a narrow hook to **composite5**, retaining all pass names. It was staged against the frozen planar-production snapshot whose shader digest is `6387b86b651c2dd230ee2fc946cb587a1ed3e3cb8cd8357edf875e8ba9b7c234`. Native checks use actual GLSL on Intel Iris Xe/OpenGL3.3 with synthetic buffers; Minecraft/Iris scheduling, runtime appearance, memory pressure and final performance still need integration testing.

The frozen 720p all-water recombine measured 0.332228 ms with the filter off and 5.482620 ms with it on (six warm draws, 25 samples). The 5.150392 ms difference excludes the other passes and Minecraft. [Native timing distribution](validation/K_timing.json) · [Cumulative driver checks](validation/WATER_TEMPORAL_GPU.json)
