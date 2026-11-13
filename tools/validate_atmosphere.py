"""M7 read-only contracts, invoked by tools/validate.py. No GPU execution."""
import math
import re
import subprocess
from validate_fog import historical_source, restore_fog_plumbing
from itertools import product

M6_BASELINE = "5479a1c3b2b579e965cdb43681422abcb45b6b79"


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def smooth(a, b, x):
    t = clamp((x-a)/(b-a))
    return t*t*(3-2*t)


def mix(a, b, t):
    return tuple(x+(y-x)*t for x, y in zip(a, b))


def decode(c):
    c = max(c, 0.0)
    return c/12.92 if c < .04045 else ((c+.055)/1.055)**2.4


def encode(c):
    c = max(c, 0.0)
    return 12.92*c if c < .0031308 else 1.055*c**(1/2.4)-.055


def phases(elevation):
    return (smooth(-.10, .16, elevation),
            smooth(-.18, -.04, elevation)*(1-smooth(.08, .35, elevation)))


def unit(v):
    if not all(math.isfinite(x) for x in v):
        return (0.0, 1.0, 0.0)
    scale = max(abs(x) for x in v)
    if scale <= 1e-6:
        return (0.0, 1.0, 0.0)
    v = tuple(x/scale for x in v)
    length = math.sqrt(sum(x*x for x in v))
    return tuple(x/length for x in v)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def rotate(v, yaw, pitch):
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = c*v[0]+s*v[2], v[1], -s*v[0]+c*v[2]
    c, s = math.cos(pitch), math.sin(pitch)
    return (x, c*y-s*z, s*y+c*z)


def environment(skylight=True, ceiling=False, fluid=0, blindness=0, darkness=0):
    return 0.0 if not skylight or ceiling or fluid else 1-clamp(max(blindness, darkness))


def reference_sky(elevation, height, facing, fog, rain, night_brightness, warmth):
    day_weight, twilight_weight = phases(elevation)
    horizon = (1-clamp(height))**3
    def linear(rgb):
        return tuple(decode(c) for c in rgb)
    night = tuple(c*night_brightness for c in mix(linear((.035,.045,.12)), linear((.12,.16,.30)), horizon))
    day = mix(linear((.12,.38,.82)), linear((.53,.75,.95)), horizon)
    twilight = mix(linear((.17,.09,.35)), linear((.68,.30,.48)), horizon)
    twilight = mix(twilight, linear((1,.56,.18)), clamp(horizon*max(facing,0)**4*warmth))
    result = mix(mix(night, day, day_weight), twilight, twilight_weight)
    fog_linear = linear(tuple(clamp(c) for c in fog))
    result = mix(result, fog_linear, .22*horizon*horizon)
    overcast = tuple(c*(.4+.6*day_weight) for c in fog_linear)
    return tuple(clamp(c) for c in mix(result, overcast, .85*clamp(rain)))


def palette_tint(elevation, rain, ndotl, visibility, ambient=.65, direct=.55):
    day, twilight = phases(elevation)
    a = mix(mix((.56,.68,1), (.78,.88,1), day), (.76,.65,.95), twilight)
    d = mix(mix((.58,.78,1), (1,.94,.82), day), (1,.66,.38), twilight)
    a = mix(a, (.86,.90,.96), .75*clamp(rain))
    d = mix(d, (.94,.95,.98), .75*clamp(rain))
    amount = direct*ndotl*visibility
    return tuple((ambient*x+amount*y)/max(ambient+amount,1e-6) for x,y in zip(a,d))


def apply_tint(scene, tint, block, sky, strength=.6, lighting=1, env=1):
    weight = clamp(strength*lighting*clamp(sky)*(1-clamp(block)))*env
    if weight <= 0:
        return scene
    return tuple(encode(decode(c)*t) for c,t in zip(scene, mix((1,1,1),tint,weight)))


def validate_atmosphere(root, expand, preprocess, compact, function_body):
    shaders = root / 'shaders'
    def read(relative):
        return historical_source(relative, (shaders/relative).read_text(encoding='utf-8'))
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M6_BASELINE+':shaders/'+relative]).decode()
    settings = read('lib/atmosphere_settings.glsl')
    celestial = read('lib/celestial.glsl')
    sky = read('lib/sky_palette.glsl')
    light = read('lib/celestial_lighting.glsl')
    color = read('lib/color_space.glsl')
    geometry = read('lib/geometry/sky_fragment.glsl')
    # Preserve full sensitive implementations, not just selected expressions.
    for relative in ('lib/lighting.glsl','lib/settings.glsl',
                     'lib/shadow.glsl','lib/shadow_bias.glsl','lib/shadow_settings.glsl',
                     'lib/position.glsl','lib/gbuffer_write.glsl',
                     'shadow.vsh','shadow.fsh','gbuffers_skytextured.vsh','gbuffers_skytextured.fsh',
                     'lib/geometry/textured_vertex.glsl'):
        assert read(relative).replace('\r\n','\n') == prior(relative).replace('\r\n','\n'), relative
    for function in ('fogify','calcSkyColor','screenToView'):
        assert compact(function_body(geometry,function)) == compact(function_body(prior('lib/geometry/sky_fragment.glsl'),function))
    restored = read('deferred.fsh').replace('#include "/lib/celestial_lighting.glsl"\n','').replace(
        '        color.rgb = applyCelestialPalette(color.rgb, normalView, levels, visibility);\n','')
    assert compact(restored) == compact(prior('deferred.fsh'))
    assert 'if(renderStage==MC_RENDER_STAGE_STARS){color=vec4(sceneFromDisplay(glcolor.rgb),glcolor.a);}' in compact(geometry)
    assert 'floatvoidWeight=clamp(SKY_BLEND,0.0,1.0)*celestialEnvironmentWeight();' in compact(geometry)
    assert 'color=mix(vec4(calcSkyColor(normalize(pos)),1.0),glcolor,voidWeight);' in compact(geometry)
    # Disabled branches return the original color before any transfer functions.
    for style, palette in product((0,1), repeat=2):
        overrides = {'SKY_STYLE':style, 'LIGHT_PALETTE':palette, 'SCENE_COLOR_MODE':0}
        sky_source = preprocess(expand(shaders/'gbuffers_skybasic.fsh'),0,False,overrides=overrides)
        deferred_source = preprocess(expand(shaders/'deferred.fsh'),0,False,overrides=overrides)
        if style == 0:
            assert compact(function_body(sky_source,'sceneFromDisplay')) == 'returndisplayColor;'
            assert compact(function_body(sky_source,'applyAuroraSky')) == 'returnsceneFromDisplay(baseline);'
            old_main = compact(function_body(prior('lib/geometry/sky_fragment.glsl'),'main'))
            new_main = compact(function_body(sky_source,'main')).replace(
                'applyAuroraSky(normalize(pos),calcSkyColor(normalize(pos)),fogColor)', 'calcSkyColor(normalize(pos))').replace(
                'vec4(sceneFromDisplay(glcolor.rgb),glcolor.a)', 'glcolor')
            assert new_main == old_main
        if palette == 0:
            assert compact(function_body(deferred_source,'applyCelestialPalette')) == 'returnlitScene;'
    # Tie mathematical tests below to actual GLSL constants/operations.
    for token in ('smoothstep(-0.10,0.16,elevation)', 'smoothstep(-0.18,-0.04,elevation)',
                  '1.0-smoothstep(0.08,0.35,elevation)',
                  'dot(celestialUnit(sunPosition),celestialUnit(upPosition))',
                  '!hasSkylight||hasCeiling||isEyeInWater!=0', 'max(blindness,darknessFactor)',
                  'any(isnan(direction))', 'any(isinf(direction))', 'normalize(direction/scale)'):
        assert token in compact(celestial), token
    assert 'shadowLightPosition' not in re.sub(r'//[^\n]*','',celestial)
    for token in ('horizon*pow(towardSun,4.0)*SUNSET_GLOW', '0.22*horizon*horizon',
                  '0.85*phases.z', 'if(weight<=0.0)returnsceneFromDisplay(baseline);'):
        assert token in compact(sky), token
    for token in ('DIRECT_LIGHT*diffuseTerm(normalView)*visibility',
                  'AMBIENT_LIGHT*ambient+directAmount*direct',
                  'if(weight<=0.0)returnlitScene;', 'LIGHT_PALETTE_STRENGTH*LIGHTING_STRENGTH*skyWeight'):
        assert token in compact(light), token
    for token in ('c/12.92','vec3(2.4)','vec3(0.04045)','vec3(0.0031308)','vec3(1.0/2.4)'):
        assert token in compact(color), token
    # Transfer endpoints, reference middle gray, monotonicity and round trips.
    assert decode(0) == encode(0) == 0
    assert abs(decode(1)-1) < 1e-12 and abs(encode(1)-1) < 1e-12
    assert abs(decode(.5)-.21404114048223255) < 1e-12
    assert all(decode(i/1000) < decode((i+1)/1000) for i in range(1000))
    for value in [i/1000 for i in range(1001)] + [.04045, .0031308, 1.2, 2.0]:
        assert abs(encode(decode(value))-value) < 3e-8
    # Smooth transitions are bounded, continuous and day weight is monotone.
    samples = [phases(-1+i/10000) for i in range(20001)]
    assert samples[0] == (0,0) and samples[-1] == (1,0)
    assert phases(0)[1] == 1
    assert all(0 <= x <= 1 for pair in samples for x in pair)
    assert all(b[0] >= a[0] for a,b in zip(samples,samples[1:]))
    assert max(abs(b[i]-a[i]) for a,b in zip(samples,samples[1:]) for i in (0,1)) < .0011
    for boundary in (-.18,-.10,-.04,.08,.16,.35):
        assert max(abs(x-y) for x,y in zip(phases(boundary-1e-7), phases(boundary+1e-7))) < 3e-6
    # Both direction terms remain unchanged by rotating the camera together.
    for sun, ray, yaw, pitch in product(((1,0,0),(1,.1,2),(1,-1,0),(0,1,0)),
                                       ((0,1,0),(1,0,0),(1,-.1,1)),(-2,-.5,0,1.5),(-1,0,.8)):
        up=(0,1,0)
        for a,b in ((sun,up),(ray,up),(ray,sun)):
            assert abs(dot(unit(a),unit(b))-dot(unit(rotate(a,yaw,pitch)),unit(rotate(b,yaw,pitch)))) < 1e-12
    for v in ((0,0,0),(1e-10,0,0),(1e300,-1e300,1e300),(math.inf,0,1),(math.nan,0,0)):
        assert all(math.isfinite(x) for x in unit(v))
        assert abs(dot(unit(v),unit(v))-1) < 1e-12
    assert environment() == 1
    for conditions in ({'skylight':False},{'ceiling':True},{'fluid':1},{'fluid':2},{'fluid':3},
                       {'blindness':1},{'darkness':1}):
        assert environment(**conditions) == 0
    assert environment(blindness=.25,darkness=.6) == .4
    # Void RGB/alpha follows the same continuous weight, including vision effects.
    baseline_void=(.2,.3,.4,1.0)
    native_void=(.01,.02,.03,.8)
    for blend,vision in product((0,.25,1),(0,.4,1)):
        weight=clamp(blend)*environment(blindness=vision)
        result=mix(baseline_void,native_void,weight)
        assert all(min(a,b) <= x <= max(a,b) for x,a,b in zip(result,baseline_void,native_void))
        if blend == 0 or vision == 1:
            assert result == baseline_void
        if blend == 1 and vision == 0:
            assert all(abs(a-b) < 1e-12 for a,b in zip(result,native_void))
    # All exposed sky control values and extreme rain/fog/direction inputs.
    sky_cases=0
    for elevation,height,facing,fog,rain,night,warmth in product(
            (-1,-.18,-.04,0,.16,.35,1),(-1,0,.2,1),(-1,0,.5,1),
            ((0,0,0),(.3,.5,.8),(1,1,1)),(0,.5,1),(.5,.75,1,1.5,2),(0,.5,1,1.5)):
        result=reference_sky(elevation,height,facing,fog,rain,night,warmth)
        assert all(math.isfinite(c) and 0 <= c <= 1 for c in result)
        sky_cases += 1
    # Facing the low sun raises the red/blue ratio relative to the opposite horizon.
    warm=reference_sky(0,0,1,(.3,.3,.3),0,1,1)
    cool=reference_sky(0,0,-1,(.3,.3,.3),0,1,1)
    assert warm[0]/warm[2] > cool[0]/cool[2]
    # Sunset control has no effect at full noon/night; below horizon remains finite.
    for elevation in (-1,1):
        assert reference_sky(elevation,0,1,(.3,.4,.5),0,1,0) == reference_sky(elevation,0,1,(.3,.4,.5),0,1,1.5)
    # Direct visibility does not remove ambient tint; closed shadows ignore NdotL.
    for elevation,rain,visibility in product((-1,0,1),(0,.5,1),(0,.25,1)):
        tint=palette_tint(elevation,rain,.7,visibility)
        assert all(0 < c <= 1+1e-12 for c in tint)
        assert palette_tint(elevation,rain,0,0) == palette_tint(elevation,rain,1,0)
        scene=(.15,.55,.95)
        for block,sky,strength,lighting,env in ((0,0,.6,1,1),(1,1,.6,1,1),(0,1,0,1,1),
                                                (0,1,.6,0,1),(0,1,.6,1,0)):
            assert apply_tint(scene,tint,block,sky,strength,lighting,env) == scene
        for strength in (0,.25,.5,.6,.75,1):
            assert apply_tint((0,0,0),tint,0,1,strength) == (0,0,0)
            result=apply_tint(scene,tint,0,1,strength)
            assert all(0 < out <= before+1e-12 for out,before in zip(result,scene))
    props=read('shaders.properties')
    labels=read('lang/en_us.lang')
    for name,default in (('SKY_STYLE','1'),('SKY_BLEND','1.0'),('SUNSET_GLOW','1.0'),
                         ('NIGHT_BRIGHTNESS','1.0'),('LIGHT_PALETTE','1'),('LIGHT_PALETTE_STRENGTH','0.6')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',settings,re.M)
        assert name in props.split('screen.ATMOSPHERE =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    assert 'value.SKY_STYLE.0=Base-330' in labels and 'value.SKY_STYLE.1=Aurora Fantasy' in labels
    assert 'value.LIGHT_PALETTE.0=Neutral M6' in labels and 'value.LIGHT_PALETTE.1=Aurora' in labels
    print('PASS: M7 opt-out in legacy pipeline restores M6 sky/lighting; unchanged shadow/data paths pinned')
    print('PASS: M7 sRGB transfer, continuous day/twilight weights, camera invariance and environment fallbacks')
    print('PASS: M7 {} bounded sky cases; directional twilight and cave/block/ambient protection'.format(sky_cases))
    print('PASS: M7 nested option screens, defaults and language labels')
    print('LIMIT: static structural/numerical validation is NOT Minecraft/Iris/GPU runtime validation')
