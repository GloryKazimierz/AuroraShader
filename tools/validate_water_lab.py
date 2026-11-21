"""Read-only domain checks for the hand-authored Java 1.21.11 water lab.

This checks authored data and commands, not Minecraft command execution or fluid
simulation. Run: python -B tools/validate_water_lab.py
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'tests' / 'water_lab'
NAMESPACE = 'aurora_lab'
DIMENSION = 'aurora_lab:water'
BOUNDS = ((-40,47,-40),(39,82,39))
EYE_HEIGHT = 1.62  # Default standing/spectator player; no posture/scale changes.
SOURCE_SURFACE = 63 + 8/9  # Exposed source fluid with no water block above.


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON field: '+key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique_object)


def commands(path):
    lines = []
    for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        require(line == line.rstrip(),str(path)+': trailing whitespace')
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            require(not stripped.startswith('/'),str(path)+': functions omit the command slash')
            lines.append((number,stripped))
    return lines


def block_operation(command):
    """Parse only absolute fill/setblock commands used by this small fixture."""
    parts = command.split()
    require(parts and parts[0] in ('fill','setblock'),'Unexpected block command: '+command)
    count = 6 if parts[0]=='fill' else 3
    require(len(parts)==count+2,'Unexpected block command arguments: '+command)
    require(all(re.fullmatch(r'-?\d+',value) for value in parts[1:count+1]),'Coordinates must be absolute integers')
    values = tuple(map(int,parts[1:count+1]))
    first,last = (values[:3],values[3:]) if count==6 else (values,values)
    lower = tuple(min(a,b) for a,b in zip(first,last))
    upper = tuple(max(a,b) for a,b in zip(first,last))
    require(all(lo<=a<=b<=hi for lo,a,b,hi in zip(BOUNDS[0],lower,upper,BOUNDS[1])),
            'Block write escapes lab bounds: '+command)
    require(math.prod(b-a+1 for a,b in zip(lower,upper))<=32768,'Fill exceeds default command block limit')
    block = parts[-1]
    require(re.fullmatch(r'minecraft:[a-z_]+(?:\[[a-z0-9_=,]+\])?',block) is not None,
            'Unexpected block/NBT syntax: '+block)
    return lower,upper,block


def block_at(operations, point):
    """Last authored write wins; no block updates, chunk loading or game actions."""
    for lower,upper,block in reversed(operations):
        if all(a<=value<=b for a,value,b in zip(lower,point,upper)):
            return block
    if point[1] == -64:
        return 'minecraft:bedrock'
    return 'minecraft:stone' if -63<=point[1]<=63 else 'minecraft:air'


def is_water(block):
    return block in ('minecraft:water','minecraft:water[level=0]')


def eye_medium(operations, position):
    point = tuple(math.floor(value) for value in position)
    block = block_at(operations,point)
    if is_water(block):
        above = block_at(operations,(point[0],point[1]+1,point[2]))
        top = point[1]+(1 if is_water(above) else 8/9)
        return 'water' if position[1]<top else 'air'
    return 'air' if block=='minecraft:air' else 'solid'


def view_direction(yaw,pitch):
    yaw,pitch = math.radians(yaw),math.radians(pitch)
    return (-math.sin(yaw)*math.cos(pitch),-math.sin(pitch),math.cos(yaw)*math.cos(pitch))


def validate_pack():
    manifest = read_json(LAB/'pack.mcmeta')
    require(set(manifest)=={'pack'},'Unexpected pack root fields')
    pack = manifest['pack']
    require(set(pack)=={'min_format','max_format','description'},'Unexpected pack metadata')
    require(pack['min_format']==pack['max_format']==[94,1],'Pack must target Java1.21.11 format94.1')
    require(isinstance(pack['description'],str) and pack['description'].strip(),'Missing pack description')
    dimension_path = LAB/'data'/NAMESPACE/'dimension'/'water.json'
    dimension = read_json(dimension_path)
    require(set(dimension)=={'type','generator'} and dimension['type']=='minecraft:overworld',
            'Lab must use the existing overworld dimension type')
    generator = dimension['generator']
    require(set(generator)=={'type','settings'} and generator['type']=='minecraft:flat','Unexpected generator')
    settings = generator['settings']
    require(set(settings)=={'biome','features','lakes','layers','structure_overrides'},'Unexpected flat settings')
    require(settings['biome']=='minecraft:ocean' and settings['features'] is False and settings['lakes'] is False,
            'Lab generation must be deterministic with no extra features/lakes')
    require(settings['structure_overrides']==[],'Structures must be disabled')
    require(settings['layers']==[{'block':'minecraft:bedrock','height':1},{'block':'minecraft:stone','height':127}],
            'Expected overworld-minY=-64 base ending at stone y63')
    functions = {}
    for path in sorted(LAB.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(LAB).as_posix()
        if relative in ('pack.mcmeta','README.md','README.zh-CN.md','scene.json','data/aurora_lab/dimension/water.json'):
            continue
        match = re.fullmatch(r'data/aurora_lab/function/((?:view/)?[a-z_]+)\.mcfunction',relative)
        require(match is not None,'Unexpected datapack file or automatic hook: '+relative)
        name = match[1]
        require(name in ('build','enter','status') or name.startswith('view/'),'Unexpected public function: '+name)
        functions[name] = commands(path)
    require({'build','enter','status'}<=set(functions),'Missing public lab functions')
    require(any(name.startswith('view/') for name in functions),'No camera functions')
    return functions


def validate_geometry(operations):
    # Independent scene requirements, not regenerated command-by-command expectations.
    pools = (('shallow',-21,-21,61,2),('deep',21,-21,47,16),
             ('cave',-21,25,59,4),('material strip',11,32,61,2),('catch basin',28,30,59,4))
    for name,x,z,floor,depth in pools:
        require(block_at(operations,(x,floor,z)) not in ('minecraft:air','minecraft:water','minecraft:water[level=0]'),
                name+': missing solid floor')
        for y in range(floor+1,64):
            require(is_water(block_at(operations,(x,y,z))),name+': missing source water at y'+str(y))
        require(63-floor==depth,name+': wrong authored column depth')
        require(block_at(operations,(x,64,z))=='minecraft:air',name+': obstructed top')
    require(block_at(operations,(-20,63,10)) not in ('minecraft:air','minecraft:water','minecraft:water[level=0]'),
            'Cave dock must be dry and solid')
    require(block_at(operations,(-20,65,10))=='minecraft:air','Cave dock eye space is obstructed')
    require(block_at(operations,(-21,70,25))=='minecraft:deepslate',
            'Cave must have an opaque roof')
    require('glass' in block_at(operations,(9,65,13)),'Missing glass classification control')
    require(block_at(operations,(10,63,24))=='minecraft:ice','Missing ice classification control')
    require(is_water(block_at(operations,(10,62,24))),'Ice control must retain water below')
    require(block_at(operations,(21,71,10)) not in ('minecraft:air','minecraft:water','minecraft:water[level=0]'),
            'Raised trough has no floor')
    require(is_water(block_at(operations,(21,72,10))),'Raised trough has no source water')
    require(block_at(operations,(21,72,19))=='minecraft:air','Raised trough outlet must be open')
    require(block_at(operations,(21,71,19))=='minecraft:air','Waterfall outlet is blocked below')
    print('PASS: five authored pool depths (2/16/4/2/4 cells), dry cave dock/roof, glass/ice and open waterfall outlet')


PLAYER_GUARD = 'execute unless entity @s[type=minecraft:player] run return fail'
DIMENSION_GUARD = 'execute unless dimension aurora_lab:water run return fail'
READY_GUARD = 'execute unless data storage aurora_lab:state ready run return fail'
SPECTATOR_GUARD = 'execute unless entity @s[gamemode=spectator] run return fail'
BLOCKS = {'minecraft:'+name for name in ('air','polished_andesite','gold_block','smooth_stone',
          'white_concrete','gray_concrete','red_concrete','yellow_concrete','blue_concrete',
          'iron_bars','water[level=0]','deepslate','torch','glass','ice')}
CONTEXTS = {'unless entity @s[type=minecraft:player]','unless dimension aurora_lab:water',
            'positioned 0 64 0 unless entity @s[distance=..8]',
            'if data storage aurora_lab:state started','unless data storage aurora_lab:state started',
            'if data storage aurora_lab:state ready','unless data storage aurora_lab:state ready',
            'if data storage aurora_lab:state started unless data storage aurora_lab:state ready',
            'unless entity @s[gamemode=spectator]','in aurora_lab:water'}


def validate_command(name, command):
    context = None
    leaf = command
    if command.startswith('execute '):
        require(' run ' in command,'Missing execute run')
        context,leaf = command[8:].split(' run ',1)
        known = context in CONTEXTS or re.fullmatch(r'unless loaded -?\d+ 64 -?\d+',context)
        known = known or re.fullmatch(r'unless block -?\d+ -?\d+ -?\d+ minecraft:[a-z_]+(?:\[level=0\])?',context)
        require(known,'Unexpected execute context: '+context)
    if leaf.startswith('tellraw @s '):
        text = json.loads(leaf[len('tellraw @s '):],object_pairs_hook=unique_object)
        require(isinstance(text,dict) and set(text)<={'text','color'} and isinstance(text.get('text'),str),
                'Status messages must be plain text without interactive actions')
    elif leaf.startswith(('fill ','setblock ')):
        require(name=='build' and context is None,'Block writes belong only to the guarded build')
        require(block_operation(leaf)[2] in BLOCKS,'Unexpected fixture block')
    elif leaf.startswith('data '):
        require(name=='build' and context is None,'State writes belong only to the guarded build')
        require(leaf in ('data modify storage aurora_lab:state started set value 1b',
                         'data modify storage aurora_lab:state schema set value 1',
                         'data modify storage aurora_lab:state ready set value 1b'),'Unexpected state mutation')
    elif leaf.startswith('tp @s '):
        require((name=='enter' and context=='in aurora_lab:water') or (name.startswith('view/') and context is None),
                'Unexpected teleport target/context')
        values = leaf.split()[2:]
        require(len(values)==5,'Camera must specify feet XYZ and yaw/pitch')
        require(all(math.isfinite(float(value)) for value in values),'Nonfinite camera')
    elif leaf=='return fail':
        require(context is not None and context!='in aurora_lab:water','Unexpected unconditional return')
    elif leaf=='return 1':
        require(name=='build' and context is None,'Unexpected return')
    else:
        raise AssertionError('Unsupported or unintended command: '+command)


def validate_build(functions):
    for name,lines in functions.items():
        require(lines and lines[0][1]==PLAYER_GUARD,name+': missing leading player guard')
        for number,command in lines:
            validate_command(name,command)
    build = [command for _,command in functions['build']]
    mutation_indices = [i for i,command in enumerate(build) if command.startswith(('fill ','setblock ','data '))]
    require(mutation_indices,'No build mutations')
    first = mutation_indices[0]
    prefix = build[:first]
    for guard in (DIMENSION_GUARD,
                  'execute positioned 0 64 0 unless entity @s[distance=..8] run return fail',
                  'execute if data storage aurora_lab:state started run return fail'):
        require(guard in prefix,'Build guard must precede all writes: '+guard)
    loaded = [tuple(map(int,re.fullmatch(r'execute unless loaded (-?\d+) 64 (-?\d+) run return fail',line).groups()))
              for line in prefix if re.fullmatch(r'execute unless loaded (-?\d+) 64 (-?\d+) run return fail',line)]
    require(len(loaded)==36 and set(loaded)=={(x*16,z*16) for x in range(-3,3) for z in range(-3,3)},
            'All36 build chunks must be checked before the lock or any block write')
    require(build[first]=='data modify storage aurora_lab:state started set value 1b','Started lock must be first mutation')
    states = [line for line in build if line.startswith('data ')]
    require(states==['data modify storage aurora_lab:state started set value 1b',
                     'data modify storage aurora_lab:state schema set value 1',
                     'data modify storage aurora_lab:state ready set value 1b'],'Unexpected state transitions')
    operations = [block_operation(line) for line in build if line.startswith(('fill ','setblock '))]
    last_block = max(i for i,line in enumerate(build) if line.startswith(('fill ','setblock ')))
    ready = build.index(states[-1])
    sentinels = []
    for line in build[last_block+1:ready]:
        match = re.fullmatch(r'execute unless block (-?\d+) (-?\d+) (-?\d+) (\S+) run return fail',line)
        require(match is not None,'Only block verification may occur between final block write and ready')
        point = tuple(map(int,match.groups()[:3]))
        require(block_at(operations,point)==match[4],'Ready sentinel mismatches authored geometry: '+line)
        sentinels.append(point)
    require(len(sentinels)==25 and len(set(sentinels))==25,'Expected25 distinct critical completion sentinels')
    require(ready==mutation_indices[-1] and build[-1]=='return 1','Ready must be the final mutation')
    require('execute in aurora_lab:water run tp @s 0.5 64 0.5 180 0' in dict(functions['enter']).values(),
            'Enter must teleport only the caller to the isolated lab start')
    require([line for _,line in functions['status']][1]==DIMENSION_GUARD,'Status requires the lab dimension')
    require(block_at(operations,(0,63,0))=='minecraft:gold_block','Start platform missing')
    print('PASS: player/dimension/radius/one-shot guards;36 loaded chunks before writes;{} bounded block commands and25 verified completion sentinels'.format(len(operations)))
    return operations


def validate_cameras(functions, operations):
    scene = read_json(LAB/'scene.json')
    require(scene['schema']==1 and scene['minecraft_version']=='1.21.11' and scene['data_pack_format']==[94,1],
            'Scene metadata targets the wrong schema/version')
    require(scene['dimension']==DIMENSION and scene['storage']=='aurora_lab:state','Wrong scene namespace')
    require(scene['build_bounds']=={'min':list(BOUNDS[0]),'max':list(BOUNDS[1])},'Wrong documented build bounds')
    require(scene['build_center']==[0,64,0] and scene['build_radius']==8,'Wrong documented build guard')
    require(scene['chunk_range']=={'x':[-3,2],'z':[-3,2]},'Wrong chunk range')
    require(scene['runtime_status']=='unobserved','Static checks cannot declare game runtime success')
    expected_depths = {'shallow':2,'deep':16,'cave':4,'glass_ice':2,'catch':4}
    require(set(scene['pools'])==set(expected_depths),'Expected five documented pool samples')
    for name,pool in scene['pools'].items():
        x,z = pool['sample'];floor = pool['floor_y']
        require(pool['water_y']==[floor+1,63] and 63-floor==expected_depths[name],
                name+': documented pool depth differs')
        require(block_at(operations,(x,floor,z)) not in ('minecraft:air','minecraft:water','minecraft:water[level=0]'),
                name+': documented sample has no floor')
        require(all(is_water(block_at(operations,(x,y,z))) for y in range(floor+1,64)),
                name+': documented sample has missing water')
    require(scene['standing_or_spectator_eye_height']==EYE_HEIGHT and abs(scene['expected_flat_source_surface_y']-SOURCE_SURFACE)<1e-12,
            'Wrong eye-height/surface calibration')
    names = {'shallow_overhead','deep_grazing','cave','glass_ice','waterfall','underwater',
             'waterline_above','waterline_center','waterline_below'}
    require(set(scene['cameras'])==names,'Expected9 explicit camera views')
    require(set(functions)=={'build','enter','status'}|{'view/'+name for name in names},'Function/camera set differs')
    views = {}
    for name,pose in scene['cameras'].items():
        lines = [line for _,line in functions['view/'+name]]
        require(lines[:3]==[PLAYER_GUARD,DIMENSION_GUARD,READY_GUARD],name+': camera lacks leading guards')
        require((SPECTATOR_GUARD in lines)==pose['spectator'],name+': spectator requirement differs')
        teleports = [line for line in lines if line.startswith('tp @s ')]
        require(len(teleports)==1 and lines[-1]==teleports[0],name+': expected one final teleport')
        values = tuple(map(float,teleports[0].split()[2:]))
        require(values==tuple(pose['feet'])+(pose['yaw'],pose['pitch']),name+': pose differs from scene manifest')
        feet,yaw,pitch = values[:3],values[3],values[4]
        require(-180<=yaw<=180 and -90<=pitch<=90,name+': invalid rotation')
        eye = (feet[0],feet[1]+EYE_HEIGHT,feet[2])
        if not pose['spectator']:
            require(eye_medium(operations,eye)=='air',name+': walking camera eye must be in air')
            floor = block_at(operations,(math.floor(feet[0]),math.floor(feet[1])-1,math.floor(feet[2])))
            require(floor not in ('minecraft:air','minecraft:water','minecraft:water[level=0]'),name+': no walking support')
        views[name] = (eye,view_direction(yaw,pitch))
    regions = {'shallow_overhead':(-35,-7,-35,-7),'deep_grazing':(7,35,-35,-7),
               'underwater':(7,35,-35,-7),'cave':(-35,-7,15,35),'glass_ice':(7,13,7,35)}
    for name,(xmin,xmax,zmin,zmax) in regions.items():
        eye,direction = views[name]
        distance = (SOURCE_SURFACE-eye[1])/direction[1]
        require(distance>0,name+': camera faces away from the water interface')
        x,z = eye[0]+direction[0]*distance,eye[2]+direction[2]*distance
        require(xmin<=x<xmax+1 and zmin<=z<zmax+1,name+': central ray misses intended water region')
    require(eye_medium(operations,views['underwater'][0])=='water','Underwater camera eye must be submerged')
    for name,offset,medium in (('waterline_above',.2,'air'),('waterline_below',-.2,'water'),('waterline_center',0,None)):
        eye,direction = views[name]
        require(abs(eye[1]-(SOURCE_SURFACE+offset))<1e-8,name+': wrong nominal eye height')
        require(abs(direction[1])<1e-14 and direction[2]<-.99,name+': expected level north-facing camera')
        require(7<eye[0]<35 and -35<eye[2]<-7,name+': waterline point outside deep pool')
        require(scene['cameras'][name]['spectator'] is True,name+': requires stable spectator posture')
        if medium:
            require(eye_medium(operations,eye)==medium,name+': wrong predicted eye medium')
    eye,direction = views['waterfall'];distance = (19-eye[2])/direction[2]
    x,y = eye[0]+direction[0]*distance,eye[1]+direction[1]*distance
    require(distance>0 and 18<=x<=25 and 64<y<73,'Waterfall camera does not face the falling-water corridor')
    print('PASS:9 manifest-matched guarded cameras; water-interface/waterfall directions and spectator waterline center/above/below placement')


def main():
    functions = validate_pack()
    operations = validate_build(functions)
    validate_geometry(operations)
    validate_cameras(functions,operations)
    print('PASS: isolated Java1.21.11 datapack; no load/tick/schedule/forceload, global game commands or Overworld block writes')
    print('LIMIT: authored data only; commands, fluid settling, camera boundary and Minecraft/Iris appearance remain unobserved')


if __name__ == '__main__':
    main()
