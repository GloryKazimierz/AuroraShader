"""M11 procedural-aurora source/numerical contracts; not Minecraft/GPU rendering."""
import math
import re
import struct
import subprocess
from functools import lru_cache
from itertools import product

M10_BASELINE = '9e9bbc06d7f115783a9fa0f52c940325dc7e3f38'
AURORA_CALL = '''        // Only the upper background receives ribbons: never stars, void or sunset draws.
        // Keep the shared sky palette unchanged so terrain fog cannot contain aurora.
        if (renderStage == MC_RENDER_STAGE_SKY) {
            color.rgb = applyNightAurora(pos, color.rgb);
        }
'''
AURORA_PROPERTIES = '''
# M11 sky-only procedural aurora; original sky objects and fog palette stay separate.
screen.AURORA = AURORA_ENABLED AURORA_INTENSITY AURORA_SPEED
screen.AURORA.columns = 2
'''


def restore_aurora_plumbing(source):
    assert source.count(AURORA_CALL) <= 1
    return source.replace(AURORA_CALL,'',1)


def restore_aurora_source(relative, source):
    """Remove exactly the intended M11 additions before older full-source pins."""
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    if relative == 'lib/geometry/sky_fragment.glsl':
        assert source.count('#include "/lib/aurora.glsl"\n') == 1
        assert source.count(AURORA_CALL) == 1
        source = restore_aurora_plumbing(source.replace('#include "/lib/aurora.glsl"\n','',1))
    if relative == 'shaders.properties':
        assert source.endswith(AURORA_PROPERTIES)
        assert source.count('screen = [AURORA] ') == 1 and source.count('sliders = AURORA_INTENSITY ') == 1
        source = source[:-len(AURORA_PROPERTIES)].replace('screen = [AURORA] ','screen = ',1).replace(
            'sliders = AURORA_INTENSITY ','sliders = ',1)
    return source


def clamp(x, low=0.0, high=1.0):
    return min(high,max(low,x))


def smooth(a,b,x):
    t = clamp((x-a)/(b-a))
    return t*t*(3-2*t)


def unit(vector):
    if not all(math.isfinite(x) for x in vector):
        return None
    scale = max(map(abs,vector))
    if scale <= 1e-6:
        return None
    scaled = tuple(x/scale for x in vector)
    length = math.sqrt(sum(x*x for x in scaled))
    return tuple(x/length for x in scaled)


def f32(value):
    return struct.unpack('f',struct.pack('f',value))[0]


def temporal_phase(seconds,speed=1,fp32=False):
    seconds = max(seconds,0.0) if math.isfinite(seconds) else 0.0
    if fp32:
        cycles = f32(f32(seconds)*f32(speed/200.0))
        return f32(f32(6.28318530718)*f32(cycles-math.floor(cycles)))
    cycles = seconds*(speed/200.0)
    return 6.28318530718*(cycles-math.floor(cycles))


def aurora_ribbons(world_direction,seconds,speed=1,fp32=False):
    """CPU reference: normalized finite world ray -> pre-fade linear RGB."""
    x,y,z = world_direction
    u,v = x/(max(y,0)+.18),z/(max(y,0)+.18)
    phase = temporal_phase(seconds,speed,fp32)
    light = [0.0,0.0,0.0]
    for ribbon in range(3):
        center = -.8-.55*ribbon+.18*math.sin(1.6*u+phase+2*ribbon)+.09*math.sin(3.1*u-2*phase+ribbon)
        distance = v-center
        core = math.exp(-(distance/.10)**2)
        tail = math.exp(-((distance-.22)/.30)**2)
        fold = .5+.5*math.sin(11*u+math.sin(2.3*u-2*phase)+3*phase+2*ribbon)
        striation = .35+.65*fold*fold
        for c,teal,violet in zip(range(3),(.08,1.35,.75),(.25,.05,.55)):
            light[c] += striation*(teal*core+violet*.45*tail)
    return tuple(clamp(c,0,2) for c in light)


def aurora_result(world_direction,scene=(.01,.02,.04),seconds=0,speed=1,intensity=.6,
                  sky_blend=1,elevation=-.5,rain=0,environment=1,
                  enabled=True,mode=1,style=1,debug=0,stage='sky'):
    if not enabled or not mode or not style or debug or stage != 'sky':
        return scene
    night = 1-smooth(-.20,-.05,clamp(elevation,-1,1))
    weight = clamp(intensity)*clamp(sky_blend)*environment*night*(1-clamp(rain))**2
    if not math.isfinite(weight) or weight <= 0:
        return scene
    direction = unit(world_direction)
    if direction is None:
        return scene
    height = direction[1]
    weight *= smooth(.04,.18,height)*(1-smooth(.82,.98,height))*smooth(0,.45,-direction[2])
    if weight <= 0:
        return scene
    return tuple(c+r*weight for c,r in zip(scene,aurora_ribbons(direction,seconds,speed)))


def close(a,b,tolerance=1e-10):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def validate_aurora(root,expand,preprocess,compact,function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M10_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files = subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',
                                        M10_BASELINE,'shaders']).decode().splitlines()
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh')) or relative == 'shaders.properties':
            assert restore_aurora_source(relative,read(relative)) == prior(relative),relative
            pinned += 1
    assert len(list(shaders.glob('*.vsh'))) == len(list(shaders.glob('*.fsh'))) == 24
    labels = read('lang/en_us.lang')
    assert labels.startswith(prior('lang/en_us.lang'))
    source = read('lib/aurora.glsl')
    code = compact(source)
    for token in (
            'if(isnan(seconds)||isinf(seconds))seconds=0.0;',
            '6.28318530718*fract(max(seconds,0.0)*(float(AURORA_SPEED)/200.0))',
            'vec2uv=worldDirection.xz/(max(worldDirection.y,0.0)+0.18);',
            'for(intribbon=0;ribbon<3;++ribbon)',
            '-0.8-0.55*index+0.18*sin(1.6*uv.x+phase+2.0*index)+0.09*sin(3.1*uv.x-2.0*phase+index)',
            'floatcoreDistance=distance/0.10;', 'floattailDistance=(distance-0.22)/0.30;',
            'floatcore=exp(-coreDistance*coreDistance);', 'floattail=exp(-tailDistance*tailDistance);',
            '0.5+0.5*sin(11.0*uv.x+sin(2.3*uv.x-2.0*phase)+3.0*phase+2.0*index)',
            '0.35+0.65*fold*fold',
            'striation*(vec3(0.08,1.35,0.75)*core+vec3(0.25,0.05,0.55)*(0.45*tail))',
            'returnclamp(light,0.0,2.0);',
            'clamp(AURORA_INTENSITY,0.0,1.0)*clamp(SKY_BLEND,0.0,1.0)*celestialEnvironmentWeight()',
            'dot(celestialUnit(sunPosition),celestialUnit(upPosition))',
            '1.0-smoothstep(-0.20,-0.05,elevation)', 'weight*=night*dry*dry;',
            'if(isnan(weight)||isinf(weight)||weight<=0.0)returnscene;',
            'if(any(isnan(rayView))||any(isinf(rayView)))returnscene;',
            'if(scale<=1e-6)returnscene;',
            'mat3(gbufferModelViewInverse)*celestialUnit(rayView)',
            'if(any(isnan(worldDirection))||any(isinf(worldDirection)))returnscene;',
            'worldDirection=celestialUnit(worldDirection);',
            'smoothstep(0.04,0.18,height)*(1.0-smoothstep(0.82,0.98,height))',
            'smoothstep(0.0,0.45,-worldDirection.z)',
            'returnscene+auroraRibbonLight(worldDirection)*weight;'):
        assert token in code,token
    assert 'pow(' not in code
    assert 'cameraPosition' not in code and 'gbufferModelViewInverse[3]' not in code
    geometry = read('lib/geometry/sky_fragment.glsl')
    assert geometry.count(AURORA_CALL) == 1
    assert body(geometry,'main').count('applyNightAurora(') == 1
    assert geometry.index('color = vec4(applyAuroraSky') < geometry.index(AURORA_CALL)
    # Exact M10 restoration pins stars/void branches, alpha, base sky and all fog.
    assert restore_aurora_source('lib/geometry/sky_fragment.glsl',geometry) == prior('lib/geometry/sky_fragment.glsl')
    for path in sorted(shaders.glob('*.fsh')):
        expanded = expand(path)
        assert ('applyNightAurora(' in expanded) == (path.stem == 'gbuffers_skybasic'),path.name
    for mode,enabled,style,debug in product((0,1),(0,1),(0,1),range(7)):
        selected = preprocess(expand(shaders/'gbuffers_skybasic.fsh'),debug,False,
                              overrides={'SCENE_COLOR_MODE':mode,'AURORA_ENABLED':enabled,'SKY_STYLE':style})
        active = mode and enabled and style and not debug
        if not active:
            assert body(selected,'applyNightAurora') == 'returnscene;'
        else:
            assert 'returnscene+auroraRibbonLight(worldDirection)*weight;' in body(selected,'applyNightAurora')
        declarations = re.findall(r'^uniform\s+\w+\s+(\w+)\s*;',selected,re.M)
        assert len(declarations) == len(set(declarations))
    props = read('shaders.properties')
    for name,default in (('AURORA_ENABLED','1'),('AURORA_INTENSITY','0.6'),('AURORA_SPEED','1')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',read('lib/aurora_settings.glsl'),re.M)
        assert name in props.split('screen.AURORA =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    # Sample all azimuths and horizon/zenith transition heights, plus exact poles.
    directions = []
    for angle,height in product(range(24),(-.1,0,.04,.10,.18,.4,.65,.82,.98,1)):
        azimuth = angle*math.pi/12
        radius = math.sqrt(1-height*height)
        directions.append((radius*math.sin(azimuth),height,-radius*math.cos(azimuth)))
    directions += [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    cases = 0
    scene = (.02,.03,.04)
    for direction,seconds,speed in product(directions,(0,17,99.9,199.99,200,3599.99,3600),(0,1,2)):
        raw = aurora_ribbons(direction,seconds,speed)
        assert all(math.isfinite(c) and 0 <= c <= 2 for c in raw)
        for intensity in (0,.3,.6,1):
            out = aurora_result(direction,scene,seconds,speed,intensity=intensity)
            assert all(math.isfinite(c) and 0 <= c-before <= 2+1e-12 for c,before in zip(out,scene))
            if intensity == 0:
                assert out is scene
        cases += 1
    north = unit((0,.5,-1))
    assert max(aurora_result(north,scene))-max(scene) > 0
    for override in ({'intensity':0},{'sky_blend':0},{'elevation':-.05},{'elevation':1},
                     {'rain':1},{'environment':0},{'environment':math.nan},{'environment':math.inf},
                     {'enabled':False},{'mode':0},{'style':0}):
        assert aurora_result(north,scene,**override) is scene
    for stage in ('stars','void','sunset','sun','moon','clouds','terrain','fog'):
        assert aurora_result(north,scene,stage=stage) is scene
    for debug in range(1,7):
        assert aurora_result(north,scene,debug=debug) is scene
    for invalid in ((0,0,0),(1e-20,0,0),(math.nan,1,0),(math.inf,1,0)):
        assert aurora_result(invalid,scene) is scene
    for direction in ((0,1,0),(0,-1,0),(1,0,0),(-1,0,0),(0,0,-1),(0,.5,1)):
        assert aurora_result(direction,scene) is scene
    for name,values in (('rain',(0,.25,.5,.75,1)),('elevation',(-.3,-.2,-.15,-.1,-.05,0))):
        amounts = [sum(aurora_result(north,scene,**{name:v})) for v in values]
        assert all(b <= a+1e-12 for a,b in zip(amounts,amounts[1:]))
    clear = aurora_result(north,scene,rain=0)
    half_rain = aurora_result(north,scene,rain=.5)
    assert close(tuple(c-s for c,s in zip(half_rain,scene)),tuple((c-s)*.25 for c,s in zip(clear,scene)))
    # Recover fixed world directions after independent yaw/pitch rotations. A
    # translation column is intentionally unused, matching mat3(inverseView).
    for ray,yaw,pitch in product((north,unit((1,.4,-1)),unit((-1,.2,-2))),(-2,-.4,0,1.7),(-1,0,.8)):
        cy,sy,cp,sp = math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        inverse_rotation = ((cy,sy*sp,sy*cp),(0,cp,-sp),(-sy,cy*sp,cy*cp))
        view = tuple(sum(inverse_rotation[j][i]*ray[j] for j in range(3)) for i in range(3))
        for translation in ((0,0,0),(10,80,-30),(-1e7,250,1e7)):
            inverse_view = [list(row)+[translation[i]] for i,row in enumerate(inverse_rotation)]
            recovered = tuple(sum(inverse_view[i][j]*view[j] for j in range(3)) for i in range(3))
            assert close(recovered,ray)
            assert close(aurora_result(recovered,scene,seconds=37),aurora_result(ray,scene,seconds=37))
    # Integer harmonics loop exactly at 200s and the 3600s runtime-clock reset.
    # fp32 phase arithmetic explicitly models finite precision at each operation.
    maximum_wrap_delta = 0.0
    for ray,speed,seconds in product(directions,(0,1,2),(0,17,99.9)):
        expected = aurora_ribbons(ray,seconds,speed)
        assert close(expected,aurora_ribbons(ray,seconds+200,speed),2e-10)
        assert close(expected,aurora_ribbons(ray,seconds+3600,speed),2e-10)
        if speed == 0:
            assert expected == aurora_ribbons(ray,0,0)
        for period in (200,3600):
            before = aurora_ribbons(ray,period-.001,speed,fp32=True)
            after = aurora_ribbons(ray,.001,speed,fp32=True)
            delta = max(abs(a-b) for a,b in zip(before,after))
            maximum_wrap_delta = max(maximum_wrap_delta,delta)
            assert delta < .005
    for invalid in (-1,math.nan,math.inf,-math.inf):
        assert temporal_phase(invalid) == 0
    assert math.isfinite(temporal_phase(3e38,2,fp32=True))
    # Signed distance is negative on one side of every ribbon; finite squared
    # Gaussian values must be symmetric there rather than invoking GLSL pow.
    for distance in (-100,-1,-.22,-.1,0,.1,.22,1,100):
        a = math.exp(-(distance/.1)**2)
        b = math.exp(-(-distance/.1)**2)
        assert math.isfinite(a) and a == b
    print('PASS: M11 {} prior shader/property files pinned; sky-only scope and exact legacy/debug/off bypass'.format(pinned))
    print('PASS: M11 {} bounded ribbon cases, finite vectors, night/rain/sky masks and cardinal/pole safety'.format(cases))
    print('PASS: M11 world-direction rotation/translation invariance and integer-harmonic 200s/3600s loops')
    print('PASS: M11 float32 clock-wrap RGB delta {:.6g}; explicit signed-distance squares'.format(maximum_wrap_delta))
    print('LIMIT: CPU analytical reference and offline GLSL only; no Minecraft/Iris/GPU rendering or performance claim')
