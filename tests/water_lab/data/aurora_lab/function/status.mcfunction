# Read-only status, no reset or state changes.
execute unless entity @s[type=minecraft:player] run return fail
execute unless dimension aurora_lab:water run return fail
execute unless data storage aurora_lab:state started run tellraw @s {"text":"Not started. A guarded first build is available near 0 64 0.","color":"yellow"}
execute if data storage aurora_lab:state started unless data storage aurora_lab:state ready run tellraw @s {"text":"PARTIAL BUILD: started but not ready. Rebuild is locked. Use a new disposable test world; do not clear the lock over user edits.","color":"red"}
execute if data storage aurora_lab:state ready run tellraw @s {"text":"Static fixture ready. Runtime rendering and fluid settling still require observation.","color":"green"}
