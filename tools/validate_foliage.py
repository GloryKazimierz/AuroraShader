"""M18 shared foliage displacement, root weighting and pass-transform contracts."""
import math
from validate_water_debug import DEBUG_FILES
import re
import struct
import subprocess
from pathlib import Path
from itertools import product
from validate_celestial_glow import GLOW_OPTIONS, restore_celestial_glow_source
from validate_water_filtered_waves import FILTER_OPTIONS
from validate_water_screen_reflection import REFLECTION_OPTIONS

M17_BASELINE = 'b26755b1c3e611dd18a4836db305d6188dafd052'
FOLIAGE_OPTIONS = {'FOLIAGE_WIND','FOLIAGE_WIND_STRENGTH','FOLIAGE_WIND_SPEED'}
TAU = 2*math.pi
MAX_FIELD = math.sqrt(.52)
IDENTITY4 = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))


def finite(values):
    return all(math.isfinite(value) for value in values)


def clamp(value,lo=0.0,hi=1.0):
    return min(hi,max(lo,value))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def matrix_vector(matrix,vector):
    return tuple(dot(row,vector) for row in matrix)


def inverse_matrix(matrix):
    size=len(matrix)
    rows=[list(map(float,row))+[float(i==j) for j in range(size)] for i,row in enumerate(matrix)]
    for column in range(size):
        pivot=max(range(column,size),key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column])<=1e-15:
            raise ValueError('Singular matrix')
        rows[column],rows[pivot]=rows[pivot],rows[column]
        scale=rows[column][column]
        rows[column]=[value/scale for value in rows[column]]
        for row in range(size):
            if row!=column:
                factor=rows[row][column]
                rows[row]=[x-factor*y for x,y in zip(rows[row],rows[column])]
    return tuple(tuple(row[size:]) for row in rows)


def f32(value):
    try:
        return struct.unpack('f',struct.pack('f',value))[0]
    except OverflowError:
        return math.copysign(math.inf,value)


def fract(value):
    return value-math.floor(value)


def wind_cycle(seconds,speed=1,fp32_time=False):
    seconds=max(seconds,0) if math.isfinite(seconds) else 0
    phase=f32(f32(seconds)*f32(speed/200)) if fp32_time else seconds*(speed/200)
    return fract(phase)


def anchored_tile(camera_int,camera_fract,player_position):
    return tuple(fract(((camera_int[index]&127)+camera_fract[index]+player_position[index])/128)
                 for index in (0,2))


def foliage_field(tile,seconds=0,speed=1,fp32_time=False):
    cycle=wind_cycle(seconds,speed,fp32_time)
    a=.6*math.sin(TAU*fract(tile[0]+2*tile[1]+37*cycle))
    b=.4*math.sin(TAU*fract(3*tile[0]-tile[1]-53*cycle))
    # An orthonormal pair gives norm^2=a^2+b^2, independently bounding the field.
    return .8*a-.6*b,.6*a+.8*b


def grass_bend(material_id,mid_y):
    if material_id not in (10003,10004,10005) or not math.isfinite(mid_y):
        return 0.0
    height=.5-mid_y/64+(1 if material_id==10005 else 0)
    full_height=1 if material_id==10003 else 2
    return clamp((height-1/64)/(full_height-1/64))**2


def foliage_displacement(player_position,material,mid_block,camera_int=(0,0,0),camera_fract=(0,0,0),
                         seconds=0,strength=.5,speed=1,enabled=True,mode=1,debug=0,fp32_time=False):
    if not enabled or not mode or debug or strength<=0:
        return (0.0,0.0,0.0)
    if not finite(material) or material[1] not in (0,-1) or material[0] not in (10002,10003,10004,10005):
        return (0.0,0.0,0.0)
    if not finite(player_position) or not finite((camera_fract[0],camera_fract[2])):
        return (0.0,0.0,0.0)
    if material[0]==10002:
        amplitude=.08
    else:
        amplitude=.20*grass_bend(material[0],mid_block[1])
    if amplitude<=0:
        return (0.0,0.0,0.0)
    x,z=foliage_field(anchored_tile(camera_int,camera_fract,player_position),seconds,speed,fp32_time)
    weight=clamp(strength)*amplitude
    return x*weight,0.0,z*weight


def foliage_clip(baseline,view_vertex,pass_inverse,pass_model_view,projection,material,mid_block,**wind_options):
    if not finite(baseline) or not finite(view_vertex):
        return baseline
    player_h=matrix_vector(pass_inverse,view_vertex)
    if not finite(player_h) or abs(player_h[3])<=1e-6:
        return baseline
    player=tuple(value/player_h[3] for value in player_h[:3])
    displacement=foliage_displacement(player,material,mid_block,**wind_options)
    if displacement==(0,0,0):
        return baseline
    projected=matrix_vector(projection,matrix_vector(pass_model_view,displacement+(0,)))
    if not finite(projected):
        return baseline
    result=tuple(a+b for a,b in zip(baseline,projected))
    return result if finite(result) else baseline


def close(a,b,tolerance=1e-10):
    return all(abs(x-y)<=tolerance for x,y in zip(a,b))

def validate_foliage_math():
    assert abs(MAX_FIELD-math.sqrt(.6*.6+.4*.4))<1e-15
    assert abs(math.hypot(*foliage_field((3/28,1/14)))-MAX_FIELD)<1e-12
    assert math.hypot(.8,.6)==math.hypot(-.6,.8)==1 and abs(dot((.8,.6),(-.6,.8)))<1e-15
    field_cases=0
    for x,z,seconds,speed in product((0,.00001,.13,.5,.99999),(0,.03,.4,.99999),(0,17,71,199.999),(0,1,2)):
        field=foliage_field((x,z),seconds,speed)
        assert finite(field) and math.hypot(*field)<=MAX_FIELD+1e-12
        for shift in ((1,0),(0,1),(-1,0),(0,-1)):
            assert close(field,foliage_field((x+shift[0],z+shift[1]),seconds,speed))
        for period in (200,3600):
            assert close(field,foliage_field((x,z),seconds+period,speed),1e-10)
        if speed==0:
            assert field==foliage_field((x,z),0,0)
        field_cases+=1
    assert foliage_field((.13,.4),0,0)!=(0,0)
    maximum_wrap=0.0
    for tile,speed,period in product(((0,0),(.13,.4),(.99999,.99999)),(0,1,2),(200,3600)):
        before=foliage_field(tile,period-.001,speed,True)
        after=foliage_field(tile,.001,speed,True)
        maximum_wrap=max(maximum_wrap,math.hypot(*(a-b for a,b in zip(before,after))))
    assert maximum_wrap<.005
    for invalid in (-1,math.nan,math.inf,-math.inf):
        assert wind_cycle(invalid)==0
    assert math.isfinite(wind_cycle(3e38,2,True))
    for plant in (10003,10004):
        assert grass_bend(plant,32)==0
        assert grass_bend(plant,31)==0  # Entire quantization dead zone stays rooted.
        values=[grass_bend(plant,32-64*h) for h in (0,.005,1/64,.1,.5,1)]
        assert values==sorted(values) and values[2]==0
    assert grass_bend(10003,-32)==grass_bend(10005,-32)==1
    assert grass_bend(10004,-32)==grass_bend(10005,32)
    assert abs(grass_bend(10004,-32)-((1-1/64)/(2-1/64))**2)<1e-15
    assert 0<grass_bend(10004,-32)<.25
    cases=0
    for x,z,seconds,speed,strength,material_id,mid_y in product((.1,15.5,127.99),(.2,64.1,127.9),
            (0,17,199.999),(0,1,2),(0,.25,.5,1),(10002,10003,10004,10005),(-32,0,31,32)):
        displacement=foliage_displacement((x,64,z),(material_id,0),(0,mid_y,0,0),
                                          seconds=seconds,speed=speed,strength=strength)
        assert finite(displacement) and displacement[1]==0
        amplitude=.08 if material_id==10002 else .20*grass_bend(material_id,mid_y)
        assert math.hypot(displacement[0],displacement[2])<=MAX_FIELD*amplitude*strength+1e-12
        assert displacement==foliage_displacement((x,-1000,z),(material_id,-1),(0,mid_y,0,0),
                                                   seconds=seconds,speed=speed,strength=strength)
        if strength==0 or (material_id in (10003,10004) and mid_y>=31):
            assert displacement==(0,0,0)
        cases+=1
    leaf_default=.08*.5*MAX_FIELD
    grass_default=.20*.5*MAX_FIELD
    assert leaf_default<.028845 and grass_default<.072112
    position=(7.25,64,15.75)
    for material_id,fluid in product((-1,0,10001,10002,10002.5,10003,10004,10005,10006),(0,-1,1,2)):
        d=foliage_displacement(position,(material_id,fluid),(0,-32,0,0),seconds=17)
        if material_id not in (10002,10003,10004,10005) or fluid not in (0,-1):
            assert d==(0,0,0)
    for options in ({'enabled':False},{'mode':0},{'debug':5},{'strength':0}):
        assert foliage_displacement(position,(10002,0),(0,0,0,0),**options)==(0,0,0)
    for invalid in (math.nan,math.inf,-math.inf):
        assert foliage_displacement((invalid,0,0),(10002,0),(0,0,0,0))==(0,0,0)
        assert foliage_displacement(position,(10002,invalid),(0,0,0,0))==(0,0,0)
        assert foliage_displacement(position,(10003,0),(0,invalid,0,0))==(0,0,0)
        assert foliage_displacement(position,(10002,0),(0,invalid,0,0))==foliage_displacement(position,(10002,0),(0,0,0,0))
        assert foliage_displacement(position,(10002,0),(0,0,0,0),camera_fract=(0,0,invalid))==(0,0,0)
    # Fixed world points split integer and fractional parts BEFORE subtraction.
    # This never forms large absolute world-space floats.
    anchor_cases=0
    for target in ((2,64,-3),(-20,80,15),(128,64,-128),(30000000,100,-30000000),
                   (2147483640,0,-2147483640),(-2147483640,0,2147483640)):
        fraction=(.375,.625,.8125)
        expected=None
        for offsets,camera_fraction in product(((-4,0,3),(0,0,0),(5,1,-6)),((.1,.2,.9),(.9,.8,.1))):
            camera=tuple(target[i]+offsets[i] for i in range(3))
            player=tuple(target[i]-camera[i]+fraction[i]-camera_fraction[i] for i in range(3))
            actual=foliage_displacement(player,(10002,0),(0,0,0,0),camera,camera_fraction,seconds=17)
            expected=actual if expected is None else expected
            assert close(expected,actual)
            anchor_cases+=1
    for camera_x in (-.1,.1,127.9,128.1,-128.1,-127.9):
        for split in (math.floor,math.trunc):
            integer=split(camera_x)
            fraction=camera_x-integer
            tile=anchored_tile((integer,0,0),(fraction,0,0),(2.375-integer-fraction,0,3.25))
            assert close(tile,(2.375/128,3.25/128))
            anchor_cases+=1
    for integer in (-2147483648,2147483647,-30000000,30000000,-129,-128,-1,0,127,128):
        original=foliage_displacement((1.25,0,-2.5),(10002,0),(0,0,0,0),(integer,0,integer),(.375,0,.625),17)
        for shift in (-128,0,128):
            shifted=foliage_displacement((1.25+shift,0,-2.5+shift),(10002,0),(0,0,0,0),(integer,0,integer),(.375,0,.625),17)
            assert close(original,shifted)
            anchor_cases+=1
    # Joining edges have both the same physical XZ field and the same full-plant
    # root coordinate, independently of which tall-grass half emits the vertex.
    for seconds,strength,position in product((0,17,199.9),(0,.25,.5,1),((0,1,0),(7.25,65,15.75))):
        lower=foliage_displacement(position,(10004,0),(0,-32,0,0),seconds=seconds,strength=strength)
        upper=foliage_displacement(position,(10005,0),(0,32,0,0),seconds=seconds,strength=strength)
        assert lower==upper
    print('PASS: M18 {} bounded field and {} displacement cases; horizontal-only motion, exact roots and continuous tall-grass joins'.format(field_cases,cases))
    print('PASS: M18 {} fixed-world anchor cases; signed/large/INT boundaries, spatial tiling and 200s/3600s clocks'.format(anchor_cases))
    print('PASS: M18 default leaf/grass tip bounds {:.8f}/{:.8f} blocks; float32 clock-wrap field delta {:.6g}'.format(leaf_default,grass_default,maximum_wrap))


def validate_foliage_transforms():
    # Compare adding a projected direction to independently projecting a fully
    # displaced world point, then recover it from TWO distinct camera/light passes.
    transforms=[]
    for yaw,pitch,scale,translation in product((-1.3,0,.8),(-.7,.4),((1,1,1),(.5,2,3)),((0,0,0),(1.5,-4,7))):
        cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        rotation=((cy,0,sy),(sp*sy,cp,-sp*cy),(-cp*sy,sp,cp*cy))
        matrix=tuple(tuple(rotation[i][j]*scale[j] for j in range(3))+(translation[i],) for i in range(3))+((0,0,0,1),)
        transforms.append(matrix)
    perspective=((1.2,0,0,0),(0,1.7,0,0),(0,0,-1.002,-.2002),(0,0,-1,0))
    orthographic=((.025,0,0,.1),(0,.025,0,-.2),(0,0,-.01,-.3),(0,0,0,1))
    cases=0
    for position,material,mid,seconds in product(((2.25,1.5,-7.75),(-1.25,2.5,-2.75)),
              ((10002,0),(10003,0),(10004,0),(10005,-1)),((0,-32,0,0),(0,32,0,0)),(0,17)):
        delta=foliage_displacement(position,material,mid,seconds=seconds)
        displaced=tuple(a+b for a,b in zip(position,delta))+(1,)
        for model_view in transforms:
            inverse=inverse_matrix(model_view)
            view=matrix_vector(model_view,position+(1,))
            for projection in (perspective,orthographic):
                baseline=matrix_vector(projection,view)
                result=foliage_clip(baseline,view,inverse,model_view,projection,material,mid,seconds=seconds)
                expected=matrix_vector(projection,matrix_vector(model_view,displaced))
                assert close(result,expected,1e-10)
                recovered=matrix_vector(inverse,matrix_vector(inverse_matrix(projection),result))
                assert close(recovered,displaced,1e-10)
                if delta==(0,0,0):
                    assert result is baseline
                cases+=1
    baseline=(.25,-.5,.75,1)
    view=(2,1,-4,1)
    for options in ({'enabled':False},{'mode':0},{'debug':5},{'strength':0}):
        assert foliage_clip(baseline,view,IDENTITY4,IDENTITY4,IDENTITY4,(10002,0),(0,0,0,0),**options) is baseline
    zero=tuple((0,0,0,0) for _ in range(4))
    invalid=((math.nan,0,0,0),)+IDENTITY4[1:]
    assert foliage_clip(baseline,view,zero,IDENTITY4,IDENTITY4,(10002,0),(0,0,0,0)) is baseline
    assert foliage_clip(baseline,view,invalid,IDENTITY4,IDENTITY4,(10002,0),(0,0,0,0)) is baseline
    assert foliage_clip(baseline,view,IDENTITY4,invalid,IDENTITY4,(10002,0),(0,0,0,0)) is baseline
    assert foliage_clip(baseline,view,IDENTITY4,IDENTITY4,invalid,(10002,0),(0,0,0,0)) is baseline
    assert foliage_clip(baseline,view,IDENTITY4,IDENTITY4,zero,(10002,0),(0,0,0,0))==baseline
    # Homogeneous scaling of the inverse point is irrelevant after its divide.
    doubled=tuple(tuple(2*x for x in row) for row in IDENTITY4)
    assert close(foliage_clip(baseline,view,doubled,IDENTITY4,IDENTITY4,(10002,0),(0,0,0,0)),
                 foliage_clip(baseline,view,IDENTITY4,IDENTITY4,IDENTITY4,(10002,0),(0,0,0,0)))
    print('PASS: M18 {} independent point/direction transform cases across terrain/light projections, rotations, translations and nonuniform scales'.format(cases))
    print('PASS: M18 exact baseline bypass, invalid/degenerate homogeneous point and projected-matrix fallbacks')

OLD_ENTITY_DECL = '''#ifdef APPLY_WATER_STYLE
in vec2 mc_Entity;
flat out int waterSurface;
#endif
'''
NEW_ENTITY_DECL = '''#if defined(APPLY_WATER_STYLE) || defined(APPLY_FOLIAGE_WIND)
in vec2 mc_Entity;
#endif
#ifdef APPLY_WATER_STYLE
flat out int waterSurface;
#endif
#ifdef APPLY_FOLIAGE_WIND
#include "/lib/foliage.glsl"
in vec4 at_midBlock;
uniform mat4 gbufferModelView;
uniform mat4 gbufferModelViewInverse;
#endif
'''
TERRAIN_CALL = '''#ifdef APPLY_FOLIAGE_WIND
    // The shadow vertex stage applies this same world-space wind before projection.
    gl_Position = foliageWindClip(gl_Position, gl_ModelViewMatrix * gl_Vertex,
        gbufferModelViewInverse, gbufferModelView, gl_ProjectionMatrix, mc_Entity, at_midBlock);
#endif
'''
SHADOW_DECL = '''#include "/lib/foliage.glsl"
in vec2 mc_Entity;
in vec4 at_midBlock;
uniform mat4 shadowModelView;
uniform mat4 shadowModelViewInverse;

'''
SHADOW_CALL = '''    // Match terrain displacement; caster alpha/UV and shadow-map configuration stay unchanged.
    gl_Position = foliageWindClip(gl_Position, gl_ModelViewMatrix * gl_Vertex,
        shadowModelViewInverse, shadowModelView, gl_ProjectionMatrix, mc_Entity, at_midBlock);
'''
FOLIAGE_BLOCKS = '''
# M18: explicit vanilla foliage only. Water keeps its independent 10001 classification.
# Tall-grass half states share the same root-to-tip bend across their joining edge.
block.10002 = minecraft:acacia_leaves minecraft:azalea_leaves minecraft:birch_leaves minecraft:cherry_leaves minecraft:dark_oak_leaves minecraft:flowering_azalea_leaves minecraft:jungle_leaves minecraft:mangrove_leaves minecraft:oak_leaves minecraft:pale_oak_leaves minecraft:spruce_leaves
block.10003 = minecraft:short_grass
block.10004 = minecraft:tall_grass:half=lower
block.10005 = minecraft:tall_grass:half=upper
'''
FOLIAGE_PROPERTIES = '''
# M18: identical wind for terrain and its shadow casters; no new passes or textures.
screen.FOLIAGE = FOLIAGE_WIND FOLIAGE_WIND_STRENGTH FOLIAGE_WIND_SPEED
screen.FOLIAGE.columns = 2
'''
FOLIAGE_LABELS = {'screen.FOLIAGE','option.FOLIAGE_WIND','value.FOLIAGE_WIND.0','value.FOLIAGE_WIND.1',
                  'option.FOLIAGE_WIND.comment','option.FOLIAGE_WIND_STRENGTH','option.FOLIAGE_WIND_STRENGTH.comment',
                  'option.FOLIAGE_WIND_SPEED','value.FOLIAGE_WIND_SPEED.0','value.FOLIAGE_WIND_SPEED.1',
                  'value.FOLIAGE_WIND_SPEED.2','option.FOLIAGE_WIND_SPEED.comment'}
OLD_PROFILE_COMMENTS = {
    'lang/en_us.lang':'profile.comment=Changes shadows, bloom, aurora and water effects while keeping your color, fog and advanced settings. Light uses hard shadows and turns off bloom, aurora, water waves and depth color.\n',
    'lang/zh_cn.lang':'profile.comment=调整阴影、泛光、极光和水面效果，保留你的调色、雾与高级设置。轻量档使用硬阴影，并关闭泛光、极光、水面波动和水深颜色。\n'}
NEW_PROFILE_COMMENTS = {
    'lang/en_us.lang':'profile.comment=Changes shadows, bloom, aurora, water effects and foliage wind while keeping your color, fog and advanced settings. Light uses hard shadows and turns off bloom, aurora, water waves, depth color and foliage wind.\n',
    'lang/zh_cn.lang':'profile.comment=调整阴影、泛光、极光、水面效果与植被风动，保留你的调色、雾和高级设置。轻量档使用硬阴影，并关闭泛光、极光、水面波动、水深颜色与植被风动。\n'}


def restore_foliage_source(relative,source):
    """Undo only the reviewed terrain/caster hooks, four mappings and foliage UI."""
    relative=relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative=relative[len('shaders/'):]
    source=restore_celestial_glow_source(relative,source)
    if relative=='gbuffers_terrain.vsh':
        flag='#define APPLY_FOLIAGE_WIND\n'
        assert source.count(flag)==1
        source=source.replace(flag,'',1)
    if relative=='lib/geometry/lit_vertex.glsl':
        assert source.count(NEW_ENTITY_DECL)==source.count(TERRAIN_CALL)==1
        source=source.replace(NEW_ENTITY_DECL,OLD_ENTITY_DECL,1).replace(TERRAIN_CALL,'',1)
    if relative=='shadow.vsh':
        assert source.count(SHADOW_DECL)==source.count(SHADOW_CALL)==1
        source=source.replace(SHADOW_DECL,'',1).replace(SHADOW_CALL,'',1)
    if relative=='block.properties':
        assert source.endswith(FOLIAGE_BLOCKS)
        source=source[:-len(FOLIAGE_BLOCKS)]
    if relative=='shaders.properties':
        assert source.endswith(FOLIAGE_PROPERTIES)
        source=source[:-len(FOLIAGE_PROPERTIES)]
        replacements=(
            (' [ADVANCED] [FOLIAGE]\n',' [ADVANCED] <empty>\n'),
            ('sliders = FOLIAGE_WIND_STRENGTH ','sliders = '),
            ('# M18 adds foliage wind to the six M17 quality controls; artistic strengths remain.\n',
             '# M17 quality profiles change only six controls; artistic preferences are retained.\n'),
            ('WATER_DEPTH_TINT=1 FOLIAGE_WIND=1\n','WATER_DEPTH_TINT=1\n'),
            ('WATER_DEPTH_TINT=0 FOLIAGE_WIND=0\n','WATER_DEPTH_TINT=0\n'))
        for current,old in replacements:
            assert source.count(current)==1
            source=source.replace(current,old,1)
    if relative in OLD_PROFILE_COMMENTS:
        marker='\nscreen.FOLIAGE='
        assert source.count(marker)==1
        prefix,tail=source.split(marker,1)
        new_lines=('screen.FOLIAGE='+tail).splitlines()
        assert all('=' in line for line in new_lines)
        keys=[line.split('=',1)[0] for line in new_lines]
        assert len(keys)==len(FOLIAGE_LABELS) and set(keys)==FOLIAGE_LABELS
        assert prefix.count(NEW_PROFILE_COMMENTS[relative])==1
        source=prefix.replace(NEW_PROFILE_COMMENTS[relative],OLD_PROFILE_COMMENTS[relative],1)
    return source


def expand_without_foliage(path,shaders,chain=()):
    """Only M18's exact changes are removed before older vertex-interface checks."""
    path,shaders=Path(path).resolve(),Path(shaders).resolve()
    assert path not in chain and shaders in path.parents
    source=restore_foliage_source(str(path.relative_to(shaders)),path.read_text(encoding='utf-8'))
    return re.sub(r'^#include "([^"]+)"\s*$',lambda match:expand_without_foliage(
        shaders/match[1].lstrip('/'),shaders,chain+(path,)),source,flags=re.M)

def validate_foliage(root,expand,preprocess,compact,function_body):
    from validate_settings_profiles import (option_definitions,parse_properties,load_profiles,menu_options,
                                            parse_language,matching_profiles,PROFILE_KEYS)
    shaders=Path(root)/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    def body(source,name):
        return compact(function_body(source,name))
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',M17_BASELINE,'shaders']).decode().splitlines()
    for path in old_files:
        relative=path[len('shaders/'):]
        previous=subprocess.check_output(['git','-C',str(root),'show',M17_BASELINE+':'+path]).decode('utf-8').replace('\r\n','\n')
        assert restore_foliage_source(relative,read(relative))==previous,relative
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files-set(old_files)=={'shaders/lib/foliage.glsl','shaders/lib/foliage_settings.glsl','shaders/lib/celestial_glow.glsl','shaders/lib/celestial_glow_settings.glsl','shaders/lib/water_scene_snapshot.glsl','shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'} | DEBUG_FILES
    assert len(list(shaders.glob('*.vsh')))==len(list(shaders.glob('*.fsh')))==24
    helper=read('lib/foliage.glsl')
    code=compact(helper)
    # Integration boundaries, not a line-by-line duplicate of implementation:
    # one shared field, homogeneous point recovery, projected direction and exact
    # baseline addition. Native GPU fixtures bind the independent math to execution.
    assert 'playerH.xyz/playerH.w' in code
    assert 'projection*(passModelView*vec4(delta,0.0))' in code
    assert 'vec4displaced=baseline+projectedDelta;' in code
    assert 'if(all(equal(delta,vec3(0.0))))returnbaseline;' in code
    for forbidden in ('texture(','texelFetch(','sampler','gl_FragDepth','gl_Normal','upPosition',
                      'celestialEnvironmentWeight','isEyeInWater','hasSkylight','hasCeiling','rainStrength',
                      'fogColor','eyeBrightness','gl_Vertex'):
        assert forbidden not in code,forbidden
    assert 'uvec2(cameraPositionInt.xz)&uvec2(127u)' in code and '%' not in code
    assert 'shadowModelView' not in code and 'gbufferModelView' not in code
    for path in shaders.glob('*.vsh'):
        selected=preprocess(expand(path),0,False)
        active=path.stem in ('gbuffers_terrain','shadow')
        assert ('foliageWindClip(' in selected)==active,path.name
        main=body(selected,'main')
        if active:
            assert main.count('foliageWindClip(')==1
            assert main.index('ftransform()')<main.index('foliageWindClip(')
            assert selected.count('in vec2 mc_Entity;')==selected.count('in vec4 at_midBlock;')==1
            expected='shadowModelViewInverse,shadowModelView' if path.stem=='shadow' else 'gbufferModelViewInverse,gbufferModelView'
            assert expected+',gl_ProjectionMatrix,mc_Entity,at_midBlock)' in main
            if path.stem=='gbuffers_terrain':
                assert 'normalView=gl_NormalMatrix*gl_Normal;' in main
                assert main.count('lmcoord=')==main.count('texcoord=')==main.count('glcolor=')==1
        uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms)==len(set(uniforms)),path.name
    for path in shaders.glob('*.fsh'):
        assert 'foliageWindClip(' not in preprocess(expand(path),0,False),path.name
    for program,mode,enabled,debug in product(('gbuffers_terrain','shadow'),(0,1),(0,1),range(7)):
        selected=preprocess(expand(shaders/(program+'.vsh')),debug,False,
                            overrides={'SCENE_COLOR_MODE':mode,'FOLIAGE_WIND':enabled})
        if not mode or not enabled or debug:
            assert body(selected,'foliageDisplacement')=='returnvec3(0.0);'
            assert body(selected,'foliageWindClip')=='returnbaseline;'
    mappings=parse_properties(read('block.properties'))
    assert set(mappings)=={'block.10001','block.10002','block.10003','block.10004','block.10005'}
    assert mappings['block.10001']=='minecraft:water'
    leaves=mappings['block.10002'].split()
    assert len(leaves)==len(set(leaves))==11 and all(name.startswith('minecraft:') and name.endswith('_leaves') for name in leaves)
    assert mappings['block.10003']=='minecraft:short_grass'
    assert mappings['block.10004']=='minecraft:tall_grass:half=lower'
    assert mappings['block.10005']=='minecraft:tall_grass:half=upper'
    options={key:value for key,value in option_definitions(root).items() if key not in (GLOW_OPTIONS | FILTER_OPTIONS | REFLECTION_OPTIONS)}
    properties=parse_properties(restore_celestial_glow_source('shaders.properties',read('shaders.properties')))
    controls,screens=menu_options(properties,options)
    assert len(options)==len(controls)==54 and len(screens)==12
    for name,default,values in (('FOLIAGE_WIND','1',('0','1')),
                                ('FOLIAGE_WIND_STRENGTH','0.5',('0.0','0.25','0.5','1.0')),
                                ('FOLIAGE_WIND_SPEED','1',('0','1','2'))):
        assert options[name]==dict(kind='number',default=default,values=values)
    profiles=load_profiles(root)
    assert all(set(profile)==PROFILE_KEYS|{'FOLIAGE_WIND'} for profile in profiles.values())
    assert profiles['BALANCED']['FOLIAGE_WIND']==profiles['SOFT_SHADOWS']['FOLIAGE_WIND']=='1'
    assert profiles['LIGHT']['FOLIAGE_WIND']=='0'
    defaults={key:option['default'] for key,option in options.items()}
    uncontrolled=set(options)-set(profiles['BALANCED'])
    assert len(uncontrolled)==47
    for name,profile in profiles.items():
        current=dict(defaults,**profile)
        assert matching_profiles(profiles,current)==(name,)
        current['FOLIAGE_WIND_STRENGTH']='1.0'
        current['FOLIAGE_WIND_SPEED']='2'
        assert matching_profiles(profiles,current)==(name,)
    assert matching_profiles(profiles,dict(defaults,FOLIAGE_WIND='0'))==()
    en,zh=(parse_language(restore_celestial_glow_source('lang/'+language,read('lang/'+language))) for language in ('en_us.lang','zh_cn.lang'))
    assert len(en)==len(zh)==171 and set(en)==set(zh)
    assert FOLIAGE_LABELS<=set(en)
    assert all(re.search(r'[\u3400-\u9fff]',zh[key]) for key in FOLIAGE_LABELS)
    print('PASS: M18 {} prior shader/property/language files pinned; only terrain/caster position, classified mappings and foliage settings changed'.format(len(old_files)))
    print('PASS: M18 shared vertex-only field, original normals/UV/lightmap/alpha and existing 24 program pairs retained')
    print('PASS: M18 54 controls once, seven-control profiles retain 47 other settings, and 171 matching English/Chinese keys')
    validate_foliage_math()
    validate_foliage_transforms()
    print('LIMIT: analytical/CPU/source checks; no Minecraft vegetation/caster appearance or measured performance claim')