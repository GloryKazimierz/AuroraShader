"""M13 water classification, interfaces and optical-style contracts; no GPU execution."""
import math
from validate_water_debug import restore_water_debug_source
import re
import subprocess
from functools import lru_cache
from itertools import product
from validate_water_waves import restore_water_wave_source
from validate_foliage import restore_foliage_source, expand_without_foliage
from validate_water_filtered_waves import restore_water_filtered_source, restore_water_filtered_plumbing

M12_BASELINE = '4e7b8b4bb943d24eee9e46745ffeaef16bee5f4f'
WATER_VERTEX_DECL = '''#ifdef APPLY_WATER_STYLE
in vec2 mc_Entity;
flat out int waterSurface;
#endif
'''
WATER_VERTEX_ASSIGN = '''#ifdef APPLY_WATER_STYLE
    // Block ID alone is insufficient: y==1 marks a fluid draw, not its host block.
    waterSurface = (mc_Entity.x == 10001.0 && mc_Entity.y == 1.0) ? 1 : 0;
#endif
'''
WATER_FRAGMENT_DECL = '''#ifdef APPLY_WATER_STYLE
#include "/lib/water.glsl"
flat in int waterSurface;
#ifndef WRITE_SURFACE_DATA
in vec3 normalView;
#endif
#endif
'''
WATER_CALL = '''    // Use the water's own position; existing late fog still runs once afterward.
    color.rgb = applyWaterStyle(color.rgb, fogView, normalView, lmcoord, waterSurface, blendFunc, fogColor);
'''
WATER_PROPERTIES = '''
# M13 classified vanilla water, source RGB only; native alpha and late fog remain.
screen.WATER = WATER_STYLE WATER_TINT_STRENGTH WATER_REFLECTION_STRENGTH
screen.WATER.columns = 2
'''


def restore_water_plumbing(source):
    """Remove the exact nested water call before older late-fog block restoration."""
    source = restore_water_filtered_plumbing(source)
    assert source.count(WATER_CALL) <= 1
    return source.replace('#ifdef APPLY_WATER_STYLE\n'+WATER_CALL+'#endif\n','',1).replace(WATER_CALL,'',1)


def restore_water_source(relative,source):
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_water_wave_source(relative,source)
    if relative in ('gbuffers_water.vsh','gbuffers_water.fsh'):
        assert source.count('#define APPLY_WATER_STYLE\n') == 1
        source = source.replace('#define APPLY_WATER_STYLE\n','',1)
    if relative == 'lib/geometry/lit_vertex.glsl':
        assert source.count(WATER_VERTEX_DECL) == source.count(WATER_VERTEX_ASSIGN) == 1
        source = source.replace(WATER_VERTEX_DECL,'',1).replace(WATER_VERTEX_ASSIGN,'',1)
    if relative == 'lib/geometry/lit_fragment.glsl':
        assert source.count(WATER_FRAGMENT_DECL) == source.count(WATER_CALL) == 1
        source = restore_water_plumbing(source.replace(WATER_FRAGMENT_DECL,'',1))
    if relative == 'shaders.properties':
        assert source.endswith(WATER_PROPERTIES)
        assert source.count('screen = [WATER] ') == 1
        assert source.count('sliders = WATER_TINT_STRENGTH WATER_REFLECTION_STRENGTH ') == 1
        source = source[:-len(WATER_PROPERTIES)].replace('screen = [WATER] ','screen = ',1).replace(
            'sliders = WATER_TINT_STRENGTH WATER_REFLECTION_STRENGTH ','sliders = ',1)
    return source


def stage_variables(source,direction):
    """Collect interfaces with interpolation; reject duplicates instead of hiding them."""
    assert direction in ('in','out')
    pattern = r'^(?:(flat|smooth|noperspective)\s+)?'+direction+r'\s+(\w+)\s+(\w+);'
    result = {}
    for interpolation,kind,name in re.findall(pattern,source,re.M):
        assert name not in result,'Duplicate stage variable: '+name
        result[name] = (kind,interpolation or 'smooth')
    return result


def clamp(x):
    return min(1.0,max(0.0,x))


def smooth(a,b,x):
    t = clamp((x-a)/(b-a))
    return t*t*(3-2*t)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def unit(vector):
    if not all(math.isfinite(x) for x in vector):
        return None
    scale = max(map(abs,vector))
    if scale <= 1e-6:
        return None
    scaled = tuple(x/scale for x in vector)
    length = math.sqrt(dot(scaled,scaled))
    return tuple(x/length for x in scaled)


def fresnel(ndotv):
    grazing = 1-clamp(ndotv)
    return .02+.98*grazing*grazing*grazing*grazing*grazing


def reflect(incident,normal):
    cosine = dot(normal,incident)
    return tuple(i-2*cosine*n for i,n in zip(incident,normal))


def classified_water(material_id,render_type):
    return material_id == 10001 and render_type == 1


def close(a,b,tolerance=1e-11):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def water_terms(view_position,normal,lightmap_uv,up=(0,1,0),environment=1,sky_blend=1,
                tint_strength=.35,reflection_strength=.35,sky_style=1):
    """Return tint/reflection weights and reflected VIEW direction for valid inputs."""
    if not all(math.isfinite(x) for x in lightmap_uv) or not math.isfinite(environment) or environment <= 0:
        return 0.0,0.0,None
    block,sky = tuple(clamp((x-.5/16)*16/15) for x in lightmap_uv)
    tint_weight = clamp(tint_strength)*environment*sky*(1-block)
    reflection_weight = clamp(reflection_strength)*environment*sky*clamp(sky_blend) if sky_style else 0
    if reflection_weight <= 0:
        return tint_weight,0.0,None
    n,v = unit(normal),unit(tuple(-x for x in view_position))
    if n is None or v is None:
        return tint_weight,0.0,None
    u = unit(up) or (0,1,0)
    reflected = reflect(tuple(-x for x in v),n)
    reflection_weight *= smooth(.5,.95,dot(n,u))*smooth(-.10,0,dot(reflected,u))*fresnel(dot(n,v))
    return tint_weight,clamp(reflection_weight),reflected


def water_result(scene,view_position=(0,-1,0),normal=(0,1,0),lightmap_uv=(.5/16,15.5/16),
                 water_surface=1,blend=(770,771,1,0),rain=0,style=1,mode=1,debug=0,
                 reflected_sky=(.2,.45,.8),**options):
    if not style or not mode or debug or water_surface != 1:
        return scene
    if options.get('tint_strength',.35) <= 0 and options.get('reflection_strength',.35) <= 0:
        return scene
    if tuple(blend) != (0,0,0,0) and tuple(blend[:2]) not in ((770,771),(1,0)):
        return scene
    if not math.isfinite(rain):
        return scene
    tw,rw,_ = water_terms(view_position,normal,lightmap_uv,**options)
    tinted = scene if tw <= 0 else tuple(c*(1+(gain-1)*tw) for c,gain in zip(scene,(.80,1.03,1.08)))
    return tinted if rw <= 0 else tuple(c+(s-c)*rw for c,s in zip(tinted,reflected_sky))


def validate_water(root,expand,preprocess,compact,function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M12_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files = subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',
                                        M12_BASELINE,'shaders']).decode().splitlines()
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh')) or relative == 'shaders.properties':
            assert restore_water_source(relative,read(relative)) == prior(relative),relative
            pinned += 1
    assert len(list(shaders.glob('*.vsh'))) == len(list(shaders.glob('*.fsh'))) == 24
    assert restore_water_debug_source('lang/en_us.lang',read('lang/en_us.lang')).startswith(prior('lang/en_us.lang'))
    assignments = [line.strip() for line in restore_foliage_source('block.properties',read('block.properties')).splitlines() if line.strip() and not line.lstrip().startswith('#')]
    assert assignments == ['block.10001 = minecraft:water']
    # Bind the M13 oracle to the precisely restored waves-off implementation.
    source = restore_water_wave_source('lib/water.glsl',read('lib/water.glsl'))
    vertex,fragment = restore_foliage_source('lib/geometry/lit_vertex.glsl',read('lib/geometry/lit_vertex.glsl')),restore_water_filtered_source('lib/geometry/lit_fragment.glsl',read('lib/geometry/lit_fragment.glsl'))
    code = compact(source)
    for token in ('floatgrazing=1.0-clamp(normalDotView,0.0,1.0);',
                  'return0.02+0.98*squared*squared*grazing;',
                  'if(waterSurface!=1)returnscene;',
                  'if(WATER_TINT_STRENGTH<=0.0&&WATER_REFLECTION_STRENGTH<=0.0)returnscene;',
                  'all(equal(blendState,ivec4(0)))||(blendState.x==770&&blendState.y==771)||(blendState.x==1&&blendState.y==0)',
                  'if(!supportedBlend)returnscene;',
                  'if(isnan(environment)||isinf(environment)||environment<=0.0)returnscene;',
                  'if(isnan(rainStrength)||isinf(rainStrength))returnscene;',
                  'if(any(isnan(lightmapUV))||any(isinf(lightmapUV)))returnscene;',
                  'clamp((lightmapUV-vec2(0.5/16.0))*(16.0/15.0),0.0,1.0)',
                  'if(skyAccess<=0.0)returnscene;',
                  'clamp(WATER_TINT_STRENGTH,0.0,1.0)*environment*skyAccess*(1.0-levels.x)',
                  'scene*mix(vec3(1.0),vec3(0.80,1.03,1.08),tintWeight)',
                  'clamp(WATER_REFLECTION_STRENGTH,0.0,1.0)*environment*skyAccess*clamp(SKY_BLEND,0.0,1.0)',
                  'any(isnan(normalView))||any(isinf(normalView))||any(isnan(viewPosition))||any(isinf(viewPosition))',
                  'if(normalScale<=1e-6||viewScale<=1e-6)returntinted;',
                  'vec3normal=celestialUnit(normalView);', 'vec3towardEye=celestialUnit(-viewPosition);',
                  'vec3reflected=reflect(-towardEye,normal);',
                  'smoothstep(0.5,0.95,dot(normal,up))', 'smoothstep(-0.10,0.0,dot(reflected,up))',
                  'reflectionWeight*=upwardSurface*aboveHorizon*waterFresnel(dot(normal,towardEye));',
                  'auroraSkyLinear(reflected,vanillaFog)',
                  'returnmix(tinted,reflectedSky,clamp(reflectionWeight,0.0,1.0));'):
        assert token in code,token
    assert code.index('if(waterSurface!=1)') < code.index('if(WATER_TINT_STRENGTH') < code.index('celestialEnvironmentWeight()')
    for forbidden in ('sampler','texture(','texelFetch(','depthtex','colortex','applyNightAurora','applyAtmosphericFog','applyLateAtmosphericFog'):
        assert forbidden not in code,forbidden
    assert 'pow(' not in body(source,'waterFresnel')
    assert vertex.count(WATER_VERTEX_DECL) == vertex.count(WATER_VERTEX_ASSIGN) == 1
    assert fragment.count(WATER_FRAGMENT_DECL) == fragment.count(WATER_CALL) == 1
    full_main = body(fragment,'main')
    assert full_main.index('discard;') < full_main.index('sceneFromDisplay(') < full_main.index('reconstructViewPosition(') < full_main.index('applyWaterStyle(') < full_main.index('applyLateAtmosphericFog(')
    assert full_main.count('applyWaterStyle(') == full_main.count('applyLateAtmosphericFog(') == 1
    assert 'color.a=' not in full_main
    # Capture flat interpolation explicitly; a plain type-only regex missed this.
    assert stage_variables('flat out int id;\n','out') == {'id':('int','flat')}
    assert stage_variables('in int id;\n','in') != {'id':('int','flat')}
    try:
        stage_variables('flat out int id;\nflat out int id;\n','out')
        raise AssertionError('Duplicate declaration was not rejected')
    except AssertionError as error:
        assert str(error).startswith('Duplicate stage variable:')
    for path in shaders.glob('*.vsh'):
        vs = preprocess(expand_without_foliage(path,shaders),0,False)
        fs = preprocess(expand(path.with_suffix('.fsh')),0,False)
        outputs,inputs = stage_variables(vs,'out'),stage_variables(fs,'in')
        for name,signature in inputs.items():
            assert outputs.get(name) == signature,(path.name,name)
        if path.stem == 'gbuffers_water':
            assert outputs['waterSurface'] == inputs['waterSurface'] == ('int','flat')
            assert inputs['normalView'] == ('vec3','smooth')
            assert stage_variables(vs,'in')['mc_Entity'] == ('vec2','smooth')
            assert body(vs,'main').count('waterSurface=') == 1
        else:
            assert 'waterSurface' not in inputs and 'waterSurface' not in outputs
            assert 'mc_Entity' not in vs and 'applyWaterStyle(' not in fs,path.stem
    for mode,style,sky_style,debug in product((0,1),(0,1),(0,1),range(7)):
        fs = preprocess(expand(shaders/'gbuffers_water.fsh'),debug,False,
                        overrides={'SCENE_COLOR_MODE':mode,'WATER_STYLE':style,'SKY_STYLE':sky_style,'WATER_SCREEN_REFLECTIONS':0})
        effect = body(fs,'applyWaterStyle')
        if not mode or not style or debug:
            assert effect == 'returnscene;'
        elif not sky_style:
            assert effect.endswith('returntinted;') and 'auroraSkyLinear(' not in effect
        assert body(fs,'main').count('applyLateAtmosphericFog(') == 1
    props,settings,labels = read('shaders.properties'),read('lib/water_settings.glsl'),read('lang/en_us.lang')
    for name,default in (('WATER_STYLE','1'),('WATER_TINT_STRENGTH','0.35'),('WATER_REFLECTION_STRENGTH','0.35')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',settings,re.M)
        assert name in props.split('screen.WATER =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    for material,render_type in product((-1,0,8,9,10,20,10000,10001,10002),(-1,0,1,2)):
        assert classified_water(material,render_type) == (material == 10001 and render_type == 1)
    values = [fresnel(i/1000) for i in range(1001)]
    assert fresnel(1) == .02 and fresnel(0) == 1
    assert all(math.isfinite(x) and .02 <= x <= 1 for x in values)
    assert all(b <= a for a,b in zip(values,values[1:]))
    assert fresnel(-1) == 1 and fresnel(2) == .02
    scene = (.1,.35,.6)
    cases = 0
    normals = ((0,1,0),(1,0,0),(0,-1,0),unit((.5,1,0)))
    positions = ((0,-1,0),(0,-.01,-1),(0,1,-1),(-1,-.5,-2))
    for normal,position,block,sky,environment,ts,rs in product(normals,positions,(0,.5,1),(0,.5,1),(0,.3,1),
            (0,.2,.35,.5,1),(0,.2,.35,.5,.75)):
        uv = ((block*15+.5)/16,(sky*15+.5)/16)
        options = dict(environment=environment,tint_strength=ts,reflection_strength=rs)
        tw,rw,direction = water_terms(position,normal,uv,**options)
        assert 0 <= tw <= 1 and 0 <= rw <= rs+1e-12
        result = water_result(scene,position,normal,uv,**options)
        assert all(math.isfinite(c) and 0 <= c <= max(base*1.08,reflection)+1e-12
                   for c,base,reflection in zip(result,scene,(.2,.45,.8)))
        if not sky or not environment or ts == rs == 0:
            assert result is scene
        if block == 1:
            assert tw == 0
        if direction is not None:
            assert abs(dot(direction,direction)-1) < 1e-12
        cases += 1
    # Sky-zero protects caves entirely; maximum block light protects tint only.
    assert water_result(scene,lightmap_uv=(15.5/16,.5/16)) is scene
    assert water_result(scene,lightmap_uv=(15.5/16,15.5/16),reflection_strength=0) is scene
    assert water_result(scene,lightmap_uv=(15.5/16,15.5/16),tint_strength=0) != scene
    assert water_result(scene,sky_style=0,reflection_strength=.75) == water_result(scene,reflection_strength=0)
    assert water_result(scene,sky_blend=0) == water_result(scene,reflection_strength=0)
    for options in ({'water_surface':0},{'water_surface':-1},{'style':0},{'mode':0},{'debug':5},
                    {'environment':0},{'environment':math.nan},{'environment':math.inf},
                    {'rain':math.nan},{'rain':math.inf},{'lightmap_uv':(math.nan,.5)},
                    {'blend':(0,0,1,0)},{'blend':(1,1,1,1)},{'blend':(770,1,1,1)},{'blend':(768,1,1,1)}):
        assert water_result(scene,**options) is scene
    assert water_result(scene,tint_strength=0,reflection_strength=0,normal=(math.nan,0,0)) is scene
    tinted = water_result(scene,reflection_strength=0)
    for invalid in ((0,0,0),(1e-30,0,0),(math.nan,0,0),(math.inf,0,0)):
        assert water_result(scene,normal=invalid) == tinted
        assert water_result(scene,view_position=invalid) == tinted
    assert close(water_result(scene,normal=(0,1e30,0),view_position=(0,-1e30,0)),water_result(scene))
    for blend in ((0,0,0,0),(770,771,1,0),(1,0,1,0)):
        assert water_result(scene,blend=blend) == water_result(scene)
    # True grazing remains strongly reflective; only the small below-horizon band fades.
    _,grazing,_ = water_terms((0,-.0001,-1),(0,1,0),(.5/16,15.5/16),reflection_strength=.75)
    assert grazing > .749
    assert smooth(-.1,0,0) == 1 and smooth(-.1,0,-.1) == 0
    assert abs(smooth(-.1,0,-.05)-.5) < 1e-12
    assert water_terms((0,-1,-1),(1,0,0),(.5/16,15.5/16))[1] == 0
    # Rotating N, V, up and reflected ray together preserves all directional terms.
    position,normal,up = (-2,-1,-4),unit((.1,1,.05)),(0,1,0)
    baseline = water_terms(position,normal,(.5/16,15.5/16),up=up)
    for yaw,pitch in product((-2,-.4,0,1.7),(-1,0,.8)):
        cy,sy,cp,sp = math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        rotation = ((cy,0,sy),(sp*sy,cp,-sp*cy),(-cp*sy,sp,cp*cy))
        rotate = lambda v: tuple(dot(row,v) for row in rotation)
        actual = water_terms(rotate(position),rotate(normal),(.5/16,15.5/16),up=rotate(up))
        assert close(actual[:2],baseline[:2]) and close(actual[2],rotate(baseline[2]))
    # Existing fog follows the styled source once. Native alpha then mixes that
    # source with the background; there is no alpha division or geometry displacement.
    styled = water_result(scene)
    atmosphere,background = (.3,.4,.5),(.8,.2,.1)
    for transmission,alpha in product((0,.2,.7,1),(0,.1,.5,1)):
        fogged = tuple(f+(c-f)*transmission for c,f in zip(styled,atmosphere))
        composed = tuple(alpha*c+(1-alpha)*b for c,b in zip(fogged,background))
        if alpha == 0:
            assert composed == background
        if alpha == 1:
            assert composed == fogged
        assert all(math.isfinite(c) for c in composed)
    print('PASS: M13 {} prior shader/property files pinned; water-only ID+fluid classification and flat interfaces'.format(pinned))
    print('PASS: M13 {} bounded water cases; Fresnel endpoints/monotonicity, horizon and camera invariance'.format(cases))
    print('PASS: M13 cave/tint torch protection, finite fallbacks, exact style/debug/legacy/non-water bypass')
    print('PASS: M13 source alpha/geometry retained, M7 analytic sky reflection and existing late fog exactly once')
    print('LIMIT: offline contracts/GLSL only; native water classification, appearance and performance require Iris runtime testing')
