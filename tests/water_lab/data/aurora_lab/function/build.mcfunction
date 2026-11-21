# One-shot explicit build. Only this file may change blocks.
# Bounds: x/z -40..39; y 47..82. No scheduled work or forced chunks.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run tellraw @s {"text":"Enter the dedicated lab dimension first.","color":"red"}
execute unless dimension aurora_lab:water run return fail
execute positioned 0 64 0 unless entity @s[distance=..8] run tellraw @s {"text":"Stand near the central start at 0 64 0, then retry.","color":"red"}
execute positioned 0 64 0 unless entity @s[distance=..8] run return fail
execute if data storage aurora_lab:state started run tellraw @s {"text":"Build already started or completed. No rebuild is allowed. Check status; use a new disposable world for recovery.","color":"red"}
execute if data storage aurora_lab:state started run return fail
tellraw @s {"text":"Checking all 36 chunks. If no completion appears, wait near the start with sufficient view/simulation distance and retry only if status has no started lock.","color":"yellow"}
execute unless loaded -48 64 -48 run return fail
execute unless loaded -48 64 -32 run return fail
execute unless loaded -48 64 -16 run return fail
execute unless loaded -48 64 0 run return fail
execute unless loaded -48 64 16 run return fail
execute unless loaded -48 64 32 run return fail
execute unless loaded -32 64 -48 run return fail
execute unless loaded -32 64 -32 run return fail
execute unless loaded -32 64 -16 run return fail
execute unless loaded -32 64 0 run return fail
execute unless loaded -32 64 16 run return fail
execute unless loaded -32 64 32 run return fail
execute unless loaded -16 64 -48 run return fail
execute unless loaded -16 64 -32 run return fail
execute unless loaded -16 64 -16 run return fail
execute unless loaded -16 64 0 run return fail
execute unless loaded -16 64 16 run return fail
execute unless loaded -16 64 32 run return fail
execute unless loaded 0 64 -48 run return fail
execute unless loaded 0 64 -32 run return fail
execute unless loaded 0 64 -16 run return fail
execute unless loaded 0 64 0 run return fail
execute unless loaded 0 64 16 run return fail
execute unless loaded 0 64 32 run return fail
execute unless loaded 16 64 -48 run return fail
execute unless loaded 16 64 -32 run return fail
execute unless loaded 16 64 -16 run return fail
execute unless loaded 16 64 0 run return fail
execute unless loaded 16 64 16 run return fail
execute unless loaded 16 64 32 run return fail
execute unless loaded 32 64 -48 run return fail
execute unless loaded 32 64 -32 run return fail
execute unless loaded 32 64 -16 run return fail
execute unless loaded 32 64 0 run return fail
execute unless loaded 32 64 16 run return fail
execute unless loaded 32 64 32 run return fail
# The persistent lock precedes every mutation. A partial build stays locked.
data modify storage aurora_lab:state started set value 1b
data modify storage aurora_lab:state schema set value 1
# Clear only this new dedicated fixture footprint; each fill is <=32768 blocks.
fill -40 64 -40 -1 82 -1 minecraft:air
fill -40 64 0 -1 82 39 minecraft:air
fill 0 64 -40 39 82 -1 minecraft:air
fill 0 64 0 39 82 39 minecraft:air
fill -3 63 -3 3 63 3 minecraft:polished_andesite
setblock 0 63 0 minecraft:gold_block
# Shallow pool: two source-water cells; floor block y61.
fill -36 61 -36 -6 64 -6 minecraft:smooth_stone
fill -35 62 -35 -7 75 -7 minecraft:air
fill -35 61 -35 -7 61 -7 minecraft:white_concrete
fill -31 61 -35 -28 61 -7 minecraft:gray_concrete
fill -23 61 -35 -20 61 -7 minecraft:gray_concrete
fill -15 61 -35 -12 61 -7 minecraft:gray_concrete
fill -35 62 -35 -7 63 -7 minecraft:water[level=0]
fill -31 64 -34 -25 69 -33 minecraft:red_concrete
fill -21 64 -30 -20 71 -29 minecraft:yellow_concrete
fill -15 64 -34 -10 67 -33 minecraft:blue_concrete
fill -24 64 -30 -24 69 -30 minecraft:iron_bars
# Deep pool: sixteen source-water cells; floor block y47.
fill 6 47 -36 36 64 -6 minecraft:smooth_stone
fill 7 48 -35 35 75 -7 minecraft:air
fill 7 47 -35 35 47 -7 minecraft:white_concrete
fill 11 47 -35 14 47 -7 minecraft:gray_concrete
fill 19 47 -35 22 47 -7 minecraft:gray_concrete
fill 27 47 -35 30 47 -7 minecraft:gray_concrete
fill 7 48 -35 35 63 -7 minecraft:water[level=0]
fill 10 64 -34 16 69 -33 minecraft:red_concrete
fill 22 64 -30 23 71 -29 minecraft:yellow_concrete
fill 28 64 -34 33 67 -33 minecraft:blue_concrete
fill 19 64 -30 19 69 -30 minecraft:iron_bars
# Covered pool, four water cells, north entrance and dry torch dock.
fill -36 59 6 -6 70 36 minecraft:deepslate
fill -35 60 7 -7 69 35 minecraft:air
fill -35 60 7 -7 63 35 minecraft:water[level=0]
fill -23 64 6 -17 66 6 minecraft:air
fill -24 63 6 -16 63 14 minecraft:smooth_stone
setblock -23 64 10 minecraft:torch
setblock -17 64 10 minecraft:torch
# Glass and ordinary-ice controls over a separate two-cell pool.
fill 6 61 6 14 64 36 minecraft:smooth_stone
fill 7 62 7 13 76 35 minecraft:air
fill 7 62 7 13 63 35 minecraft:water[level=0]
fill 9 63 10 9 67 16 minecraft:glass
fill 9 63 21 11 63 27 minecraft:ice
# Four-cell catch pool.
fill 15 59 18 34 64 36 minecraft:smooth_stone
fill 16 60 19 33 76 35 minecraft:air
fill 16 60 19 33 63 35 minecraft:water[level=0]
# Raised trough: source at north; six exposed channel cells then +Z fall.
fill 17 70 7 25 73 18 minecraft:smooth_stone
fill 18 72 8 24 74 18 minecraft:air
fill 18 72 8 24 72 12 minecraft:water[level=0]
fill 17 64 7 17 69 7 minecraft:smooth_stone
fill 25 64 7 25 69 7 minecraft:smooth_stone
fill 17 64 18 17 69 18 minecraft:smooth_stone
fill 25 64 18 25 69 18 minecraft:smooth_stone
# Critical sentinels: no ready flag unless the authored static fixture exists.
execute unless block 0 63 0 minecraft:gold_block run return fail
execute unless block -21 61 -21 minecraft:gray_concrete run return fail
execute unless block -21 62 -21 minecraft:water[level=0] run return fail
execute unless block -21 63 -21 minecraft:water[level=0] run return fail
execute unless block -21 64 -21 minecraft:air run return fail
execute unless block 21 47 -21 minecraft:gray_concrete run return fail
execute unless block 21 48 -21 minecraft:water[level=0] run return fail
execute unless block 21 63 -21 minecraft:water[level=0] run return fail
execute unless block 21 64 -21 minecraft:air run return fail
execute unless block -20 59 24 minecraft:deepslate run return fail
execute unless block -20 60 24 minecraft:water[level=0] run return fail
execute unless block -20 63 24 minecraft:water[level=0] run return fail
execute unless block -20 70 24 minecraft:deepslate run return fail
execute unless block -20 63 11 minecraft:smooth_stone run return fail
execute unless block -23 64 10 minecraft:torch run return fail
execute unless block 8 61 18 minecraft:smooth_stone run return fail
execute unless block 8 62 18 minecraft:water[level=0] run return fail
execute unless block 9 65 13 minecraft:glass run return fail
execute unless block 10 63 24 minecraft:ice run return fail
execute unless block 26 59 30 minecraft:smooth_stone run return fail
execute unless block 26 60 30 minecraft:water[level=0] run return fail
execute unless block 26 63 30 minecraft:water[level=0] run return fail
execute unless block 21 71 15 minecraft:smooth_stone run return fail
execute unless block 21 72 10 minecraft:water[level=0] run return fail
execute unless block 21 71 19 minecraft:air run return fail
data modify storage aurora_lab:state ready set value 1b
tellraw @s {"text":"Aurora water lab built and static sentinels verified. Wait for vanilla fluid updates before the waterfall comparison. No reset/rebuild command is provided.","color":"green"}
return 1
