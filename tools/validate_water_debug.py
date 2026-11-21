"""M0 live water diagnostics: independent geometry, source pins and UI contracts."""
import math
import hashlib
import re
import subprocess
from functools import lru_cache
from itertools import product
from pathlib import Path

W3_BASELINE = 'df94fe404146c1364920f709569898359c84c8ed'
DEBUG_LABELS = {'value.DEBUG_VIEW.7', 'value.DEBUG_VIEW.8', 'value.DEBUG_VIEW.9'}
DEBUG_FILES = {'shaders/lib/water_params.glsl', 'shaders/lib/water_debug_capture.glsl',
               'shaders/lib/water_debug_view.glsl'}
IDENTITY4 = ((1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1))
DEPTH_TOLERANCE = 1 / 16777215
BLACK = (0.0, 0.0, 0.0)
MAGENTA = (1.0, 0.0, 1.0)


def finite(values):
    return all(math.isfinite(value) for value in values)


def matrix_vector(matrix, vector):
    return tuple(sum(a*b for a,b in zip(row,vector)) for row in matrix)


def unit(vector):
    if not finite(vector):
        return None
    scale = max(map(abs,vector))
    if scale <= 1e-6:
        return None
    scaled = tuple(value/scale for value in vector)
    length = math.sqrt(sum(value*value for value in scaled))
    return tuple(value/length for value in scaled)


def unproject(uv, depth, inverse_projection):
    homogeneous = matrix_vector(inverse_projection, (2*uv[0]-1, 2*uv[1]-1, 2*depth-1, 1))
    if not finite(homogeneous) or homogeneous[3] == 0:
        return None
    position = tuple(value/homogeneous[3] for value in homogeneous[:3])
    return position if finite(position) else None


def water_debug_color(surface, final_depth, background_depth, uv,
                      inverse_projection, model_view_inverse=IDENTITY4, debug=7,
                      world_block_meters=1.0, gap_range_meters=16.0):
    """Reference of raw display data; no tone mapping or water-volume assumption."""
    if not finite(tuple(surface)+(final_depth,)) or len(surface) != 4:
        return BLACK
    squared = sum(value*value for value in surface[:3])
    if abs(squared-1) > .001 or not 0 <= surface[3] < 1 or not 0 <= final_depth < 1:
        return BLACK
    if abs(surface[3]-final_depth) > DEPTH_TOLERANCE:
        return BLACK
    if debug == 7:
        return (1.0, 1.0, 1.0)
    if debug == 8:
        return tuple(value*.5+.5 for value in surface[:3])
    if debug != 9:
        raise ValueError('Expected water debug view 7, 8 or 9')
    if not math.isfinite(background_depth) or not surface[3] < background_depth < 1:
        return MAGENTA
    if not finite(uv) or any(value < 0 or value >= 1 for value in uv) or not finite((world_block_meters,gap_range_meters)):
        return MAGENTA
    foreground = unproject(uv, surface[3], inverse_projection)
    background = unproject(uv, background_depth, inverse_projection)
    if foreground is None or background is None:
        return MAGENTA
    delta = tuple(b-a for a,b in zip(foreground,background))
    world_gap = matrix_vector(tuple(row[:3] for row in model_view_inverse[:3]),delta)
    if not finite(world_gap):
        return MAGENTA
    scale = max(map(abs,world_gap))
    if scale <= 0:
        return MAGENTA
    distance = scale * math.sqrt(sum((value/scale)**2 for value in world_gap)) * world_block_meters
    if not math.isfinite(distance) or distance <= 0 or gap_range_meters <= 0:
        return MAGENTA
    value = min(1.0,max(0.0,distance/gap_range_meters))
    return (value,value,value)


@lru_cache(maxsize=1)
def debug_fixtures():
    """Analytic camera rays; known world distances do not use depth reconstruction."""
    from validate_water_screen_reflection import perspective, inverse, project
    cases = []
    for fov,aspect,u,v,distance,gap,yaw,pitch in product(
            (45,95),(.75,16/9),(.15,.5,.85),(.2,.8),(2,32),(.125,4,16,32),(0,.7),(0,.4)):
        projection = perspective(fov,aspect)
        inverse_projection = inverse(projection)
        focal = 1/math.tan(math.radians(fov)/2)
        direction = unit(((2*u-1)*aspect/focal,(2*v-1)/focal,-1))
        foreground = tuple(value*distance for value in direction)
        background = tuple(value*(distance+gap) for value in direction)
        uv,front_depth = project(foreground,projection)
        back_uv,back_depth = project(background,projection)
        assert max(abs(a-b) for a,b in zip(uv,back_uv)) < 1e-14
        cy,sy,cp,sp = math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        # R_yaw * R_pitch; nonzero translation must cancel in a direction gap.
        camera = ((cy,sy*sp,sy*cp,1234),(0,cp,-sp,-987),(-sy,cy*sp,cy*cp,17),(0,0,0,1))
        view_normal = (camera[1][0],camera[1][1],camera[1][2])
        surface = view_normal+(front_depth,)
        cases.append(dict(surface=surface,final_depth=front_depth,background_depth=back_depth,
                          uv=uv,inverse_projection=inverse_projection,model_view_inverse=camera,
                          distance=gap,expected_gray=min(gap/16,1),view_normal=view_normal))
    return cases


def debug_pixel(uv, extent, final_depth_extent):
    """Select metadata by normalized final UV, independent of output viewport size."""
    if extent != final_depth_extent or len(extent) != 2 or any(value <= 0 for value in extent):
        return None
    if not finite(uv) or any(value < 0 or value >= 1 for value in uv):
        return None
    return tuple(min(math.floor(value*size),size-1) for value,size in zip(uv,extent))


def validate_debug_math():
    mappings = 0
    for source_size,output_size in product(((1,1),(17,9),(96,64),(1920,1080)),((1,1),(31,19),(1920,1080))):
        for output_pixel in ((0,0),(output_size[0]//2,output_size[1]//2),(output_size[0]-1,output_size[1]-1)):
            uv = tuple((value+.5)/size for value,size in zip(output_pixel,output_size))
            expected = tuple(math.floor((2*value+1)*size/(2*output)) for value,size,output in zip(output_pixel,source_size,output_size))
            assert debug_pixel(uv,source_size,source_size)==expected
            mappings += 1
    for uv in ((-.01,.5),(1,.5),(.5,1),(math.nan,.5),(.5,math.inf)):
        assert debug_pixel(uv,(96,64),(96,64)) is None
    assert debug_pixel((.5,.5),(96,64),(95,64)) is None
    assert debug_pixel((.5,.5),(0,64),(0,64)) is None
    print('PASS: M0 {} normalized-UV mappings across different final/source extents; invalid UV/dimension guards'.format(mappings))
    maximum_error = 0.0
    for case in debug_fixtures():
        args = {key:case[key] for key in ('surface','final_depth','background_depth','uv',
                                        'inverse_projection','model_view_inverse')}
        assert water_debug_color(**args,debug=7) == (1,1,1)
        expected_normal = tuple(value*.5+.5 for value in case['view_normal'])
        assert water_debug_color(**args,debug=8) == expected_normal
        actual = water_debug_color(**args,debug=9)
        error = max(abs(value-case['expected_gray']) for value in actual)
        maximum_error = max(maximum_error,error)
        assert error < 1e-10,(case,actual)
    case = debug_fixtures()[0]
    args = {key:case[key] for key in ('surface','final_depth','background_depth','uv',
                                    'inverse_projection','model_view_inverse')}
    for debug in (7,8,9):
        assert water_debug_color(**dict(args,surface=(0,0,0,0)),debug=debug) == BLACK
        for invalid in (math.nan,math.inf,-math.inf):
            for channel in range(4):
                bad = list(case['surface']);bad[channel] = invalid
                assert water_debug_color(**dict(args,surface=bad),debug=debug) == BLACK
            assert water_debug_color(**dict(args,final_depth=invalid),debug=debug) == BLACK
        for normal in ((0,0,0),(2,0,0),(1.01,0,0)):
            assert water_debug_color(**dict(args,surface=normal+(case['surface'][3],)),debug=debug) == BLACK
        for depth in (-.01,1,1.01):
            assert water_debug_color(**dict(args,surface=case['surface'][:3]+(depth,)),debug=debug) == BLACK
            assert water_debug_color(**dict(args,final_depth=depth),debug=debug) == BLACK
        for direction in (-1,1):
            nearly = dict(args,final_depth=case['surface'][3]+direction*DEPTH_TOLERANCE*.5)
            assert water_debug_color(**nearly,debug=debug) != BLACK
            blocked = dict(args,final_depth=case['surface'][3]+direction*DEPTH_TOLERANCE*2)
            assert water_debug_color(**blocked,debug=debug) == BLACK
    for invalid in (-.1,0,case['surface'][3],1,1.1,math.nan,math.inf,-math.inf):
        assert water_debug_color(**dict(args,background_depth=invalid),debug=9) == MAGENTA
    zero_matrix = ((0,0,0,0),)*4
    assert water_debug_color(**dict(args,inverse_projection=zero_matrix),debug=9) == MAGENTA
    assert water_debug_color(**dict(args,model_view_inverse=zero_matrix),debug=9) == MAGENTA
    invalid_matrix = ((math.nan,0,0,0),)+IDENTITY4[1:]
    assert water_debug_color(**dict(args,model_view_inverse=invalid_matrix),debug=9) == MAGENTA
    for meters,span in ((2,16),(1,8),(.5,32)):
        result = water_debug_color(**args,debug=9,world_block_meters=meters,gap_range_meters=span)
        assert max(abs(value-min(case['distance']*meters/span,1)) for value in result)<1e-11
    print('PASS: M0 {} analytic world-ray gap cases across FOV/aspect/camera rotations; max grayscale error {:.6g}'.format(len(debug_fixtures()),maximum_error))
    print('PASS: M0 mask/normal colors, unit metadata, raw/front depth tolerance, occlusion and black/magenta fallbacks')


# Reviewed M0-only edits: exact normalized-text hashes, not permissive transforms.
# Historical validators read the pinned W3 file only after this current-text check.
# Independent stage comparisons below always expand the real current shaders.
M0_SOURCE_PINS = {'final.fsh': '395f4a0d775c78afb653dfc3c165f628e911ba3ec9059a3281cea940458563a7',
 'lib/geometry/lit_fragment.glsl': '62d5807f50085dceaac4461e6ff5d7ca25099112a63d4b3b3a79b9ae91f42644',
 'lib/lighting_settings.glsl': '38f6a05a32d331d32f2b26e7dd80e984dbdd675e1fd7755cee68dbd1096c63d2',
 'lib/water.glsl': '687266e9baca68f3fb463f568928896136e2acf9cdfb7329ebdd3821587cb99a',
 'shaders.properties': 'e2a49558794909acb130986f1512f37becc2e663dcfc0dd18da863d24238323a',
 'lang/en_us.lang': '166cd40ceb27291a274baf6c1962ed736103f58dadf6acb0f4b96646b01ca683',
 'lang/zh_cn.lang': '255ff0c1bdbd8970d1675e6442f3f740b1a534c8c501a9a3af3980ec3053796f'}


@lru_cache(maxsize=None)
def w3_source(relative):
    root = Path(__file__).resolve().parents[1]
    return subprocess.check_output(['git','-C',str(root),'show',W3_BASELINE+':shaders/'+relative]).decode('utf-8').replace('\r\n','\n')


def restore_water_debug_source(relative, source):
    """Accept only an approved M0 edit or its exact W3 predecessor, then restore."""
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    if relative not in M0_SOURCE_PINS:
        return source
    source = source.replace('\r\n','\n')
    previous = w3_source(relative)
    if source == previous:
        return source
    actual = hashlib.sha256(source.encode('utf-8')).hexdigest()
    assert actual == M0_SOURCE_PINS[relative], 'Unreviewed M0 source change: '+relative
    return previous


def capture_surface(view_position, normal_view, world_dx=(0,0), world_dy=(0,0),
                    water_surface=1, window_depth=.5, up_position=(0,1,0),
                    model_view_inverse=IDENTITY4, camera_int=(0,0,0), camera_fract=(0,0,0),
                    seconds=0, waves=1, detail=1, strength=.6, speed=1):
    """Capture protocol oracle, reusing independently tested M14/W2 wave math."""
    from validate_water_waves import wave_gradient, wave_normal_from_gradient, anchored_tile
    from validate_water_filtered_waves import filtered_gradient
    if water_surface != 1 or not math.isfinite(window_depth) or not 0 <= window_depth < 1:
        return (0,0,0,0)
    if not finite(tuple(view_position)+tuple(normal_view)+tuple(up_position)):
        return (0,0,0,0)
    normal,up = unit(normal_view),unit(up_position)
    if normal is None or up is None:
        return (0,0,0,0)
    facing = sum(a*b for a,b in zip(normal,up))
    weight = min(1,max(0,(facing-.5)/.45))
    eligibility = weight*weight*(3-2*weight)
    player = matrix_vector(model_view_inverse,tuple(view_position)+(1,))[:3]
    if waves and strength > 0 and eligibility > 0 and finite(player) and finite((camera_fract[0],camera_fract[2])):
        tile = anchored_tile(camera_int,camera_fract,player)
        gradient = (filtered_gradient(tile,seconds,speed,world_dx,world_dy) if detail
                    else wave_gradient(tile,seconds,speed))
        normal_matrix = tuple(tuple(model_view_inverse[column][row] for column in range(3)) for row in range(3))
        normal = wave_normal_from_gradient(normal,gradient,normal_matrix,strength,eligibility)
    return tuple(normal)+(window_depth,)


def validate_capture_math():
    from validate_water_waves import wave_gradient, wave_normal_from_gradient, anchored_tile
    from validate_water_filtered_waves import filtered_gradient
    count = 0
    for normal,depth,detail,waves,strength,time in product(
            ((0,1,0),(1,0,0),(0,-1,0)),(0,.5,.999), (0,1),(0,1),(0,.6,1),(0,17)):
        view=(3,-2,-8)
        actual=capture_surface(view,normal,window_depth=depth,detail=detail,waves=waves,strength=strength,seconds=time)
        assert actual[3]==depth and abs(sum(x*x for x in actual[:3])-1)<1e-12
        if normal != (0,1,0) or not waves or strength==0:
            assert actual[:3]==normal
        else:
            tile=anchored_tile((0,0,0),(0,0,0),view)
            gradient=filtered_gradient(tile,time) if detail else wave_gradient(tile,time)
            expected=wave_normal_from_gradient(normal,gradient,strength=strength)
            assert actual[:3]==expected
        count+=1
    for material in (-1,0,2,10001):
        assert capture_surface((0,0,-1),(0,1,0),water_surface=material)==(0,0,0,0)
    for invalid in (math.nan,math.inf,-math.inf):
        for key in ('view_position','normal_view','up_position'):
            args=dict(view_position=(0,0,-1),normal_view=(0,1,0))
            args[key]=(invalid,1,0)
            assert capture_surface(**args)==(0,0,0,0)
        assert capture_surface((0,0,-1),(0,1,0),window_depth=invalid)==(0,0,0,0)
        assert capture_surface((0,0,-1),(0,1,0),world_dx=(invalid,0))[:3]==(0,1,0)
    for value in (-.1,1,1.1):
        assert capture_surface((0,0,-1),(0,1,0),window_depth=value)==(0,0,0,0)
    for key in ('normal_view','up_position'):
        args=dict(view_position=(0,0,-1),normal_view=(0,1,0));args[key]=(0,0,0)
        assert capture_surface(**args)==(0,0,0,0)
    print('PASS: M0 {} capture/face/wave cases, material exclusion, raw-depth preservation and invalid-input clears'.format(count))


def validate_water_debug(root,expand,preprocess,compact,function_body):
    from validate_settings_profiles import (option_definitions,parse_properties,parse_language,
                                           menu_options,load_profiles,matching_profiles,PROFILE_KEYS)
    from validate_water import stage_variables
    from validate_bloom import BLOOM_TARGETS
    root=Path(root);shaders=root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    def body(source,name):
        return compact(function_body(source,name))
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',W3_BASELINE+':shaders/'+relative]).decode('utf-8').replace('\r\n','\n')
    @lru_cache(maxsize=None)
    def prior_expanded(relative):
        return re.sub(r'^#include "([^"]+)"\s*$',lambda match:prior_expanded(match[1].lstrip('/')),prior(relative),flags=re.M)
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',W3_BASELINE,'shaders']).decode().splitlines()
    assert len(old_files)==104
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files==set(old_files)|DEBUG_FILES
    for path in old_files:
        relative=path[len('shaders/'):]
        assert restore_water_debug_source(relative,read(relative))==prior(relative),relative
    params=read('lib/water_params.glsl')
    assert re.findall(r'float (\w+);',params)==['reflectionF0','worldBlockMeters','debugGapRangeMeters']
    assert body(params,'waterParams')=='returnWaterParams(0.02,1.0,16.0);'
    constructor='WaterParamswaterParams(){returnWaterParams(0.02,1.0,16.0);}'
    structure='structWaterParams{floatreflectionF0;floatworldBlockMeters;floatdebugGapRangeMeters;};'
    new_fresnel='WaterParamsparams=waterParams();returnparams.reflectionF0+(1.0-params.reflectionF0)*squared*squared*grazing;'
    old_fresnel='return0.02+0.98*squared*squared*grazing;'
    def normalize_params(source):
        selected=compact(source)
        if structure in selected:
            assert selected.count(structure)==selected.count(constructor)==1
            selected=selected.replace(structure,'',1).replace(constructor,'',1)
        if new_fresnel in selected:
            assert selected.count(new_fresnel)==1
            selected=selected.replace(new_fresnel,old_fresnel,1)
        return selected
    # Every complete current stage is compared, not just selected functions.
    preserved=0
    for path in sorted(shaders.glob('*.*sh')):
        for mode,debug in product((0,1),range(7)):
            options={'SCENE_COLOR_MODE':mode}
            actual=preprocess(expand(path),debug,False,overrides=options)
            before=preprocess(prior_expanded(path.name),debug,False,overrides=options)
            assert normalize_params(actual)==compact(before),(path.name,mode,debug)
            assert 'colortex7' not in actual and 'captureWaterDebugSurface(' not in actual
            preserved+=1
    capture=read('lib/water_debug_capture.glsl');capture_code=compact(capture)
    for token in ('colortex7Clear=true','colortex7ClearColor=vec4(0.0)',
                  'waterSurface!=1','windowDepth<0.0||windowDepth>=1.0',
                  'waterFilteredWaveNormal(normal,viewPosition,upwardSurface,worldDx,worldDy)',
                  'returnvec4(normal,windowDepth);'):
        assert token in capture_code,token
    assert 'const int colortex7Format = RGBA32F;' in capture
    assert not re.search(r'const int colortex7Format',re.sub(r'/\*.*?\*/','',capture,flags=re.S))
    assert 'uniform sampler' not in capture
    view=read('lib/water_debug_view.glsl');view_code=compact(view)
    for token in ('ownershipTolerance=1.0/16777215.0','abs(surface.a-finalDepth)>ownershipTolerance',
                  'abs(normalLengthSquared-1.0)>0.001','returnsurface.rgb*0.5+0.5;',
                  'mat3(gbufferModelViewInverse)*(backgroundView-waterView)',
                  'scale*length(worldDelta/scale)*params.worldBlockMeters',
                  'clamp(gapMeters/params.debugGapRangeMeters,0.0,1.0)'):
        assert token in view_code,token
    assert 'uniform sampler' not in view
    for source in (capture,view,params):
        for forbidden in ('imageStore','gl_FragDepth','gl_Position','textureLod'):
            assert forbidden not in source
    water_raw=read('lib/geometry/lit_fragment.glsl')
    assert water_raw.index('discard;')<water_raw.index('waterDebugSurface = captureWaterDebugSurface(')<water_raw.index('color.rgb = applyLateAtmosphericFog(')
    capture_call='waterDebugSurface=captureWaterDebugSurface(fogView,normalView,waterWorldDx,waterWorldDy,waterSurface,gl_FragCoord.z);'
    checked=0
    for debug,mode in product((7,8,9),(0,1)):
        for vertex in sorted(shaders.glob('*.vsh')):
            options={'SCENE_COLOR_MODE':mode}
            vs=preprocess(expand(vertex),debug,False,overrides=options)
            fs=preprocess(expand(vertex.with_suffix('.fsh')),debug,False,overrides=options)
            for source in (vs,fs):
                assert source.startswith('#version 330 compatibility') and source.count('void main()')==1
            for name,signature in stage_variables(fs,'in').items():
                assert stage_variables(vs,'out').get(name)==signature,(vertex.name,name)
            locations=list(map(int,re.findall(r'layout\(location = (\d+)\) out (?:vec4|float)\b',fs)))
            targets=re.findall(r'/\* RENDERTARGETS: ([0-9,]+) \*/',fs)
            expected=([0,1] if vertex.stem=='gbuffers_water' else [] if vertex.stem=='shadow' else
                      [0,1,2] if vertex.stem in ('deferred','gbuffers_terrain','gbuffers_block','gbuffers_entities') else [0])
            assert locations==expected,(vertex.name,debug,locations)
            if vertex.stem in ('final','shadow'):
                assert not targets
            else:
                expected_targets=([0,7] if vertex.stem=='gbuffers_water' else [0,5,6] if vertex.stem=='deferred' else
                                  [BLOOM_TARGETS[vertex.stem]] if vertex.stem in BLOOM_TARGETS else expected)
                assert targets==[','.join(map(str,expected_targets))],(vertex.name,targets)
            assert ('captureWaterDebugSurface(' in fs)==(vertex.stem=='gbuffers_water')
            assert ('uniform sampler2D colortex7;' in fs)==(vertex.stem=='final')
            uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',fs,re.M)
            assert len(uniforms)==len(set(uniforms)),vertex.name
            if vertex.stem=='gbuffers_water':
                assert body(fs,'main').count(capture_call)==1
                previous=preprocess(prior_expanded('gbuffers_water.fsh'),debug,False,overrides=options)
                assert body(fs,'main').replace(capture_call,'',1)==body(previous,'main')
            if vertex.stem=='final':
                main=body(fs,'main')
                assert 'color=vec4(debugColor,1.0);' in main
                assert 'textureSize(colortex7,0)' in main and 'textureSize(depthtex0,0)' in main
                assert 'min(ivec2(texcoord*vec2(debugSize)),debugSize-ivec2(1))' in main
                assert 'gl_FragCoord' not in main and '(vec2(pixel)+0.5)/vec2(debugSize)' in main
                assert ('texelFetch(depthtex2,pixel,0)' in main)==(debug==9)
                assert not any(name in main for name in ('gradeColor','toneMapScene','linearToSrgb','EXPOSURE'))
            if vertex.stem in BLOOM_TARGETS:
                assert body(fs,'bloomActive')=='returnfalse;'
            checked+=1
    props=read('shaders.properties')
    for debug in range(10):
        active=preprocess('#define DEBUG_VIEW 0\n'+props,debug,False)
        assert ('blend.gbuffers_water.colortex7 = off' in active)==(debug in (7,8,9))
    assert not re.search(r'^(?:size\.buffer\.colortex7|flip\.\w+\.colortex7)\s*=',props,re.M)
    options=option_definitions(root);properties=parse_properties(props)
    controls,screens=menu_options(properties,options)
    assert len(options)==len(controls)==60 and len(screens)==12
    assert options['DEBUG_VIEW']==dict(kind='number',default='0',values=tuple(map(str,range(10))))
    profiles=load_profiles(root);controlled=PROFILE_KEYS|{'FOLIAGE_WIND'}
    assert all(set(profile)==controlled for profile in profiles.values())
    defaults={key:value['default'] for key,value in options.items()}
    for name,profile in profiles.items():
        for debug in ('7','8','9'):
            assert matching_profiles(profiles,dict(defaults,**profile,DEBUG_VIEW=debug))==(name,)
    en,zh=(parse_language(read('lang/'+language)) for language in ('en_us.lang','zh_cn.lang'))
    assert len(en)==len(zh)==194 and set(en)==set(zh) and DEBUG_LABELS<=set(en)
    assert all(re.search(r'[\u3400-\u9fff]',zh[key]) for key in DEBUG_LABELS)
    validate_capture_math()
    validate_debug_math()
    print('PASS: M0 all 104 W3 files pinned after exact seven-file restoration; three live helper files')
    print('PASS: M0 {} full stages preserve debug0-6 after only exact F0 extraction normalization'.format(preserved))
    print('PASS: M0 {} live-debug program pairs; fullres RGBA32F 0/7 output, alpha discard, clear and blend contracts'.format(checked))
    print('PASS: M0 60 controls/12 screens, 10 debug choices, unchanged profiles and 194 bilingual keys')
    print('LIMIT: source/CPU checks; one front-depth ownership heuristic and a background ray gap, not physical water volume or Iris runtime proof')
