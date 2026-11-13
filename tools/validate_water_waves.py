"""M14 periodic water-normal contracts and independent numerical references."""
import math
import re
import struct
import subprocess
from functools import lru_cache
from itertools import product
from validate_water_depth import restore_water_depth_source

M13_BASELINE = 'fd394d3e5f60ebbb101f3cc4a48656623dcd3e34'
WAVES = ((11,3,.06,10),(4,-9,.04,-13),(7,13,.03,7))
TAU = 2*math.pi
MAX_GRADIENT = sum(amplitude*TAU/128*math.hypot(kx,kz) for kx,kz,amplitude,_ in WAVES)
OLD_NORMAL_BLOCK = '''    vec3 normal = celestialUnit(normalView);
    vec3 towardEye = celestialUnit(-viewPosition);
    vec3 reflected = reflect(-towardEye, normal);
    vec3 up = celestialUnit(upPosition);
    float upwardSurface = smoothstep(0.5, 0.95, dot(normal, up));
'''
NEW_NORMAL_BLOCK = '''    vec3 normal = celestialUnit(normalView);
    vec3 towardEye = celestialUnit(-viewPosition);
    vec3 up = celestialUnit(upPosition);
    // Face eligibility uses the original normal, so animation cannot toggle the face mask.
    float upwardSurface = smoothstep(0.5, 0.95, dot(normal, up));
    normal = waterWaveNormal(normal, viewPosition, upwardSurface);
    vec3 reflected = reflect(-towardEye, normal);
'''
ANCHOR_UNIFORMS = 'uniform ivec3 cameraPositionInt;\nuniform vec3 cameraPositionFract;\n'


def restore_water_wave_source(relative,source):
    """Restore only M14's exact normal block, shared declarations and option UI."""
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_water_depth_source(relative,source)
    if relative == 'lib/fog.glsl':
        include = '#include "/lib/camera_anchor.glsl"\n'
        assert source.count(include) == 1
        source = source.replace(include,ANCHOR_UNIFORMS,1)
    if relative == 'lib/water.glsl':
        include = '#include "/lib/water_waves.glsl"\n'
        assert source.count(include) == source.count(NEW_NORMAL_BLOCK) == 1
        source = source.replace(include,'',1).replace(NEW_NORMAL_BLOCK,OLD_NORMAL_BLOCK,1)
    if relative == 'shaders.properties':
        old_screen = 'screen.WATER = WATER_STYLE WATER_TINT_STRENGTH WATER_REFLECTION_STRENGTH'
        new_screen = old_screen+' WATER_WAVES WATER_WAVE_STRENGTH WATER_WAVE_SPEED'
        assert source.count(new_screen) == source.count('sliders = WATER_WAVE_STRENGTH ') == 1
        source = source.replace(new_screen,old_screen,1).replace('sliders = WATER_WAVE_STRENGTH ','sliders = ',1)
    return source


def fract(x):
    return x-math.floor(x)


def f32(x):
    try:
        return struct.unpack('f',struct.pack('f',x))[0]
    except OverflowError:
        return math.copysign(math.inf,x)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def unit(v):
    scale = max(map(abs,v))
    if not all(math.isfinite(x) for x in v) or scale <= 1e-6:
        return None
    v = tuple(x/scale for x in v)
    length = math.sqrt(dot(v,v))
    return tuple(x/length for x in v)


def close(a,b,tolerance=1e-10):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def clock_cycle(seconds,speed=1,fp32=False):
    seconds = max(seconds,0) if math.isfinite(seconds) else 0
    return fract(f32(f32(seconds)*f32(speed/200))) if fp32 else fract(seconds*(speed/200))


def anchored_tile(camera_int,camera_fract,player_position):
    """Match integer low-bit reduction before any float conversion of the anchor."""
    return tuple(fract(((camera_int[i]&127)+camera_fract[i]+player_position[i])/128) for i in (0,2))


def wave_height(tile,seconds=0,speed=1):
    cycle = clock_cycle(seconds,speed)
    return sum(amplitude*math.sin(TAU*fract(kx*tile[0]+kz*tile[1]+harmonic*cycle))
               for kx,kz,amplitude,harmonic in WAVES)


def wave_gradient(tile,seconds=0,speed=1,fp32=False):
    cycle = clock_cycle(seconds,speed,fp32)
    result = [0.0,0.0]
    for kx,kz,amplitude,harmonic in WAVES:
        angle = TAU*fract(kx*tile[0]+kz*tile[1]+harmonic*cycle)
        gain = amplitude*(TAU/128)*math.cos(angle)
        result[0] += gain*kx
        result[1] += gain*kz
    return tuple(result)


def matrix_vector(matrix,vector):
    return tuple(dot(row,vector) for row in matrix)


def wave_normal_from_gradient(base_normal,gradient,normal_matrix=((1,0,0),(0,1,0),(0,0,1)),
                              strength=.6,eligibility=1,enabled=True,fp32_length=False):
    if not enabled or strength <= 0 or eligibility <= 0:
        return base_normal
    if not all(math.isfinite(x) for row in normal_matrix for x in row):
        return base_normal
    if not all(math.isfinite(x) for x in gradient):
        return base_normal
    up = matrix_vector(normal_matrix,(0,1,0))
    squared = dot(up,up) if not fp32_length else f32(sum(f32(x*x) for x in up))
    up_scale = math.sqrt(squared)
    if not math.isfinite(up_scale) or up_scale <= 1e-6:
        return base_normal
    slope = matrix_vector(normal_matrix,(gradient[0],0,gradient[1]))
    weight = min(1,max(0,strength))*min(1,max(0,eligibility))
    result = tuple(n-weight*s/up_scale for n,s in zip(base_normal,slope))
    return unit(result) or base_normal


def anchored_wave_normal(base_normal,player_position,camera_int,camera_fract,seconds=0,speed=1,**options):
    if not options.get('enabled',True) or options.get('strength',.6) <= 0 or options.get('eligibility',1) <= 0:
        return base_normal
    if not all(math.isfinite(x) for x in player_position+(camera_fract[0],camera_fract[2])):
        return base_normal
    return wave_normal_from_gradient(base_normal,wave_gradient(anchored_tile(camera_int,camera_fract,player_position),seconds,speed),**options)


def validate_water_waves(root,expand,preprocess,compact,function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M13_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files = subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',
                                        M13_BASELINE,'shaders']).decode().splitlines()
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh','.properties')):
            assert restore_water_wave_source(relative,read(relative)) == prior(relative),relative
            pinned += 1
    assert len(list(shaders.glob('*.vsh'))) == len(list(shaders.glob('*.fsh'))) == 24
    assert restore_water_depth_source('lang/en_us.lang',read('lang/en_us.lang')).startswith(prior('lang/en_us.lang'))
    anchor = read('lib/camera_anchor.glsl')
    assert anchor.startswith('#ifndef AURORA_CAMERA_ANCHOR_INCLUDED\n#define AURORA_CAMERA_ANCHOR_INCLUDED\n')
    assert anchor.endswith('#endif\n') and anchor.count(ANCHOR_UNIFORMS) == 1
    wave = read('lib/water_waves.glsl')
    code = compact(wave)
    for token in ('if(isnan(seconds)||isinf(seconds))seconds=0.0;',
                  'fract(max(seconds,0.0)*(float(WATER_WAVE_SPEED)/200.0))',
                  'vec2(11.0,3.0),vec2(4.0,-9.0),vec2(7.0,13.0)',
                  'float[3](0.06,0.04,0.03)', 'float[3](10.0,-13.0,7.0)',
                  'for(intwave=0;wave<3;++wave)',
                  '6.28318530718*fract(dot(directions[wave],tile)+harmonics[wave]*cycle)',
                  'amplitudes[wave]*(6.28318530718/128.0)*directions[wave]*cos(angle)',
                  'clamp(WATER_WAVE_STRENGTH,0.0,1.0)*clamp(surfaceEligibility,0.0,1.0)',
                  'if(strength<=0.0)returnbaseNormal;', 'vec3playerPosition=viewToPlayerPosition(viewPosition);',
                  'any(isnan(playerPosition))||any(isinf(playerPosition))',
                  'any(isnan(cameraPositionFract.xz))||any(isinf(cameraPositionFract.xz))',
                  'vec2anchor=vec2(uvec2(cameraPositionInt.xz)&uvec2(127u));',
                  'vec2tile=fract((anchor+cameraPositionFract.xz+playerPosition.xz)/128.0);',
                  'mat3normalToView=transpose(mat3(gbufferModelViewInverse));',
                  'vec3upView=normalToView*vec3(0.0,1.0,0.0);',
                  'vec3slopeView=normalToView*vec3(slope.x,0.0,slope.y);',
                  'any(isnan(upView))||any(isinf(upView))||any(isnan(slopeView))||any(isinf(slopeView))',
                  'if(isnan(upLength)||isinf(upLength)||upLength<=1e-6)returnbaseNormal;',
                  'vec3perturbed=baseNormal-slopeView/upLength;',
                  'if(any(isnan(perturbed))||any(isinf(perturbed)))returnbaseNormal;',
                  'if(scale<=1e-6)returnbaseNormal;', 'returncelestialUnit(perturbed);'):
        assert token in code,token
    assert '%' not in code and not re.search(r'\bvec2\(cameraPositionInt',code)
    assert 'sampler' not in code and 'gl_Position' not in code and 'gl_FragDepth' not in code
    water = restore_water_depth_source('lib/water.glsl',read('lib/water.glsl'))
    assert water.count(NEW_NORMAL_BLOCK) == 1
    effect = body(water,'applyWaterStyle')
    assert effect.count('floatupwardSurface=') == effect.count('waterWaveNormal(') == 1
    assert effect.index('floatupwardSurface=') < effect.index('waterWaveNormal(') < effect.index('vec3reflected=') < effect.index('waterFresnel(')
    assert effect.index('if(reflectionWeight<=0.0)returntinted;') < effect.index('waterWaveNormal(')
    # Off uses the exact old normal. Narrow block restoration proves all old
    # Fresnel/reflection/tint operations are otherwise identical to M13.
    assert restore_water_wave_source('lib/water.glsl',read('lib/water.glsl')) == prior('lib/water.glsl')
    for mode,enabled,style,debug in product((0,1),(0,1),(0,1),range(7)):
        selected = preprocess(expand(shaders/'gbuffers_water.fsh'),debug,False,
                              overrides={'SCENE_COLOR_MODE':mode,'WATER_WAVES':enabled,'WATER_STYLE':style})
        if not enabled:
            assert body(selected,'waterWaveNormal') == 'returnbaseNormal;'
        if not mode or not style or debug:
            assert body(selected,'applyWaterStyle') == 'returnscene;'
        uniforms = re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms) == len(set(uniforms))
        assert uniforms.count('cameraPositionInt') == uniforms.count('cameraPositionFract') == 1
        assert uniforms.count('frameTimeCounter') == 1
    for path in shaders.glob('*.fsh'):
        selected = preprocess(expand(path),0,False)
        assert ('waterWaveNormal(' in selected) == (path.stem == 'gbuffers_water'),path.name
    settings,props,labels = read('lib/water_wave_settings.glsl'),read('shaders.properties'),read('lang/en_us.lang')
    for name,default in (('WATER_WAVES','1'),('WATER_WAVE_STRENGTH','0.6'),('WATER_WAVE_SPEED','1')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',settings,re.M)
        assert name in props.split('screen.WATER =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    assert abs(MAX_GRADIENT-.07466212197046658) < 1e-10
    assert math.degrees(math.atan(MAX_GRADIENT)) < 4.27
    assert math.degrees(math.atan(MAX_GRADIENT*.6)) < 2.565
    # Full tile sampling and an independent finite difference of virtual height.
    normal_cases = 0
    for x,z,seconds,speed in product((0,.00001,.13,.5,.99999),(0,.03,.4,.99999),(0,17,71,199.99),(0,1,2)):
        tile = (x,z)
        gradient = wave_gradient(tile,seconds,speed)
        assert all(math.isfinite(v) for v in gradient) and math.hypot(*gradient) <= MAX_GRADIENT+1e-12
        epsilon = 1e-4  # World-block step, independently differentiate the sine height.
        for axis in (0,1):
            lo,hi = list(tile),list(tile)
            lo[axis] = fract(lo[axis]-epsilon/128)
            hi[axis] = fract(hi[axis]+epsilon/128)
            numerical = (wave_height(hi,seconds,speed)-wave_height(lo,seconds,speed))/(2*epsilon)
            assert abs(numerical-gradient[axis]) < 1e-8
        for strength,eligibility in product((0,.3,.6,1),(0,.25,.75,1)):
            base = (0,1,0)
            normal = wave_normal_from_gradient(base,gradient,strength=strength,eligibility=eligibility)
            assert all(math.isfinite(v) for v in normal) and abs(dot(normal,normal)-1) < 1e-12
            if not strength or not eligibility:
                assert normal is base
            tilt = math.atan2(math.hypot(normal[0],normal[2]),normal[1])
            assert tilt <= math.atan(MAX_GRADIENT*strength*eligibility)+1e-12
            normal_cases += 1
    # Fixed world points are represented by integer + fraction. Subtract integer
    # anchors first: these oracles never construct a large world-space float.
    anchor_cases = 0
    for target in ((2,64,-3),(-20,80,15),(128,64,-128),(30000000,100,-30000000),
                   (2147483640,0,-2147483640),(-2147483640,0,2147483640)):
        target_fract = (.375,.625,.8125)
        expected = tuple(fract(((target[i]&127)+target_fract[i])/128) for i in (0,2))
        for offsets,fraction in product(((-4,0,3),(0,0,0),(5,1,-6)),((.1,.2,.9),(.9,.8,.1))):
            camera = tuple(target[i]+offsets[i] for i in range(3))
            relative = tuple((target[i]-camera[i])+(target_fract[i]-fraction[i]) for i in range(3))
            assert close(anchored_tile(camera,fraction,relative),expected)
            anchor_cases += 1
    for camera_x in (-.1,.1,127.9,128.1,-128.1,-127.9):
        for splitter in (math.floor,math.trunc):
            integer = splitter(camera_x)
            fraction = camera_x-integer
            relative_x = (2-integer)+(.375-fraction)
            assert close(anchored_tile((integer,0,0),(fraction,0,0),(relative_x,0,3.25)),(2.375/128,3.25/128))
            anchor_cases += 1
    for integer in (-2147483648,2147483647,-30000000,30000000,-129,-128,-1,0,127,128):
        for delta in (-128,0,128):
            tile = anchored_tile((integer,0,integer),(.375,0,.625),(delta+1.25,0,delta-2.5))
            expected = (fract(((integer&127)+1.625)/128),fract(((integer&127)-1.875)/128))
            assert close(tile,expected)
            anchor_cases += 1
    # Spatial tile edges and temporal resets preserve value AND derivative.
    maximum_wrap_delta = 0.0
    for tile,seconds,speed in product(((0,0),(.13,.47),(.99999,.99999)),(0,17,71),(0,1,2)):
        expected = wave_gradient(tile,seconds,speed)
        for shift in ((1,0),(0,1),(-1,0),(0,-1)):
            assert close(expected,wave_gradient((tile[0]+shift[0],tile[1]+shift[1]),seconds,speed))
        for period in (200,3600):
            assert close(expected,wave_gradient(tile,seconds+period,speed))
            before = wave_gradient(tile,period-.001,speed,fp32=True)
            after = wave_gradient(tile,.001,speed,fp32=True)
            delta = max(abs(a-b) for a,b in zip(before,after))
            maximum_wrap_delta = max(maximum_wrap_delta,delta)
            assert delta < .0002
        if speed == 0:
            assert expected == wave_gradient(tile,0,0)
    assert wave_gradient((.13,.47),0,0) != (0,0)  # Speed zero freezes, rather than flattens.
    for invalid in (-1,math.nan,math.inf,-math.inf):
        assert clock_cycle(invalid) == 0
    assert math.isfinite(clock_cycle(3e38,2,fp32=True))
    gradient,base = wave_gradient((.13,.47),17,1),(0,1,0)
    assert wave_normal_from_gradient(base,gradient,enabled=False) is base
    assert wave_normal_from_gradient(base,gradient,strength=0) is base
    for bad in (((0,0,0),(0,0,0),(0,0,0)),((math.nan,0,0),(0,1,0),(0,0,1)),
                ((math.inf,0,0),(0,1,0),(0,0,1))):
        assert wave_normal_from_gradient(base,gradient,bad) is base
    assert wave_normal_from_gradient(base,(math.nan,0)) is base
    assert wave_normal_from_gradient(base,gradient,((1,0,0),(0,1e30,0),(0,0,1)),fp32_length=True) is base
    for invalid in (math.nan,math.inf,-math.inf):
        assert anchored_wave_normal(base,(invalid,0,0),(0,0,0),(0,0,0)) is base
        assert anchored_wave_normal(base,(0,0,0),(0,0,0),(0,0,invalid)) is base
    # A rotated normal matrix must rotate the perturbed result. For nonuniform
    # scale, compare against the transformed horizontal world normal analytically;
    # the world/rigid-camera angle bound intentionally does not apply in view space.
    for yaw,pitch,scales in product((-2,0,.7),(-.8,0,.5),((1,1,1),(.5,2,3),(3,.75,.4))):
        cy,sy,cp,sp = math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        rotation = ((cy,0,sy),(sp*sy,cp,-sp*cy),(-cp*sy,sp,cp*cy))
        normal_matrix = tuple(tuple(rotation[i][j]/scales[j] for j in range(3)) for i in range(3))
        base_view = unit(matrix_vector(normal_matrix,base))
        actual = wave_normal_from_gradient(base_view,gradient,normal_matrix,strength=.6)
        expected = unit(matrix_vector(normal_matrix,(-gradient[0]*.6,1,-gradient[1]*.6)))
        assert close(actual,expected)
        if scales == (1,1,1):
            world = wave_normal_from_gradient(base,gradient,strength=.6)
            assert close(actual,matrix_vector(rotation,world))
            # Compose anchor reduction with inverse-view rotation AND translation.
            # This catches accidentally feeding view space directly to the tiled field.
            player = (2.375,4.625,-5.1875)
            translation = (.2,1.62,-.1)
            view = matrix_vector(rotation,tuple(p-t for p,t in zip(player,translation)))
            inverse_rotation = tuple(tuple(rotation[j][i] for j in range(3)) for i in range(3))
            recovered = tuple(x+t for x,t in zip(matrix_vector(inverse_rotation,view),translation))
            assert close(recovered,player)
            anchor_int,anchor_fract = (30000000,80,-30000000),(.25,.5,.75)
            direct = anchored_wave_normal(base,player,anchor_int,anchor_fract,seconds=17)
            posed = anchored_wave_normal(matrix_vector(rotation,base),recovered,anchor_int,anchor_fract,
                                         seconds=17,normal_matrix=rotation)
            assert close(posed,matrix_vector(rotation,direct))
    print('PASS: M14 {} prior shader/property files pinned; shared anchor declarations only, old waves-off reflection retained'.format(pinned))
    print('PASS: M14 {} bounded unit-normal cases; independent finite-difference gradient and 4.27/2.565 degree rigid-camera limits'.format(normal_cases))
    print('PASS: M14 {} fixed-point/anchor cases; negative/large/INT limits, 128-block tiling and 200s/3600s clocks'.format(anchor_cases))
    print('PASS: M14 matrix/zero/invalid fallbacks, original face eligibility and float32 clock-wrap gradient delta {:.6g}'.format(maximum_wrap_delta))
    print('LIMIT: normals only; no vertex waves, Iris/GPU runtime validation or measured performance')
