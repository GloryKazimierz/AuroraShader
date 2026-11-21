# Explicit player teleport only; flat ground already provides a safe landing.
execute unless entity @s[type=minecraft:player] run return fail
execute in aurora_lab:water run tp @s 0.5 64 0.5 180 0
tellraw @s {"text":"Aurora lab: stand here, wait for chunks, then /function aurora_lab:build. Use only a new disposable D: test world.","color":"yellow"}
