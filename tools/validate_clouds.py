"""M12 native-cloud color/fog contracts. CPU references, not GPU rendering."""
import math
from validate_water_debug import restore_water_debug_source
import re
import subprocess
from functools import lru_cache
from itertools import product
from validate_water import restore_water_source

M11_BASELINE = 'b0f6e105a11b1c09e97ff3100cc58f8bed7c986a'
CLOUD_INCLUDE = '''#ifdef APPLY_CLOUD_ATMOSPHERE
#include "/lib/clouds.glsl"
#endif
'''
CLOUD_CALL = '''    // Cloud source color changes only after its original coverage/discard decision.
    color.rgb = applyCloudAtmosphere(color.rgb);
'''
CLOUD_PROPERTIES = '''
# M12 native cloud source styling and per-fragment fog; no cloud mesh replacement.
screen.CLOUDS = CLOUD_STYLE CLOUD_COLOR_STRENGTH CLOUD_FOG
screen.CLOUDS.columns = 2
'''


def restore_cloud_plumbing(source):
    assert source.count(CLOUD_CALL) <= 1
    return source.replace(CLOUD_CALL,'',1)


def restore_cloud_source(relative,source):
    """Strip only exact M12 hooks/options before all historical source pins."""
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_water_source(relative,source)
    if relative == 'gbuffers_clouds.fsh':
        assert source.count('#define APPLY_CLOUD_ATMOSPHERE\n') == 1
        source = source.replace('#define APPLY_CLOUD_ATMOSPHERE\n','',1)
    if relative == 'lib/geometry/textured_fragment.glsl':
        full_call = '#ifdef APPLY_CLOUD_ATMOSPHERE\n'+CLOUD_CALL+'#endif\n'
        assert source.count(CLOUD_INCLUDE) == source.count(full_call) == 1
        source = source.replace(CLOUD_INCLUDE,'',1).replace(full_call,'',1)
    if relative == 'shaders.properties':
        assert source.endswith(CLOUD_PROPERTIES)
        assert source.count('screen = [CLOUDS] ') == source.count('sliders = CLOUD_COLOR_STRENGTH ') == 1
        source = source[:-len(CLOUD_PROPERTIES)].replace('screen = [CLOUDS] ','screen = ',1).replace(
            'sliders = CLOUD_COLOR_STRENGTH ','sliders = ',1)
    return source


def clamp(x):
    return min(1.0,max(0.0,x))


def smooth(a,b,x):
    t = clamp((x-a)/(b-a))
    return t*t*(3-2*t)


def mix(a,b,t):
    return tuple(x+(y-x)*t for x,y in zip(a,b))


def cloud_palette(elevation,rain=0):
    day = smooth(-.10,.16,elevation)
    twilight = smooth(-.18,-.04,elevation)*(1-smooth(.08,.35,elevation))
    tint = mix(mix((.55,.65,1.05),(1.02,1,.96),day),(1.15,.72,.50),twilight)
    return mix(tint,(1,1,1),.8*clamp(rain))


def supported_cloud_blend(blend):
    return tuple(blend) == (0,0,0,0) or tuple(blend[:2]) in ((770,771),(1,0))


def cloud_result(scene,elevation=-.5,rain=0,strength=.6,environment=1,
                 blend=(770,771,1,0),cloud_fog=True,global_fog=True,
                 transmission=.5,atmosphere=(.3,.4,.5),style=1,mode=1,debug=0):
    if not style or not mode or debug or not supported_cloud_blend(blend):
        return scene
    if not math.isfinite(environment) or environment <= 0 or not math.isfinite(rain):
        return scene
    weight = clamp(strength)*environment
    tinted = scene if weight <= 0 else tuple(c*t for c,t in zip(scene,mix((1,1,1),cloud_palette(elevation,rain),weight)))
    if not cloud_fog or not global_fog or transmission >= 1:
        return tinted
    return mix(atmosphere,tinted,transmission)


def close(a,b,tolerance=1e-11):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def validate_clouds(root,expand,preprocess,compact,function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M11_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files = subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',
                                        M11_BASELINE,'shaders']).decode().splitlines()
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh')) or relative == 'shaders.properties':
            assert restore_cloud_source(relative,read(relative)) == prior(relative),relative
            pinned += 1
    # Exact M11 restoration preserves native texture/vertex shading, alpha/discard,
    # all MRT layouts, allocation/flip rules, shadow logic, and the M9 fog functions.
    assert len(list(shaders.glob('*.vsh'))) == len(list(shaders.glob('*.fsh'))) == 24
    assert restore_water_debug_source('lang/en_us.lang',read('lang/en_us.lang')).startswith(prior('lang/en_us.lang'))
    fragment = read('lib/geometry/textured_fragment.glsl')
    assert fragment.count(CLOUD_CALL) == fragment.count(CLOUD_INCLUDE) == 1
    assert fragment.index('discard;') < fragment.index('sceneFromDisplay(color.rgb)') < fragment.index('applyCloudAtmosphere(color.rgb)')
    source = read('lib/clouds.glsl')
    code = compact(source)
    for token in ('vec2phases=celestialPhases();', 'vec3night=vec3(0.55,0.65,1.05);',
                  'vec3day=vec3(1.02,1.0,0.96);','vec3twilight=vec3(1.15,0.72,0.50);',
                  'mix(mix(night,day,phases.x),twilight,phases.y)',
                  'mix(tint,vec3(1.0),0.8*clamp(rainStrength,0.0,1.0))',
                  'all(equal(blendFunc,ivec4(0)))||(blendFunc.x==770&&blendFunc.y==771)||(blendFunc.x==1&&blendFunc.y==0)',
                  'if(!supportedBlend)returnscene;', 'floatenvironment=celestialEnvironmentWeight();',
                  'if(isnan(environment)||isinf(environment)||environment<=0.0)returnscene;',
                  'if(isnan(rainStrength)||isinf(rainStrength))returnscene;',
                  'clamp(CLOUD_COLOR_STRENGTH,0.0,1.0)*environment',
                  'vec3tinted=scene;if(weight>0.0)tinted=scene*mix(vec3(1.0),cloudColorTint(),weight);',
                  'vec2uv=gl_FragCoord.xy/vec2(viewWidth,viewHeight);',
                  'vec3viewPosition=reconstructViewPosition(uv,gl_FragCoord.z);',
                  'returnapplyAtmosphericFog(tinted,viewPosition);'):
        assert token in code,token
    assert code.index('if(!supportedBlend)returnscene;') < code.index('vec3tinted=scene;')
    assert body(source,'applyCloudAtmosphere').count('applyAtmosphericFog(') == 1
    assert 'applyLateAtmosphericFog' not in code
    assert 'depthtex' not in code and 'colortex' not in code
    for path in shaders.glob('*.fsh'):
        expanded = expand(path)
        assert ('#define APPLY_CLOUD_ATMOSPHERE' in expanded) == (path.stem == 'gbuffers_clouds')
        selected = preprocess(expanded,0,False)
        assert ('applyCloudAtmosphere(' in selected) == (path.stem == 'gbuffers_clouds'),path.name
    expanded = expand(shaders/'gbuffers_clouds.fsh')
    assert 'applyNightAurora' not in expanded and 'auroraRibbonLight' not in expanded
    for mode,style,cloud_fog,global_fog,debug in product((0,1),(0,1),(0,1),(0,1),range(7)):
        selected = preprocess(expanded,debug,False,overrides={'SCENE_COLOR_MODE':mode,'CLOUD_STYLE':style,
                               'CLOUD_FOG':cloud_fog,'FOG_ENABLED':global_fog})
        effect = body(selected,'applyCloudAtmosphere')
        if not mode or not style or debug:
            assert effect == 'returnscene;'
        elif not cloud_fog or not global_fog:
            assert effect.endswith('returntinted;')
            assert 'reconstructViewPosition' not in effect and 'applyAtmosphericFog' not in effect
        else:
            assert effect.count('applyAtmosphericFog(') == 1
        assert body(selected,'main').count('applyCloudAtmosphere(') == 1
        declarations = re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(declarations) == len(set(declarations))
        assert 'color.a=' not in body(selected,'main')
    props,settings,labels = read('shaders.properties'),read('lib/cloud_settings.glsl'),read('lang/en_us.lang')
    for name,default in (('CLOUD_STYLE','1'),('CLOUD_COLOR_STRENGTH','0.6'),('CLOUD_FOG','1')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',settings,re.M)
        assert name in props.split('screen.CLOUDS =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    assert cloud_palette(-1) == (.55,.65,1.05)
    assert close(cloud_palette(1),(1.02,1,.96))
    assert close(cloud_palette(0),(1.15,.72,.50))
    cases = 0
    for elevation,rain,strength,environment,scene in product(
            (-1,-.18,-.10,-.04,0,.08,.16,.35,1),(0,.25,.5,1),(0,.3,.6,1),(0,.25,1),
            ((0,0,0),(.1,.1,.1),(1,1,1),(.1,.4,.8),(2,4,16))):
        tint = cloud_palette(elevation,rain)
        assert all(math.isfinite(c) and .5-1e-12 <= c <= 1.15+1e-12 for c in tint)
        result = cloud_result(scene,elevation,rain,strength,environment,cloud_fog=False)
        assert all(math.isfinite(c) and .5*x-1e-12 <= c <= 1.15*x+1e-12 for c,x in zip(result,scene))
        if not strength or not environment:
            assert result is scene
        if scene == (0,0,0):
            assert result == scene
        cases += 1
    for elevation in (-1,0,1):
        clear,rainy = cloud_palette(elevation,0),cloud_palette(elevation,1)
        assert close(tuple(c-1 for c in rainy),tuple((c-1)*.2 for c in clear))
    # Rain and day/night changes are continuous, including palette phase joins.
    for boundary in (-.18,-.10,-.04,.08,.16,.35):
        assert close(cloud_palette(boundary-1e-7),cloud_palette(boundary+1e-7),3e-6)
    scene,atmosphere,background = (.2,.5,.9),(.3,.4,.6),(.8,.1,.2)
    accepted = ((0,0,0,0),(770,771,1,0),(770,771,770,771),(1,0,1,0))
    for blend in accepted:
        assert supported_cloud_blend(blend)
    for blend in ((0,0,1,0),(0,0,770,771),(1,1,1,1),(770,1,1,1),(768,1,1,1),(774,771,1,0)):
        assert not supported_cloud_blend(blend)
        assert cloud_result(scene,blend=blend) is scene
    for option in ({'style':0},{'mode':0},{'debug':1},{'environment':0},{'environment':math.nan},
                   {'environment':math.inf},{'rain':math.nan},{'rain':math.inf}):
        assert cloud_result(scene,**option) is scene
    for transmission,blend in product((0,.2,.7,1),accepted):
        tinted = cloud_result(scene,cloud_fog=False,blend=blend)
        fogged = cloud_result(scene,blend=blend,transmission=transmission,atmosphere=atmosphere)
        assert close(fogged,mix(atmosphere,tinted,transmission))
        # Tint zero does not disable fog; either fog switch only disables fog.
        untinted = cloud_result(scene,strength=0,blend=blend,transmission=transmission,atmosphere=atmosphere)
        assert close(untinted,mix(atmosphere,scene,transmission))
        assert cloud_result(scene,strength=0,cloud_fog=False,blend=blend) is scene
        assert cloud_result(scene,strength=0,global_fog=False,blend=blend) is scene
        for alpha in (0,.1,.5,1):
            # Native disabled/ONE-ZERO blending replaces RGB. Ordinary alpha
            # blends the fogged foreground once with the already-fogged background.
            coverage = alpha if blend[:2] == (770,771) else 1.0
            result = tuple(coverage*c+(1-coverage)*b for c,b in zip(fogged,background))
            if coverage == 1:
                assert result == fogged
            if blend[:2] != (770,771):
                continue
            if alpha == 0:
                assert result == background
            if alpha == 1:
                assert result == fogged
            assert close(result,tuple(alpha*transmission*c+alpha*(1-transmission)*f+(1-alpha)*b
                                      for c,f,b in zip(tinted,atmosphere,background)))
    # Perspective round trip at the current fragment's own depth (not opaque depth).
    for near,far,position in product((.05,.1),(256,1024),((1,2,-8),(-15,20,-128),(80,130,-400))):
        a,b = -(far+near)/(far-near),-2*far*near/(far-near)
        x,y,z = position
        ndc = (1.3*x/-z,1.7*y/-z,(a*z+b)/-z)
        uv = (ndc[0]*.5+.5,ndc[1]*.5+.5)
        depth = ndc[2]*.5+.5
        recovered_z = -b/((2*depth-1)+a)
        recovered = ((2*uv[0]-1)*(-recovered_z)/1.3,(2*uv[1]-1)*(-recovered_z)/1.7,recovered_z)
        assert close(recovered,position,1e-8)
    print('PASS: M12 {} prior shader/property files pinned; cloud-only RGB hook, native alpha/geometry preserved'.format(pinned))
    print('PASS: M12 {} bounded palette cases; continuous phases, rain neutralization and tint/fog independence'.format(cases))
    print('PASS: M12 disabled/ordinary blend support, unsupported bypass, per-fragment depth and single foreground fog')
    print('PASS: M12 exact legacy/debug/environment/style bypass; no aurora in cloud fog')
    print('LIMIT: offline source/CPU contracts only; native Fast/Fancy cloud rendering still requires Iris runtime validation')
