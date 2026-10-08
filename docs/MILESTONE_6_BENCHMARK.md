# Milestone 6 — shadow bias test worksheet

Status: blank worksheet. No Minecraft/Iris runtime results or performance results
have been collected for this milestone. Static checks cannot establish GPU
compilation, visible artifact reduction or rendering stability.

## Load the intended project

Test branch `milestone-6-shadow-bias` at
`D:\MinecraftShaders\MyShader-pcf-kernels`. The existing `MyShader` junction
points to the separate sky experiment, not this checkout. Follow the isolated
D: test-profile instructions in [Milestone 4 benchmark](MILESTONE_4_BENCHMARK.md).
That optional profile/junction setup has not been performed here. Confirm the
loaded pack offers four filters, Constant/Angle-Aware bias, and Debug 6.

## Record and freeze the controls

- Date; Minecraft/Fabric/Iris/Sodium versions; GPU and driver:
- World name/seed; dimension; resource packs and other mods:
- Position; camera yaw/pitch; FOV:
- Render/simulation distance; window resolution; fullscreen; VSync/FPS cap:
- Time/weather; original `doDaylightCycle` and `doWeatherCycle` values:
- Shadow map resolution: **2048**; shadow distance: **64**; deviations:
- Shadows enabled; Debug **0**; filter **3x3 PCF**; softness **1.0**:
- Lighting/color settings; screenshot names; observation duration:

Keep all of these fixed within each bias sweep. Wait for chunks and shader reloads
to settle before capturing the same view. Only bias mode/settings may change.
The numbers below are test inputs, not recommended universal solutions.

## Reproducible scene

Use a disposable Overworld creative test world. Build a level stone platform
from `(0,64,0)` through `(24,64,24)` in a clear area. Place:

| Geometry | Proposed placement | Inspect |
|---|---|---|
| Vertical wall | x=4..20, y=65..69, z=4 | Self-shadowing and grazing faces |
| Ground-contact pillar | x=10, y=65..70, z=12 | Shadow attachment at its base |
| Stair run | x=16..18, y=65..68, z=14..17 | Steps, corners and contact shadows |
| Fence and iron bars | x=5..9, y=65, z=18 | Thin shadows and light leaks |
| Persistent leaves | x=16..18, y=66..68, z=7..9 | Cutouts and thin coverage |

Record the exact stair layout and leaf state. Ordinary Minecraft stairs have
axis-aligned faces, not a continuous sloped normal; low sunlight on the platform
and wall provides the grazing-angle test. Use an initial camera position of
`(12,68,28)`, yaw `180`, pitch `25`, FOV `70`, then record the actual pose used.
Keep the contact points visible; capture additional close-ups at separately
recorded fixed poses if needed.

Read and record the original gamerules first. Freeze time/weather with
`/gamerule doDaylightCycle false`, `/gamerule doWeatherCycle false`,
`/weather clear`, and `/time set 1000` for a morning/long-shadow pass. Repeat the
whole sweep at `/time set 6000` as a separate pass; do not change time within a
comparison. Restore the recorded gamerule values afterwards, not assumed values.

## Bias sweep: fill observations, leave no invented results

First compare Constant `0.0002` against Angle-Aware `0.0001`/`0.0005` using
3x3 PCF and softness 1.0. Then complete the sweep below. For Constant rows,
both columns repeat `SHADOW_BIAS`; min/max controls are ignored in that mode.

| Bias Mode | Min Bias | Max Bias | Filter | Acne | Peter-Panning | Contact Quality | Grazing Surface | Thin Geometry | Notes |
|---|---:|---:|---|---|---|---|---|---|---|
| Constant | 0 | 0 | 3x3 | | | | | | |
| Constant | 0.00005 | 0.00005 | 3x3 | | | | | | |
| Constant | 0.0001 | 0.0001 | 3x3 | | | | | | |
| Constant | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Constant | 0.0005 | 0.0005 | 3x3 | | | | | | |
| Constant | 0.001 | 0.001 | 3x3 | | | | | | |
| Constant | 0.002 | 0.002 | 3x3 | | | | | | |
| Angle-Aware | 0 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.00005 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 3x3 | | | | | | |
| Angle-Aware | 0.0002 | 0.001 | 3x3 | | | | | | |
| Angle-Aware | 0.0005 | 0.002 | 3x3 | | | | | | |
| Angle-Aware (equal bounds) | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware (reversed bounds) | 0.0005 | 0.0001 | 3x3 | | | | | | |

Record acne, detached contacts/peter-panning, light leaks, disappearing thin
shadows and screenshot identifiers. Reversed bounds test defensive handling;
equal bounds test constant output and safe debug normalization.

## Filter compatibility matrix

After the bias sweep, repeat the same scene with both modes in every filter.
Within each pair keep filter/softness fixed. These are correctness observations,
not performance claims.

| Bias Mode | Min Bias | Max Bias | Filter | Acne | Peter-Panning | Contact Quality | Grazing Surface | Thin Geometry | Notes |
|---|---:|---:|---|---|---|---|---|---|---|
| Constant | 0.0002 | 0.0002 | Hard | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | Hard | | | | | | |
| Constant | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 3x3 | | | | | | |
| Constant | 0.0002 | 0.0002 | 5x5 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 5x5 | | | | | | |
| Constant | 0.0002 | 0.0002 | Poisson | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | Poisson | | | | | | |

## Debug and regression checks

- Debug 5 shows actual shadow visibility. Debug 6 shows **potential receiver
  bias**, not visibility: black at the sanitized minimum, white at the maximum,
  clamped in between. Constant mode uses the same display range. A bounds span <= 1e-8, invalid surface metadata,
  and sky produce black. A valid-marked but degenerate normal uses maximum bias in
  Angle-Aware mode (white for distinct bounds). Color grading must not alter it.
- Confirm Debug 0–5 still works. With Constant 0.0002, compare all filters against
  Milestone 5 captures. Test softness 0 in both modes: filtered results must match
  Hard; Hard must ignore softness. Return to softness 1 afterwards.
- Separately repeat a recorded slow camera walk/rotation to inspect shimmer,
  attachment and map-boundary behavior. Out-of-map comparisons remain lit.
- Separately advance time to check sun-driven direction changes; restore the
  frozen time before resuming comparisons. Check caves/torches: ambient and block
  lighting must remain visible.
- Record Iris errors, screenshots and observations before declaring runtime
  success. A smoother edge does not prove self-shadowing has been fixed.
