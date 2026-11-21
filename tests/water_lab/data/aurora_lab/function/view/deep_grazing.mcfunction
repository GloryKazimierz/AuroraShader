# Explicit camera pose only. Coordinates are feet, not eye position.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run return fail
execute unless data storage aurora_lab:state ready run return fail
tp @s 21.5 64.0 -3.5 180.0 6.0
