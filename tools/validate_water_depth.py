"""M16 nonlinear-depth reconstruction and luminance-preserving water color oracles.

The reference geometry is generated from world-space pool planes and projected
independently. No GPU/Iris execution is performed by this module.
"""
import math
import re
import struct
import subprocess
from functools import lru_cache
from itertools import product
from validate_settings_profiles import restore_settings_profiles_source
from validate_water_filtered_waves import restore_water_filtered_source

M15_BASELINE = 'bc811801441709143cbb2ef33a2db3dadc597ee7'
LUMA = (.2126, .7152, .0722)
DEEP_CHROMA = (.25, .85, 1.05)
IDENTITY4 = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))
OLD_EARLY_RETURN = '    if (WATER_TINT_STRENGTH <= 0.0 && WATER_REFLECTION_STRENGTH <= 0.0) return scene;\n'
NEW_EARLY_RETURN = '''    if (WATER_TINT_STRENGTH <= 0.0 && WATER_REFLECTION_STRENGTH <= 0.0
        && (WATER_DEPTH_TINT == 0 || WATER_DEPTH_STRENGTH <= 0.0)) return scene;
'''
DEPTH_CALL = '''    // Depth color is independent of the M13 tint/reflection and Aurora Sky controls.
    tinted = applyWaterDepthTint(tinted, viewPosition, normalView, environment * skyAccess * (1.0 - levels.x));
'''
OLD_STYLE_LABEL = 'option.WATER_STYLE.comment=Classified vanilla water only. Glass, lava and unknown fluids keep their original source. No waves, refraction or opacity changes.\n'
NEW_STYLE_LABEL = OLD_STYLE_LABEL.replace('No waves,','No vertex displacement,')


def restore_water_depth_source(relative,source):
    """Undo only M16's three exact source hooks and three exact option changes."""
    relative=relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative=relative[len('shaders/'):]
    source=restore_settings_profiles_source(relative,source)
    if relative == 'lib/water.glsl':
        include='#include "/lib/water_depth.glsl"\n'
        assert source.count(include) == source.count(NEW_EARLY_RETURN) == source.count(DEPTH_CALL) == 1
        source=source.replace(include,'',1).replace(NEW_EARLY_RETURN,OLD_EARLY_RETURN,1).replace(DEPTH_CALL,'',1)
    if relative == 'shaders.properties':
        old='screen.WATER = WATER_STYLE WATER_TINT_STRENGTH WATER_REFLECTION_STRENGTH WATER_WAVES WATER_WAVE_STRENGTH WATER_WAVE_SPEED'
        new=old+' WATER_DEPTH_TINT WATER_DEPTH_STRENGTH WATER_DEPTH_SCALE'
        sliders='sliders = WATER_DEPTH_STRENGTH WATER_DEPTH_SCALE '
        assert source.count(new) == source.count(sliders) == 1
        source=source.replace(new,old,1).replace(sliders,'sliders = ',1)
    if relative == 'lang/en_us.lang':
        assert source.count(NEW_STYLE_LABEL) == 1
        source=source.replace(NEW_STYLE_LABEL,OLD_STYLE_LABEL,1)
    return source


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def matrix_vector(matrix,vector):
    return tuple(dot(row,vector) for row in matrix)


def finite(values):
    return all(math.isfinite(x) for x in values)


def clamp(value,lo=0.0,hi=1.0):
    return min(hi,max(lo,value))


def smooth(a,b,value):
    t=clamp((value-a)/(b-a))
    return t*t*(3-2*t)


def unit(vector):
    if not finite(vector):
        return None
    scale=max(map(abs,vector))
    if scale <= 1e-6:
        return None
    scaled=tuple(x/scale for x in vector)
    length=math.sqrt(dot(scaled,scaled))
    return tuple(x/length for x in scaled)


def f32(value):
    try:
        return struct.unpack('f',struct.pack('f',value))[0]
    except OverflowError:
        return math.copysign(math.inf,value)


def inverse_matrix(matrix):
    """Gauss-Jordan inverse for independent fixture generation (row-major input)."""
    size=len(matrix)
    rows=[list(map(float,row))+[float(i==j) for j in range(size)] for i,row in enumerate(matrix)]
    for column in range(size):
        pivot=max(range(column,size),key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) <= 1e-15:
            raise ValueError('Singular matrix')
        rows[column],rows[pivot]=rows[pivot],rows[column]
        scale=rows[column][column]
        rows[column]=[value/scale for value in rows[column]]
        for row in range(size):
            if row != column:
                factor=rows[row][column]
                rows[row]=[x-factor*y for x,y in zip(rows[row],rows[column])]
    return tuple(tuple(row[size:]) for row in rows)


def perspective_matrix(fov_y=70.0,aspect=16/9,near=.05,far=1024.0):
    """OpenGL perspective, right-handed view coordinates looking toward -Z."""
    focal=1/math.tan(math.radians(fov_y)/2)
    return ((focal/aspect,0,0,0),(0,focal,0,0),
            (0,0,(far+near)/(near-far),2*far*near/(near-far)),(0,0,-1,0))


def project_view(position,projection):
    """Return ((u,v), depth) from an independently constructed view-space point."""
    clip=matrix_vector(projection,tuple(position)+(1,))
    ndc=tuple(value/clip[3] for value in clip[:3])
    return ((ndc[0]+1)/2,(ndc[1]+1)/2),(ndc[2]+1)/2


def reconstruct_view(screen_uv,depth,projection_inverse):
    homogeneous=matrix_vector(projection_inverse,(2*screen_uv[0]-1,2*screen_uv[1]-1,2*depth-1,1))
    if not finite(homogeneous) or homogeneous[3] == 0:
        return None
    result=tuple(x/homogeneous[3] for x in homogeneous[:3])
    return result if finite(result) else None


def depth_drop(screen_uv,surface_depth,background_depth,surface_view,projection_inverse,
               model_view_inverse=IDENTITY4):
    """Vertical world-space drop behind the same pixel, bounded to [0,32].

    UV is the current fragment center divided by the actual depth texture extent;
    callers must reject an out-of-bounds integer pixel before fetching depthtex2.
    Invalid/foreground/sky/non-descending inputs deliberately return zero.
    """
    if not finite(screen_uv) or any(x < 0 or x >= 1 for x in screen_uv):
        return 0.0
    if not finite((surface_depth,background_depth)):
        return 0.0
    if surface_depth < 0 or surface_depth >= 1 or background_depth <= surface_depth or background_depth >= 1:
        return 0.0
    direction=unit(surface_view)
    if direction is None:
        return 0.0
    background=reconstruct_view(screen_uv,background_depth,projection_inverse)
    if background is None:
        return 0.0
    delta=tuple(b-s for b,s in zip(background,surface_view))
    ray_gap=dot(delta,direction)
    if not finite(delta) or not math.isfinite(ray_gap) or ray_gap <= 0:
        return 0.0
    # Only the upper-left 3x3 is read, just as a direction transform requires.
    # Even a nonfinite unused translation cannot contaminate this operation.
    world_delta=tuple(dot(row[:3],delta) for row in model_view_inverse[:3])
    if not finite(world_delta):
        return 0.0
    return clamp(-world_delta[1],0,32)


def depth_fraction(drop,scale=8.0):
    if not finite((drop,scale)):
        return 0.0
    return -math.expm1(-clamp(drop,0,32)/max(scale,1e-4))


def depth_color(scene,drop,strength=.35,scale=8.0,eligibility=1.0,environment=1.0,
                sky=1.0,block=0.0,enabled=True):
    """Artistic source RGB; native alpha/reflection/fog are separate operations."""
    if not enabled or strength <= 0:
        return scene
    if not finite(scene) or not finite((strength,scale,eligibility,environment,sky,block)):
        return scene
    weight=clamp(strength,0,.35)*clamp(eligibility)*clamp(environment*sky*(1-block))*depth_fraction(drop,scale)
    if weight <= 0:
        return scene
    peak=max(scene)
    if peak <= 0 or min(scene) < 0:
        return scene
    scaled=tuple(c/peak for c in scene)
    colored=tuple(c*g for c,g in zip(scaled,DEEP_CHROMA))
    renormalization=dot(scaled,LUMA)/dot(colored,LUMA)
    target=tuple(c*renormalization for c in colored)
    result=tuple((c+(t-c)*weight)*peak for c,t in zip(scaled,target))
    return result if finite(result) and min(result) >= 0 and max(result) <= 65504 else scene


def normal_eligibility(normal,up=(0,1,0)):
    n,u=unit(normal),unit(up)
    return 0.0 if n is None or u is None else smooth(.5,.95,dot(n,u))


def depth_pixel(fragment_xy,extent):
    """Return the exact texel and its center UV, or None before any sample."""
    if not finite(fragment_xy) or any(size <= 0 for size in extent):
        return None
    if any(value < 0 or value >= size for value,size in zip(fragment_xy,extent)):
        return None
    pixel=tuple(int(value) for value in fragment_xy)
    return pixel,tuple((value+.5)/size for value,size in zip(pixel,extent))


def close(a,b,tolerance=1e-10):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def validate_numerical_depth():
    # Independent world-space construction: the two intersections of one ray
    # with horizontal pool planes must recover their known vertical separation.
    pool_cases=0
    float32_error=0.0
    for height,horizontal,drop,yaw,fov,aspect in product((1,3,12),(2,9,40),(.01,.5,4,16,40),
                                                       (-2,0,.7),(45,100),(1,16/9)):
        sy,cy=math.sin(yaw),math.cos(yaw)
        ray=unit((horizontal*sy,-height,-horizontal*cy))
        right=(cy,0,sy)
        up=(-ray[1]*sy,math.hypot(ray[0],ray[2]),ray[1]*cy)
        rotation=(right,up,tuple(-x for x in ray))
        surface_world=(horizontal*sy,-height,-horizontal*cy)
        background_world=tuple(x*(1+drop/height) for x in surface_world)
        surface=matrix_vector(rotation,surface_world)
        background=matrix_vector(rotation,background_world)
        projection=perspective_matrix(fov,aspect,.05,4096)
        inverse=inverse_matrix(projection)
        uv,surface_depth=project_view(surface,projection)
        background_uv,background_depth=project_view(background,projection)
        assert close(uv,background_uv)
        # Nonzero and extreme translations must have no influence on a delta.
        for translation in ((0,0,0),(1.25,1.62,-.75),(30000000,80,-30000000)):
            inverse_view=tuple(tuple(rotation[j][i] for j in range(3))+(translation[i],) for i in range(3))+((0,0,0,1),)
            actual=depth_drop(uv,surface_depth,background_depth,surface,inverse,inverse_view)
            assert abs(actual-min(drop,32)) < 3e-8,(height,horizontal,drop,actual)
            normal_view=matrix_vector(rotation,(0,1,0))
            assert abs(normal_eligibility(normal_view,normal_view)-1) < 1e-12
        # A real depth texture is float32. Quantify its geometric error separately
        # from the precise project/unproject identity above, without assuming
        # nonlinear depth differences are world-space distances.
        actual32=depth_drop(tuple(map(f32,uv)),f32(surface_depth),f32(background_depth),
                            tuple(map(f32,surface)),tuple(tuple(map(f32,row)) for row in inverse),inverse_view)
        float32_error=max(float32_error,abs(actual32-min(drop,32)))
        assert abs(actual32-min(drop,32)) < .03,(height,horizontal,drop,actual32)
        pool_cases += 1
    # Show why subtracting depthtex2 - gl_FragCoord.z is not a thickness metric.
    projection=perspective_matrix(70,1,.1,1000)
    near_delta=project_view((0,0,-4),projection)[1]-project_view((0,0,-2),projection)[1]
    far_delta=project_view((0,0,-42),projection)[1]-project_view((0,0,-40),projection)[1]
    assert near_delta > far_delta*100
    inverse=inverse_matrix(projection)
    surface=(0,-2,-4)
    uv,front=project_view(surface,projection)
    _,back=project_view((0,-4,-8),projection)
    assert abs(depth_drop(uv,front,back,surface,inverse)-2) < 1e-11
    unused_translation=tuple(tuple(row[:3])+(math.nan,) for row in IDENTITY4[:3])+((0,0,0,1),)
    assert abs(depth_drop(uv,front,back,surface,inverse,unused_translation)-2) < 1e-11
    # Boundaries reject sky, foreground, equal depth and invalid input before
    # dereferencing arbitrary pixels or manufacturing a non-existent water column.
    for invalid in (-math.inf,math.nan,math.inf,-.1,1,1.1):
        assert depth_drop(uv,invalid,back,surface,inverse) == 0
        assert depth_drop(uv,front,invalid,surface,inverse) == 0
    for background in (0,front*.5,front):
        assert depth_drop(uv,front,background,surface,inverse) == 0
    for invalid_uv in ((-1e-6,.5),(1,.5),(.5,1),(.5,-1),(.5,math.nan),(math.inf,.5)):
        assert depth_drop(invalid_uv,front,back,surface,inverse) == 0
    for invalid_view in ((0,0,0),(1e-30,0,0),(math.nan,0,0),(0,math.inf,0)):
        assert depth_drop(uv,front,back,invalid_view,inverse) == 0
    for bad_matrix in (tuple((0,0,0,0) for _ in range(4)),
                       ((math.nan,0,0,0),)+inverse[1:],((math.inf,0,0,0),)+inverse[1:]):
        assert depth_drop(uv,front,back,surface,bad_matrix) == 0
    bad_inverse_view=((math.nan,0,0,0),)+IDENTITY4[1:]
    assert depth_drop(uv,front,back,surface,inverse,bad_inverse_view) == 0
    assert depth_drop(uv,front,back,surface,inverse,tuple((0,0,0,0) for _ in range(4))) == 0
    # A larger supplied surface point than the reconstructed background yields a
    # negative ray gap, even if its passed-in depth number claims otherwise.
    assert depth_drop(uv,front,back,tuple(x*3 for x in surface),inverse) == 0
    # Looking upwards cannot turn an above-water sample into positive depth.
    upward=(0,2,-4)
    upward_uv,upfront=project_view(upward,projection)
    upback=project_view((0,4,-8),projection)[1]
    assert depth_drop(upward_uv,upfront,upback,upward,inverse) == 0
    for extent in ((1,1),(3,2),(7,5),(1920,1080)):
        for pixel in ((0,0),(extent[0]-1,extent[1]-1)):
            for offset in (.001,.5,.999):
                found,center=depth_pixel(tuple(x+offset for x in pixel),extent)
                assert found == pixel
                assert center == tuple((x+.5)/size for x,size in zip(pixel,extent))
        for fragment in ((-.001,0),(0,-.001),(extent[0],0),(0,extent[1]),(math.nan,0),(math.inf,0)):
            assert depth_pixel(fragment,extent) is None
    assert depth_pixel((0,0),(0,1)) is None
    # A small but nonzero homogeneous divisor is allowed by the existing helper.
    tiny_w=((1,0,0,0),(0,1,0,0),(0,0,1,-1),(0,0,0,1e-7))
    assert reconstruct_view((.5,.25),.75,tiny_w) == (0,-5e6,-5e6)
    for scale in (4,8,16,32):
        fractions=[depth_fraction(drop,scale) for drop in (0,.001,.1,1,4,8,16,32,100)]
        assert fractions[0] == 0 and fractions == sorted(fractions)
        assert all(0 <= fraction < 1 for fraction in fractions)
        assert fractions[-1] == fractions[-2]
        assert abs(depth_fraction(scale,scale)-(1-math.exp(-1))) < 1e-14
    for drop in (.1,1,8,32):
        assert [depth_fraction(drop,s) for s in (4,8,16,32)] == sorted(
            (depth_fraction(drop,s) for s in (4,8,16,32)),reverse=True)
    print('PASS: M16 {} projected pool cases; nonlinear perspective, camera pitch/yaw and translation-free vertical depth'.format(pool_cases))
    print('PASS: M16 invalid/sky/front/equal/negative-ray/depth bounds; float32 reconstruction error <= {:.6g} blocks in fixtures'.format(float32_error))


def validate_numerical_color():
    scenes=((0,0,0),(.2,.4,.6),(1,1,1),(1,0,0),(0,1,0),(0,0,1),(4,1,.25),
            (1e-20,2e-20,5e-20),(64,128,256))
    cases=0
    for scene,drop,strength,scale,environment,sky,block in product(scenes,(0,.1,4,16,32),
            (0,.15,.25,.35),(4,8,16,32),(0,.4,1),(0,.5,1),(0,.5,1)):
        result=depth_color(scene,drop,strength=strength,scale=scale,environment=environment,sky=sky,block=block)
        assert finite(result) and min(result) >= 0
        assert abs(dot(result,LUMA)-dot(scene,LUMA)) <= max(1e-30,dot(scene,LUMA)*3e-15)
        if not drop or not strength or not environment or not sky or block == 1 or max(scene) == 0:
            assert result is scene
        # Interpolation is bounded by source and the independently computed
        # chroma-renormalized endpoint, even for bright and tiny RGB inputs.
        if max(scene) > 0:
            colored=tuple(c*g for c,g in zip(scene,DEEP_CHROMA))
            endpoint=tuple(c*dot(scene,LUMA)/dot(colored,LUMA) for c in colored)
            for original,actual,target in zip(scene,result,endpoint):
                assert min(original,target)-1e-12 <= actual <= max(original,target)+1e-12
        cases += 1
    scene=(.2,.4,.6)
    for options in ({'enabled':False},{'strength':0},{'eligibility':0},{'environment':0},{'sky':0},{'block':1}):
        assert depth_color(scene,8,**options) is scene
    assert depth_color(scene,32,strength=1) == depth_color(scene,32,strength=.35)
    for normal in ((1,0,0),(0,-1,0),(0,0,0),(math.nan,0,0),(math.inf,0,0)):
        assert normal_eligibility(normal) == 0
        assert depth_color(scene,8,eligibility=normal_eligibility(normal)) is scene
    assert normal_eligibility((0,1,0)) == 1
    assert 0 < normal_eligibility((.6,.8,0)) < 1
    for invalid in (math.nan,math.inf,-math.inf):
        assert depth_color(scene,invalid) is scene
        for key in ('strength','scale','eligibility','environment','sky','block'):
            assert depth_color(scene,8,**{key:invalid}) is scene
        bad=(invalid,.3,.7)
        assert depth_color(bad,8) is bad
    negative=(-.1,.2,.3)
    assert depth_color(negative,8) is negative
    for bright in ((65504,65504,65504),(60000,65000,65504),(1e30,2e30,3e30)):
        assert depth_color(bright,32) is bright
    # Depth color remains source RGB. Its alpha endpoints and one subsequent fog
    # composition follow the existing translucent-water blend exactly.
    styled=depth_color(scene,8)
    assert styled != scene
    background,atmosphere=(.8,.2,.1),(.3,.4,.5)
    for transmission,alpha in product((0,.2,.7,1),(0,.1,.5,1)):
        fogged=tuple(f+(c-f)*transmission for c,f in zip(styled,atmosphere))
        result=tuple(alpha*c+(1-alpha)*b for c,b in zip(fogged,background))
        if alpha == 0:
            assert result == background
        if alpha == 1:
            assert result == fogged
    print('PASS: M16 {} finite bounded color cases; arbitrary-RGB luminance, original-face/cave/torch protection and exact bypasses'.format(cases))


def validate_water_depth(root,expand,preprocess,compact,function_body):
    shaders=root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M15_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',M15_BASELINE,'shaders']).decode().splitlines()
    pinned=0
    for path in old_files:
        relative=path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh','.properties')):
            assert restore_water_depth_source(relative,read(relative)) == prior(relative),relative
            pinned += 1
    assert len(list(shaders.glob('*.vsh'))) == len(list(shaders.glob('*.fsh'))) == 24
    assert restore_water_depth_source('lang/en_us.lang',read('lang/en_us.lang')).startswith(prior('lang/en_us.lang'))
    new_files=set(str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file())-set(old_files)
    assert new_files == {'shaders/lib/water_depth.glsl','shaders/lib/water_depth_settings.glsl','shaders/lang/zh_cn.lang','shaders/lib/foliage.glsl','shaders/lib/foliage_settings.glsl','shaders/lib/celestial_glow.glsl','shaders/lib/celestial_glow_settings.glsl','shaders/lib/water_scene_snapshot.glsl','shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'},new_files
    source=read('lib/water_depth.glsl')
    assert source.startswith('#ifndef AURORA_WATER_DEPTH_INCLUDED\n#define AURORA_WATER_DEPTH_INCLUDED\n')
    assert source.endswith('#endif\n')
    code=compact(source)
    # Keep source assertions at integration boundaries. Numerical appearance,
    # finite fallbacks and nonlinear depth are checked by independent oracles and
    # the native GPU suite, not a line-by-line copy of this implementation.
    for contract in (
            'uniformsampler2Ddepthtex2;',
            'dot(celestialUnit(normalView),celestialUnit(upPosition))',
            'vec2pixelCenterUV=(vec2(pixel)+0.5)/vec2(depthSize);',
            'reconstructViewPosition(pixelCenterUV,backgroundDepth)',
            'vec3deltaView=backgroundView-surfaceView;',
            'mat3(gbufferModelViewInverse)*deltaView'):
        assert contract in code,contract
    assert code.count('texelFetch(') == 1
    assert re.findall(r'uniform\s+sampler2D\s+(\w+);',source) == ['depthtex2']
    for forbidden in ('depthtex0','depthtex1','colortex','cameraPosition','texture(','gl_FragDepth',
                      'gl_Position','waterWaveNormal(','applyLateAtmosphericFog(','applyAtmosphericFog(','.a='):
        assert forbidden not in code,forbidden
    assert code.index('greaterThanEqual(gl_FragCoord.xy') < code.index('ivec2pixel=') < code.index('texelFetch(')
    assert code.index('backgroundDepth<=surfaceDepth') < code.index('reconstructViewPosition(')
    assert code.index('rayGap<=0.0') < code.index('mat3(gbufferModelViewInverse)') < code.index('floatdrop=')
    water=restore_water_filtered_source('lib/water.glsl',read('lib/water.glsl'))
    effect=body(water,'applyWaterStyle')
    assert water.count(DEPTH_CALL) == water.count(NEW_EARLY_RETURN) == 1
    assert effect.index('waterSurface!=1') < effect.index('supportedBlend=') < effect.index('celestialEnvironmentWeight()')
    assert effect.index('scene*mix(') < effect.index('applyWaterDepthTint(') < effect.index('waterWaveNormal(')
    assert effect.index('applyWaterDepthTint(') < effect.index('floatreflectionWeight=')
    # Full historical restore above pins original flat IDs, all outputs, native
    # alpha, texture coordinates, water reflection normals and single late fog.
    for mode,style,enabled,sky_style,debug in product((0,1),(0,1),(0,1),(0,1),range(7)):
        fs=preprocess(expand(shaders/'gbuffers_water.fsh'),debug,False,
                      overrides={'SCENE_COLOR_MODE':mode,'WATER_STYLE':style,'WATER_DEPTH_TINT':enabled,'SKY_STYLE':sky_style,'WATER_SCREEN_REFLECTIONS':0})
        helper=body(fs,'applyWaterDepthTint')
        active=body(fs,'applyWaterStyle')
        if not enabled:
            assert helper == 'returnscene;'
        if not mode or not style or debug:
            assert active == 'returnscene;'
        else:
            assert active.count('applyWaterDepthTint(') == 1
            if not sky_style:
                assert active.endswith('returntinted;') and 'auroraSkyLinear(' not in active
        assert body(fs,'main').count('applyLateAtmosphericFog(') == 1
    for path in shaders.glob('*.fsh'):
        selected=preprocess(expand(path),0,False)
        assert ('applyWaterDepthTint(' in selected) == (path.stem == 'gbuffers_water'),path.name
        # W1 also samples pre-hand depth in deferred; the tint hook above remains water-only.
        assert ('uniform sampler2D depthtex2;' in selected) == (path.stem in ('gbuffers_water','deferred')),path.name
        uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms) == len(set(uniforms)),path.name
    settings,props,labels=read('lib/water_depth_settings.glsl'),read('shaders.properties'),read('lang/en_us.lang')
    for name,default,choices in (('WATER_DEPTH_TINT','1','[0 1]'),
                                 ('WATER_DEPTH_STRENGTH','0.35','[0.0 0.15 0.25 0.35]'),
                                 ('WATER_DEPTH_SCALE','8.0','[4.0 8.0 16.0 32.0]')):
        assert '#define '+name+' '+default+' // '+choices in settings
        assert name in props.split('screen.WATER =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    print('PASS: M16 {} prior shader/property files pinned; one same-pixel depthtex2 read, water-only source RGB hook'.format(pinned))
    print('PASS: M16 original geometry, alpha, classification, reflection and fog retained; depth independent of base tint and sky style')
    validate_numerical_depth()
    validate_numerical_color()
    print('LIMIT: CPU/source contracts only; snapshot contents approximate background geometry, not true water volume or absorption')
