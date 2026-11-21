# M6: optional dual-cascade spectral water normals

This note records the original normals-only implementation at `5ab6f4c`. The current spectral path also transports foam and estimates unresolved glint energy from the simulated slopes. It has seven images and three frame dispatches. [Current implementation and measurements](WATER_SPECTRAL_FOAM.zh-CN.md)

This first spectral release computes a periodic height and analytic-slope field with actual GPU compute, then uses its slopes in the existing water normal path. It does not displace Minecraft vertices. The same helper drives eligible water metadata, native water shading, debug normals and the caustic shadow normal capture.

## Player controls and capability fallback

`WATER_FFT` defaults to 0. Enabling it also requires `WATER_WAVES=1`, `WATER_SURFACE_DETAIL=1`, and both optional Iris features `COMPUTE_SHADERS` and `CUSTOM_IMAGES`. Wave strength and the existing speeds 0/1/2 remain applicable. Speed 0 is a static spectral pattern; strength 0 is exactly the original geometric normal. Detail 0 retains the original M14 path.

The properties gate disables setup, begin and begin1 and declares no simulation images if a required capability/option is absent. The GLSL 430 compute sources contain empty disabled branches, but those are NOT a solution for hardware without GLSL 430: Iris must actually suppress the disabled program sources. The graphics fallback is independently proven identical to the prior shader tree; the installed Iris 1.10.5 parser was tested across all 32 compute, image, FFT, wave and detail selections. Its source loader checks disabled program basenames before loading shader text.

## Frame schedule and storage

* `setup.csh`: deterministic Gaussian initial spectrum, once at initialization/reset.
* `begin.csh`: time evolution, horizontal 64-point inverse FFT.
* `begin1.csh`: vertical 64-point inverse FFT, publishing height and two slopes.
* Water/shadow fragments: manually bilinear-sample each cascade with finite checks and footprint attenuation.

Separate begin programs provide cross-pass image visibility. Each 64-thread transform group uses 1 KiB shared memory, and each FFT stage synchronizes reads before overwrites. The combined 1/64 row and column factors yield 1/4096 normalization. Only two image bindings are needed by a compute pass.

All three images are 128 by 64 atlases containing two independent 64-square fields. Seed RG32F uses 64 KiB; row RGBA32F uses 128 KiB; output RGBA32F uses 128 KiB. Total nominal storage is **320 KiB**, with no colortex allocation or persistent history. The output channels are height, world-X slope, world-Z slope and a validity marker. There is no buffer flip requirement. Existing interaction and refraction buffers remain separate.

## Spectral model

The 16 m cascade admits wavelengths 1.5–8 m; the 64 m cascade admits 8–32 m. Smooth radial tapers remove DC/Nyquist ambiguity and separate their bands. Both tapers go to zero at the 8 m boundary, producing a deliberate small spectral notch; this is an artistic choice rather than a continuous measured ocean spectrum.

A Phillips-shaped, wind-weighted spectrum uses direction (0.8, 0.6), 8 m/s nominal wind, gravity 9.81 m/s², and high-frequency damping. Ensemble height RMS targets are 0.035 m and 0.12 m before common artistic strength. These are calibrated model parameters, not measurements of Minecraft water. A single deterministic realization has a different instantaneous RMS.

Hermitian evolution creates real spatial height and slope fields. Analytic frequency derivatives i*kx*H and i*kz*H are packed as a two-real-field complex transform. Nyquist rows/columns are zeroed rather than interpreting ambiguous self-conjugate derivatives. Deep-water angular frequency sqrt(g|k|) is rounded to integer harmonics of a 600-second loop. This changes dispersion slightly but makes speeds 0/1/2 continuous across Iris's 3600-second time reset.

A world integer anchor is reduced before float arithmetic; absolute large world coordinates are never converted to float for phase. Both periods divide the existing 128 m anchor tile. Each atlas half is wrapped separately, so interpolation cannot bleed across cascades. A conservative whole-band attenuation fades at 0.25–0.5 cycles per pixel using each band's shortest wavelength. It is not an exact Fourier integration over a perspective pixel. Up to eight texture fetches sample both bands. The summed gradient is bounded to 0.12 before artistic strength, preserving current normal/capture safety ranges.

Invalid image size, nonfinite image data or invalid validity markers select the prior six-wave gradient. Invalid reconstructed footprints retain the geometric normal. The caustic camera-footprint filter uses the active FFT's shortest wavelength of 1.5 m; shadow and visible-water capture use the same sampled field.

## Deliberate limits in this release

FFT height/slopes do not yet define a horizontal material displacement. With FFT active, foam uses an identity material map, zero velocity and unit Jacobian. Shoreline evidence and conservative history still work; compression/crest foam is deliberately absent. The old six-wave Jacobian is never presented as a spectral Jacobian.

Likewise, unresolved spectral slope variance is not yet integrated. Sun/moon highlights retain their base material roughness and resolved FFT normal but omit the old six-wave variance increment. A measured FFT variance/dispersion-aware extension belongs in a separate change. Flat/flowing side faces retain their existing eligibility and flow approximations. This is neither a fluid solver nor a claim of measured current.

No geometric wave height, shoreline displacement, submerged topology reconstruction, physical breaking waves or global caustic conservation is claimed. Future mesh displacement must agree in water and shadow vertices and preserve stair, waterlogged-block and sidewall boundaries. Wind controls, choppy horizontal displacement, spectral foam and more cascades are later work.

## Verification

`validate_water_fft.py` independently implements complex evolution, recursive FFT and full separable DFT. Tiny DFT/FFT comparisons have error below 2.9e-15; Hermitian height imaginary residual is below 2.7e-16. All UI speeds have exact CPU reset continuity.

`validate_gpu_water_fft.py` requests an actual OpenGL 4.3 context, checks limits, allocates the specified mixed-format images and dispatches all three real production compute shaders. Independent full 64-square DFT truth is compared with actual stored GPU seeds; seed generation is checked separately. A single-frequency fixture proves derivative signs and cascade isolation. On Intel Iris Xe, driver 31.0.101.3962, maximum full-field error was 5.53e-7 for the speed-1 frames. GPU 600/3600-second snapshots were bit-identical; speed 0/2 checks also passed.

The actual production water fragment consumed the generated field on 4096 authored pixels: maximum normal error 6.49e-8. The real RGBA16 shadow fragment agreed with the visible-water world normal within 7.66e-6, including quantization. A large-coordinate camera-anchor transition was bit-identical. Missing either capability and invalid-image fallback were exact; zero strength was exactly flat. Native helper readback also confirmed identity FFT foam flow, retained shoreline evidence and absent legacy variance.

`validate_water_fft_integration.py --baseline PATH --report NAME.json` runs 78 focused compiler configurations and proves 54 disabled graphics stages exactly equal to an independently captured prior shader tree. The native test's optional callback is `fft_tests(runner, cxx)`; remove `field_at_17_5` from a JSON summary if the caller does not need the returned native image for visual fixtures.

These are synthetic native/OpenGL and offline tests, not a Minecraft runtime or Iris frame-scheduling acceptance claim. No frame-rate claim is inferred from the small correctness fixtures. The separate bounded GPU timing report measures the two per-frame FFT passes and their barriers, excluding setup, allocation, compilation, upload and readback.

## Sources and related contracts

[Iris optional features](https://shaders.properties/current/reference/shadersproperties/flags/), [custom images](https://shaders.properties/current/reference/buffers/custom_images/), [setup](https://shaders.properties/current/reference/programs/setup/), [begin](https://shaders.properties/current/reference/programs/begin/), and [compute pass documentation](https://github.com/IrisShaders/ShaderDoc/blob/master/passes/compute.md) describe the integration surface. The separate M4 notes retain the limitations of shadow-space caustics and require `shadowTranslucent=true` under the active caustic gate.

## 中文开发笔记

这一版让水面的大波与小波来自同一份真实计算的频谱，再把同一份斜率用于画面和阴影。这样反射起伏与焦散所看到的水面不会各自使用一套波。它还没有抬高方块顶点：高度场已计算，但目前只使用法线，优先保证岸边、台阶和含水方块不裂开。

“有高度场”也不等于“有流体流动”。首版没有水平位移，所以不会假装有频谱压缩泡沫；高光也不会借用旧六波的粗糙度统计。保留岸边泡沫和基础粗糙度，之后把实测频谱方差、水平形变和交互逐项补齐，证据范围更清楚。

## Measured simulation cost and active caustic filter

The isolated native compute timer retained all 25 samples after six warm frames: median **0.039572 ms**, p95 **0.049608 ms**, maximum **0.284440 ms** on the above Intel Xe driver. This is the two per-frame transforms plus image barriers only. It excludes the up-to-eight sampler reads per helper invocation in rendered water/shadow, so it cannot establish total water cost or Minecraft FPS. Reproduce with `python -B tools/benchmark_water_fft.py --report NEW.json --exclusive-window` only after coordinating other GPU workloads.

A further 16 native caustic-filter cases verify that FFT uses its 1.5 m admitted shortest wavelength, while disabled FFT retains the prior six-wave threshold. Exact threshold, far, extreme and nonfinite footprints are included. This proves the filter contract, not the full visual quality of FFT-driven caustic flux. Run `python -B tools/validate_gpu.py --suite water-fft --report docs/validation/NEW.json` for the compute, graphics, underwater exit and filter checks. Use `--debug-plate docs/validation/NEW.png` for the three camera angles.
