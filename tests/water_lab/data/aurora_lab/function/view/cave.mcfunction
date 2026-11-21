# Explicit camera pose only. Coordinates are feet, not eye position.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run return fail
execute unless data storage aurora_lab:state ready run return fail
tp @s -20.5 64.0 11.5 0.0 10.0
