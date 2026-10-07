# Milestone 4 benchmark worksheet

Status: blank template. Minecraft/Iris runtime results have not been collected.

## Load the correct checkout first

The PCF branch is checked out at `D:\MinecraftShaders\MyShader-pcf-kernels`.
The existing `MyShader` junction still points to the separate sky experiment at
`D:\MinecraftShaders\MyShader`; selecting it does not test this PCF checkout.
The old working tree and junction have not been changed.

To test in isolation, use a separate Fabric/Iris profile with its game directory
on D: (for example `D:\MinecraftShaders\Iris-PCF-Test`), using the same Minecraft,
Iris, Sodium and resource-pack versions as the working profile. After that profile
creates its `shaderpacks` folder, a new directory junction named `AuroraShader-PCF`
inside that folder can point to `D:\MinecraftShaders\MyShader-pcf-kernels`.
Verify the target exists and the new alias path is unused first; if anything is
already there, stop instead of overwriting it. Leave the existing C: junction
alone. This optional test-profile setup has **not** been performed by this task.
In the test profile, select AuroraShader-PCF and verify the filter menu contains
Hard, 3x3 PCF and 5x5 PCF. Keep all three comparisons in this same test world.

## Environment and controls (fill in)

- Date / Minecraft / Fabric / Iris / Sodium versions:
- GPU / driver / CPU:
- World / dimension / coordinates / yaw / pitch / FOV:
- Render distance / simulation distance / window resolution / fullscreen:
- Time of day / weather:
- Resource packs / other mods / VSync / FPS cap:
- Shadow map: 2048; distance: 64; bias: 0.0002 (record any deviation):
- Shadows enabled; debug: 0; softness: 1.0; other shader settings:
- Warm-up duration / measurement duration / measurement tool:

## Results (fill in; no example numbers)

| Mode | Softness | FPS | Frame Time | Edge Quality | Shimmer | Notes |
|---|---:|---:|---:|---|---|---|
| Hard | N/A | | | | | |
| 3x3 PCF | 1.0 | | | | | |
| 5x5 PCF | 1.0 | | | | | |

Frame Time is in milliseconds. If direct frame timing is unavailable, label
`1000 / stable FPS` as an estimate, not a measured GPU time. Record a stable range
instead of a single best frame. Save screenshots with the mode in each filename.

## Controlled procedure

1. Use the same Minecraft world and dimension for all three runs.
2. Stand at the same coordinates near a pillar/overhang with a visible shadow edge.
3. Keep the same camera direction and FOV; record coordinates, yaw and pitch.
4. Keep the same render and simulation distances; allow chunks to finish loading.
5. Keep the same time of day and weather. For a controlled daylight scene, use
   `/time set 6000`, `/weather clear`, `/gamerule doDaylightCycle false` and
   `/gamerule doWeatherCycle false`, noting the original rules for restoration.
6. Keep the same window resolution/fullscreen mode.
7. Keep the same shader settings except Shadow Filtering. Use debug 0, shadows
   enabled, softness 1.0 and bias 0.0002. Leave VSync/FPS cap unchanged across runs;
   preferably disable them for this benchmark and restore afterwards.
8. After each mode switch/recompile, wait for the scene to settle, then observe
   FPS for at least 10-15 seconds. Avoid menus and screenshots during measurement.
9. Record approximate stable FPS/frame time, edge quality and notes. Repeat in
   reverse mode order to spot warm-up or thermal effects. A flat capped/CPU-limited
   result does not prove filtering is free.
10. Take screenshots at the recorded pose after measurement. Separately repeat the
    same slow camera movement for each mode to judge shimmer; keep this separate
    from the stationary timing run. Restore changed world rules and display settings.

## Runtime acceptance, separate from the benchmark

- All three filter modes compile and render; no Iris errors after reload.
- Hard and 3x3 retain the tested 3B behavior; 5x5 has a wider filtered transition.
- Test softness 0, 0.5, 1, 1.5 and 2 in every mode. At zero, both PCF modes should
  match Hard. Hard must ignore softness. Larger spacing may show discrete steps.
- Debug 5 shows binary Hard visibility and fractional PCF transition values;
  debug 4 still shows raw depth. Recheck debug 0-3 and return to debug 0 for timing.
- Walk/rotate and change time: shadows stay attached and follow the sun/moon.
- Check cutout leaves, grazing surfaces, map boundaries, caves and torches:
  ambient/block light must remain visible; watch for acne, detachment or light leaks.
- Do not mark the milestone runtime-tested until these observations are recorded.
