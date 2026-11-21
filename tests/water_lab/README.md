# Aurora water lab — isolated Minecraft fixture

[中文](README.zh-CN.md) · [Scene coordinates](scene.json)

A small, repeatable **Java 1.21.11 / data pack 94.1** scene for AuroraShader water.
It contains a separate `aurora_lab:water` dimension and explicit player functions.
It has not been installed or run in Minecraft; shader appearance, fluid settling,
dimension loading and Iris behavior remain **unobserved**. Static validation is
recorded separately by the repository checker.

## Install into a new disposable world on D:

Keep the game directory and the new save on D:. Select this data pack when creating
the disposable world, or put this folder (with `pack.mcmeta` directly inside it)
under that new save's `datapacks/aurora_water_lab/` and fully reopen the world.
Use Minecraft 1.21.11, commands enabled and normal command limits. This repository
does not install the pack, launch Minecraft, modify a world, change junctions or
copy shader files to C:.

Do not add it to a historical or ordinary playing world. The custom dimension uses
the built-in overworld type, an ocean biome, no structures/features/lakes and a
flat stone surface at y63. It provides a safe landing before any build command.

Run as a player:

```mcfunction
/function aurora_lab:enter
/function aurora_lab:build
/function aurora_lab:status
```

Wait near the starting position for chunks to load before build. The build requires
the player within 8 blocks of (0,64,0) in the lab dimension and checks all 36 involved
chunks before writing anything. If it returns without a completion message, inspect
status; when not started, wait/increase the test world's view/simulation distance
and retry. No forced chunks, scheduled commands or load/tick functions exist.

The build writes only x/z -40..39 and y47..82 inside the dedicated dimension.
Its largest fill is 30,400 blocks (below the ordinary 32,768 limit). A persistent
`aurora_lab:state` started lock is set before edits; 25 critical static block checks
must pass before ready is set. A started-but-not-ready state is a **partial build**,
not success. No automatic rollback/reset/rebuild exists: recover with a fresh
disposable world, not by clearing the lock over later user edits. Engine interruption
or custom command limits are not transactional guarantees. A completed build never
runs again over later construction.

## Geometry and depth calibration

All still pools have source water in their upper cell y63. In the flat interior,
the ordinary exposed source-water surface is expected near **63+8/9**, not y64;
verify the actual surface in the tested version/resource pack. The source-cell
count is a block-grid calibration, not optical ray length.

| Pool / sample x,z | Floor block y (top plane) | Source-water y / cells | Expected vertical free-surface gap |
|---|---|---|---|
| Shallow / -21,-21 | 61 (62) | 62..63 / 2 | about 1.8889 blocks |
| Deep / 21,-21 | 47 (48) | 48..63 / 16 | about 15.8889 blocks |
| Covered cave / -20,24 | 59 (60) | 60..63 / 4 | about 3.8889 blocks |
| Glass/ice strip / 8,18 | 61 (62) | 62..63 / 2 | about 1.8889 blocks |
| Fall catch basin / 26,30 | 59 (60) | 60..63 / 4 | about 3.8889 blocks |

Colored walls/pillars and thin iron bars provide reflection and silhouette targets.
The covered pool has a roof at y70 and a dry dock with two torches. The southeast
strip contains a glass panel and ordinary ice as **non-water controls**.

The raised trough has source water at y72, floor y71 and an open outlet toward **+Z**.
It should develop a vanilla flow across six exposed channel cells and fall at z19
into the catch basin. Wait for normal fluid updates before recording it. The
sentinels verify source/trough geometry, not the yet-unobserved settled flow.
These are real vanilla fluid inputs; they do not claim Aurora implements custom flow.

## Nine fixed camera functions

Use first person, fixed FOV (suggested 70), 16:9 resolution and unchanged shader/
resource settings for comparisons. Coordinates below are **feet**, yaw/pitch in
degrees. Standing/spectator eye height is assumed 1.62 blocks; crouching, swimming,
third person, camera mods and future displaced water can change the result.

Functions never change game mode. Select spectator manually for the marked poses
(e.g. `/gamemode spectator` in this disposable world). Standing poses should be
viewed upright and grounded; use the same posture on both sides of an A/B test.

Prefix every name with `/function aurora_lab:view/`.

| Name | Feet x,y,z | Yaw / pitch | Posture and purpose | Observed result |
|---|---|---|---|---|
| shallow_overhead | -21.5,82,-21.5 | 180 / 90 | Spectator; vertical depth/normal baseline | |
| deep_grazing | 21.5,64,-3.5 | 180 / 6 | Standing on ground; grazing reflection/depth | |
| cave | -20.5,64,11.5 | 0 / 10 | Standing on dock; local torch light/no outdoor sky | |
| glass_ice | 1.5,64,18.5 | -90 / 12 | Standing; glass/ice classification and overlap | |
| waterfall | 32.5,70,29.5 | 135 / 18 | Spectator; +Z channel and falling side/impact | |
| underwater | 21.5,54,-21.5 | 180 / -45 | Spectator; center ray reaches the interface inside the deep pool | |
| waterline_above | 21.5,62.468888889,-21.5 | 180 / 0 | Spectator; nominal eye 0.20 blocks above surface | |
| waterline_center | 21.5,62.268888889,-21.5 | 180 / 0 | Spectator; nominal eye at surface, then gentle vertical sweep | |
| waterline_below | 21.5,62.068888889,-21.5 | 180 / 0 | Spectator; nominal eye 0.20 blocks below surface | |

The above/below poses are medium controls; at a level view they are too far from
a roughly 0.05-block near plane to guarantee a split waterline. Use **center plus a
slow spectator vertical sweep** through the surface for that experiment. Record
actual FOV, eye/feet height, posture, pitch and observed fluid classification.
Minecraft's eye-fluid test and rendered interface can differ; this fixture does
not prove per-pixel medium handling or a successful split-screen result.

## Optional time/weather track — disposable world only

These are manual commands, never part of the data pack. Time/weather/game rules
can affect the save beyond this dimension; use them only in the disposable test
save, with the state recorded before comparisons.

```mcfunction
/gamerule minecraft:advance_time false
/gamerule minecraft:advance_weather false
/time set 6000
/weather clear
```

| Capture condition | Manual change |
|---|---|
| Noon / baseline | `/time set 6000` and `/weather clear` |
| Sunset | `/time set 12000` |
| Night | `/time set 18000` |
| Rain | `/time set 6000` and `/weather rain`; wait for the transition to settle |

Record shader revision, Iris/Fabric/game versions, GPU/driver, resolution, FOV,
resource pack, camera, time/weather and settings. Compare normal rendering with
DEBUG_VIEW 7/8/9, then SSR off/on and 64/128 budgets without changing the scene.
Capture both a still and a short motion sequence. Empty result cells remain
unobserved; screenshots or FPS are not invented by the static checker.

## What is checked without Minecraft

The [static validator](../../tools/validate_water_lab.py) passed: 36 loaded-chunk
guards, 50 bounded block operations, 25 completion sentinels, five calibrated
water columns and all nine camera poses. Nine in-memory negative controls rejected
missing guards, unsafe dimensions/bounds and forbidden automatic/world-state commands.
Run from the repository with `python -B tools/validate_water_lab.py`.

The separate repository validator checks the exact pack format/dimension schema,
isolated absolute block bounds, one-shot/load guards, fill volumes, critical
geometry, camera containment and intended eye/center-ray relationships. It does
not run Mojang's command parser, simulate fluid/light updates, load the dimension,
test shader integration or measure performance. Build-ready describes static
sentinels only.

Schema references were checked against the installed official 1.21.11 client
resources: version.json, the flat world preset and built-in data-pack metadata.
No game resources are copied into this fixture.

- [1.21.11 release notes: data format and game-rule names](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-11).
- [1.21.9 pack metadata: min_format/max_format and minor versions](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-9).
- [1.21 singular function directories](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21).
