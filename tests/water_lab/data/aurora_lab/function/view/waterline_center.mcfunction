# Nominal flat source-waterline center. Feet + 1.62 = 63 + 8/9.
# A gentle spectator vertical sweep is the actual split-waterline experiment.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run return fail
execute unless data storage aurora_lab:state ready run return fail
execute unless entity @s[gamemode=spectator] run tellraw @s {"text":"This pose requires spectator mode. Keep first-person posture and gently sweep vertically through the nominal waterline.","color":"yellow"}
execute unless entity @s[gamemode=spectator] run return fail
tp @s 21.5 62.268888889 -21.5 180.0 0.0
