# Explicit camera pose only. Coordinates are feet, not eye position.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run return fail
execute unless data storage aurora_lab:state ready run return fail
execute unless entity @s[gamemode=spectator] run tellraw @s {"text":"This pose requires spectator mode for stable eye height and no falling/buoyancy. Select it manually in the disposable test world.","color":"yellow"}
execute unless entity @s[gamemode=spectator] run return fail
tp @s -21.5 82.0 -21.5 180.0 90.0
