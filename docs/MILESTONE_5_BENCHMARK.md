# Milestone 5 benchmark: grid versus Poisson PCF

Status: blank worksheet. Minecraft/Iris runtime testing and measurements are
pending. Do not infer performance or runtime success from the validator.

## Load the correct checkout

The branch is `milestone-5-poisson-pcf`, checked out at
`D:\MinecraftShaders\MyShader-pcf-kernels`. The existing `MyShader` junction
points to `D:\MinecraftShaders\MyShader`, the separate sky experiment, and has
not changed. Selecting that entry does not test this checkout.

Follow the [separate D: test-profile setup in the Milestone 4 worksheet](MILESTONE_4_BENCHMARK.md#load-the-correct-checkout-first).
That setup has not been performed by this task. If a test profile already exists,
verify its pack resolves to this PCF checkout; do not overwrite existing paths.
Use matching Minecraft/Fabric/Iris/Sodium/resource-pack versions, then select the
PCF pack and verify its filter menu offers **Hard, 3x3 PCF, 5x5 PCF, Poisson PCF**.

## Record the environment

- Date / branch / commit / Minecraft / Fabric / Iris / Sodium versions:
- GPU / driver / CPU / other mods / resource packs:
- World / dimension / coordinates / yaw / pitch:
- FOV / window resolution / fullscreen / render distance / simulation distance:
- Time / weather / original daylight and weather-cycle rules:
- VSync / FPS cap / measurement tool / warm-up and observation duration:
- Shadow resolution 2048 / shadow distance 64 / bias 0.0002 (record deviations):
- Shadows enabled / softness 1.0 / Debug 0 / all other shader settings:

## Results

| Mode | Samples | Softness | FPS | Frame Time | Edge Quality | Grid Artifact | Shimmer | Notes |
|---|---:|---:|---:|---:|---|---|---|---|
| Hard | 1 | N/A | | | | | | |
| 3x3 PCF | 9 | 1.0 | | | | | | |
| 5x5 PCF | 25 | 1.0 | | | | | | |
| Poisson PCF | 8 | 1.0 | | | | | | |

Keep the softness setting at 1.0 in Hard as well; it is ignored. Samples are
logical comparisons, not necessarily distinct texels or a GPU instruction count.
Frame Time is in milliseconds. If derived from FPS, label `1000 / FPS` as an
estimate rather than measured GPU time. Record a stable range, not a best frame.

Same softness does not mean equal footprint: Poisson fits within radius 1 *
softness, 3x3 reaches 1 * softness along each axis, and 5x5 reaches 2 * softness.
Grid corner radii are sqrt(2) and sqrt(8) times softness. Account for the different
edge widths when judging quality; this table does not isolate distribution alone.

## First controlled comparison

1. Load the correct PCF checkout, reload shaders, and check `latest.log` for Iris
   compile/link errors. Start with shadows on, Debug 0, bias `0.0002`, softness
   `1.0`, default lighting, and neutral color controls (exposure 0, saturation 1,
   contrast 1, temperature/tint 0, grayscale off).
2. Choose one daylight scene containing a pillar or overhang, diagonal edges,
   leaves, thin geometry, a sloped/grazing receiver, and shadows at several
   distances. Record the world, dimension, coordinates, yaw and pitch. Capture
   additional fixed viewpoints if one cannot show every case.
3. Record the current time, weather and world rules. In a test world with commands
   enabled, set `/time set 6000`, `/weather clear`,
   `/gamerule doDaylightCycle false`, and `/gamerule doWeatherCycle false`.
4. Hold position, camera direction, FOV, render/simulation distances, resolution,
   window mode, time, weather, bias, softness, resource packs, and all other
   shader settings constant. Let chunks finish loading. Use the same VSync/FPS
   cap for every run; disabling both makes timing differences easier to see.
5. Switch only Shadow Filtering: Hard (0), 3x3 (1), 5x5 (2), Poisson (3). After
   each recompile let the view settle, then observe for at least 10-15 seconds.
   Keep menus closed and avoid screenshots during the timed interval.
6. Record FPS/frame time and the stable range. Take screenshots afterward from
   the recorded pose, naming them by mode, softness, viewpoint and commit.
   Inspect straight and diagonal edges, leaves, thin geometry, grazing surfaces,
   and distant shadows for **grid structure, jagged edges, noise, shimmer,
   light leaking, shadow acne, and peter-panning**.
7. Repeat the timing run in reverse mode order. A capped or CPU-limited result
   cannot establish that extra filtering is free. Poisson is not assumed faster
   or better simply because it uses eight taps.

## Correctness and motion, separate from timing

1. Repeat each mode at softness `0`, `0.5`, `1.0`, `1.5`, and `2.0`. All PCF
   modes must match Hard at zero; Hard must ignore softness. At larger values,
   watch for discrete bands, leaking or detached edges rather than assuming that
   more softness is better. Eight offsets may quantize onto fewer unique texels.
2. Repeat the mode comparison in Debug 5. Hard is binary; each filtered mode
   should show fractional visibility at suitable edges. Poisson may show steps
   of 1/8, with some levels absent when taps hit the same texel. Check Debug 4
   remains raw shadow depth and Debug 0-3 still behave as before.
3. At frozen time, repeat the same slow walk, camera rotation and return to the
   recorded pose for every mode. Check that shadows stay attached to geometry
   and inspect edges for shimmer. A fixed Poisson pattern does not promise
   better temporal stability.
4. At a fixed camera pose, repeat the same world-time progression for every mode.
   For example start at `/time set 6000`, enable the daylight cycle for an equal
   observation interval, then freeze/reset it before the next mode. Also inspect
   morning/evening grazing light. Shadows must follow the light consistently.
5. Check map boundaries, caves and torch-lit areas. Ambient and block lighting
   must remain visible in shadowed areas. Shadows disabled should restore the
   existing unshadowed directional-light behavior.
6. Restore original world rules, weather/time, display settings, and preferred
   shader settings. Record any compile errors or artifacts with the mode,
   softness, bias, coordinates, time and screenshot. Do not mark runtime testing
   passed until the observations have been completed and confirmed.
