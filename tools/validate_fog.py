"""M9 read-only fog contracts and narrow adapters for historical source pins.

Numerical references check invariants independently of a GPU; GLSL source
contracts connect those references to the shader. No runtime claims are made.
"""
import math
import re
import subprocess
from functools import lru_cache
from itertools import product
from validate_bloom import BLOOM_PROGRAMS, restore_bloom_properties
from validate_aurora import restore_aurora_source
from validate_water import restore_water_plumbing, restore_water_source

M8_BASELINE = '7ac62da5bada1ab0fd0eb6c66cb27222d6ed3586'
GUARDED = ('pipeline_settings', 'color_space', 'scene_color', 'atmosphere_settings',
           'celestial', 'sky_palette', 'position')
LATE_PROGRAMS = ('gbuffers_water', 'gbuffers_weather', 'gbuffers_textured', 'gbuffers_textured_lit')
DEFERRED_FOG = '''        // Fog is added AFTER direct/ambient lighting, so shadows cannot darken its color.
        float surfaceDepth = texelFetch(depthtex1, pixel, 0).r;
        if (surfaceDepth < 1.0) {
            vec2 screenUV = (vec2(pixel) + 0.5) / vec2(textureSize(depthtex1, 0));
            color.rgb = applyAtmosphericFog(color.rgb, reconstructViewPosition(screenUV, surfaceDepth));
        }
'''
LATE_INCLUDE = '''#ifdef APPLY_LATE_FOG
#include "/lib/fog.glsl"
#endif
'''
LATE_FOG = '''    // Reconstruct this foreground fragment, not the already composed background.
    vec2 fogUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 fogView = reconstructViewPosition(fogUV, gl_FragCoord.z);
    color.rgb = applyLateAtmosphericFog(color.rgb, fogView);
'''
FOG_PROPERTIES = '''
# M9 fog scope depends on particles being drawn after deferred lighting.
particles.ordering = after
screen.FOG = FOG_ENABLED FOG_DENSITY FOG_START FOG_BASE_HEIGHT FOG_HEIGHT_FALLOFF FOG_RAIN_BOOST
screen.FOG.columns = 2
'''


def remove_once(source, fragment):
    assert source.count(fragment) <= 1, 'Duplicated M9 plumbing'
    return source.replace(fragment, '', 1)


def restore_fog_plumbing(source):
    """Remove only the exact two M9 call sites from preprocessed historical checks."""
    return remove_once(remove_once(restore_water_plumbing(source), DEFERRED_FOG), LATE_FOG)


def historical_source(relative, source):
    """Keep all prior checks; unwrap precisely whitelisted M9 additions only."""
    relative = relative.replace('\\', '/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_aurora_source(relative, source.replace('\r\n', '\n'))
    for name in GUARDED:
        if relative == 'lib/' + name + '.glsl':
            guard = 'AURORA_' + name.upper() + '_INCLUDED'
            prefix = '#ifndef ' + guard + '\n#define ' + guard + '\n'
            assert source.startswith(prefix) and source.endswith('#endif\n'), relative
            source = source[len(prefix):-len('#endif\n')]
    if relative == 'deferred.fsh':
        source = remove_once(source, '#include "/lib/fog.glsl"\n')
        source = remove_once(source, DEFERRED_FOG)
    if relative == 'lib/geometry/lit_fragment.glsl':
        source = remove_once(source, LATE_INCLUDE)
        source = remove_once(source, '#ifdef APPLY_LATE_FOG\n' + LATE_FOG + '#endif\n')
    if relative in tuple(name + '.fsh' for name in LATE_PROGRAMS):
        source = remove_once(source, '#define APPLY_LATE_FOG\n')
    if relative == 'shaders.properties':
        source = restore_bloom_properties(source)
        assert source.endswith(FOG_PROPERTIES)
        source = source[:-len(FOG_PROPERTIES)]
        source = source.replace('screen = [FOG] ', 'screen = ', 1).replace(
            'sliders = FOG_DENSITY FOG_START FOG_BASE_HEIGHT FOG_HEIGHT_FALLOFF FOG_RAIN_BOOST ',
            'sliders = ', 1)
    return source


def clamp(x, lo=0.0, hi=1.0):
    return min(hi, max(lo, x))


def density_at(height, base=64.0, falloff=64.0):
    return math.exp(-max(height-base, 0.0)/max(falloff, 1.0))


def segment_density(origin, end, distance, start, base=64.0, falloff=64.0):
    first = origin + (end-origin)*start/distance
    middle = (first+end)*.5
    return (density_at(first, base, falloff) + 4*density_at(middle, base, falloff)
            + density_at(end, base, falloff))/6


def transmission(distance, origin=64.0, end=64.0, density=.006, start=24.0,
                 base=64.0, falloff=64.0, rain=0.0, boost=1.0, environment=1.0):
    if not all(math.isfinite(x) for x in (distance, origin, end)):
        return 1.0
    start = max(start, 0.0)
    if distance <= start or density <= 0.0 or environment <= 0.0:
        return 1.0
    mean = segment_density(origin, end, distance, start, base, falloff)
    depth = max(density, 0.0)*(distance-start)*mean*(1+max(boost, 0.0)*clamp(rain))*environment
    return math.exp(-clamp(depth, 0.0, 80.0))


def environment_weight(skylight=True, ceiling=False, fluid=0, blindness=0.0,
                       darkness=0.0, eye_sky=240):
    if not skylight or ceiling or fluid:
        return 0.0
    t = clamp(clamp(eye_sky/240.0)/.5)
    return (1-clamp(max(blindness, darkness)))*t*t*(3-2*t)


def fog_color(scene, atmosphere, t):
    return tuple(t*c+(1-t)*f for c, f in zip(scene, atmosphere))


def late_color(scene, atmosphere, t, blend):
    if blend in ((770, 771), (1, 0)):
        return fog_color(scene, atmosphere, t)
    if blend in ((1, 1), (770, 1)):
        return tuple(c*t for c in scene)
    if blend == (768, 1):
        return tuple(c*math.sqrt(t) for c in scene)
    return scene


def close(a, b, tolerance=1e-11):
    return all(abs(x-y) <= tolerance for x, y in zip(a, b))


def validate_fog(root, expand, preprocess, compact, function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git', '-C', str(root), 'show',
                                       M8_BASELINE+':shaders/'+relative]).decode().replace('\r\n', '\n')
    def body(source, name):
        return compact(function_body(source, name))
    # Every old shader/program/property file is preserved after removing exact
    # intentional M9 plumbing. New language labels have separate checks below.
    old_files = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only',
                                        M8_BASELINE, 'shaders']).decode().splitlines()
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl', '.vsh', '.fsh')) or relative == 'shaders.properties':
            assert historical_source(relative, read(relative)) == prior(relative), relative
            pinned += 1
    for extension in ('vsh','fsh'):
        programs = list(shaders.glob('*.'+extension))
        assert len(programs) == 24
        assert len([p for p in programs if p.stem not in BLOOM_PROGRAMS]) == 20
    fog = read('lib/fog.glsl')
    fog_compact = compact(fog)
    for token in (
            'exp(-max(worldY-FOG_BASE_HEIGHT,0.0)/max(FOG_HEIGHT_FALLOFF,1.0))',
            'if(any(isnan(viewPosition))||any(isinf(viewPosition)))return1.0;',
            'if(isnan(rayLength)||isinf(rayLength))return1.0;',
            'if(isnan(originY)||isinf(originY)||isnan(endY)||isinf(endY))return1.0;',
            'if(rayLength<=start||FOG_DENSITY<=0.0)return1.0;',
            'smoothstep(0.0,0.5,clamp(float(eyeBrightnessSmooth.y)/240.0,0.0,1.0))',
            'celestialEnvironmentWeight()*skyAccess', 'if(environment<=0.0)return1.0;',
            'floatanchorY=float(cameraPositionInt.y)+cameraPositionFract.y;',
            'floatoriginY=anchorY+gbufferModelViewInverse[3].y;',
            'floatendY=anchorY+viewToPlayerPosition(viewPosition).y;',
            'floatstartY=mix(originY,endY,start/rayLength);',
            '(fogHeightDensity(startY)+4.0*fogHeightDensity(middleY)+fogHeightDensity(endY))/6.0',
            '1.0+max(FOG_RAIN_BOOST,0.0)*clamp(rainStrength,0.0,1.0)',
            'max(FOG_DENSITY,0.0)*(rayLength-start)*averageDensity*weather*environment',
            'returnexp(-clamp(opticalDepth,0.0,80.0));',
            'applyAuroraSky(celestialUnit(viewPosition),fogColor,fogColor)',
            'returnmix(atmosphere,scene,transmission);',
            '(blendFunc.x==770&&blendFunc.y==771)||(blendFunc.x==1&&blendFunc.y==0)',
            'blendFunc.y==1&&(blendFunc.x==1||blendFunc.x==770)',
            'blendFunc.x==768&&blendFunc.y==1', 'returnscene*sqrt(transmission);'):
        assert token in fog_compact, token
    assert 'shadow' not in compact(function_body(fog, 'applyAtmosphericFog')).lower()
    assert 'returnscene;' == body(preprocess(expand(shaders/'deferred.fsh'), 0, False,
                                            overrides={'FOG_ENABLED':0}), 'applyAtmosphericFog')
    deferred = read('deferred.fsh')
    assert deferred.count(DEFERRED_FOG) == 1
    main = body(deferred, 'main')
    assert main.index('if(surface.a>0.5)') < main.index('lightScene(') < main.index('applyCelestialPalette(') < main.index('applyAtmosphericFog(')
    assert 'if(surfaceDepth<1.0){vec2screenUV=' in main
    assert main.count('applyAtmosphericFog(') == 1
    lit = restore_water_source('lib/geometry/lit_fragment.glsl', read('lib/geometry/lit_fragment.glsl'))
    assert lit.count(LATE_INCLUDE) == lit.count(LATE_FOG) == 1
    assert lit.index('discard;') < lit.index('sceneFromDisplay(color.rgb)') < lit.index('applyLateAtmosphericFog(color.rgb,fogView)'.replace(',', ', '))
    # Every active fragment contains one copy of each guarded declaration/function.
    # This catches the duplicate include problem rather than merely balancing guards.
    for mode, enabled in product((0, 1), repeat=2):
        for path in sorted(shaders.glob('*.fsh')):
            source = preprocess(expand(path), 0, False,
                                overrides={'SCENE_COLOR_MODE':mode, 'FOG_ENABLED':enabled})
            declarations = re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;', source, re.M)
            assert len(declarations) == len(set(declarations)), path.name
            definitions = re.findall(r'^(?:float|vec[234]|void|bool|int)\s+(\w+)\([^;]*?\)\s*\{', source, re.M)
            assert len(definitions) == len(set(definitions)), path.name
            m = body(source, 'main')
            if path.stem in LATE_PROGRAMS or path.stem == 'deferred':
                for name in ('applyAtmosphericFog', 'applyLateAtmosphericFog'):
                    if not mode or not enabled:
                        assert body(source, name) == 'returnscene;', (path.name, mode, enabled, name)
                if path.stem in LATE_PROGRAMS:
                    assert m.count('applyLateAtmosphericFog(') == 1
                    assert 'gl_FragCoord.xy/vec2(viewWidth,viewHeight)' in m
                    assert 'reconstructViewPosition(fogUV,gl_FragCoord.z)' in m
            elif path.stem == 'gbuffers_clouds':
                # M12 adds this one verified native draw path; all other exclusions remain.
                assert m.count('applyCloudAtmosphere(') == 1
                assert 'applyLateAtmosphericFog(' not in m
                if not mode or not enabled:
                    assert compact(function_body(source, 'applyAtmosphericFog')) == 'returnscene;'
            else:
                assert 'applyAtmosphericFog' not in source and 'applyLateAtmosphericFog' not in source, path.name
        # Compare M8 complete main bodies after removal of the precise new calls;
        # disabled/legacy helper bodies above establish that these calls are identity.
        for name in ('deferred',) + LATE_PROGRAMS:
            assert '#define APPLY_LATE_FOG' not in read(name+'.vsh')
    settings = read('lib/fog_settings.glsl')
    props = read('shaders.properties')
    labels = read('lang/en_us.lang')
    for name, default in (('FOG_ENABLED','1'), ('FOG_DENSITY','0.006'), ('FOG_START','24.0'),
                          ('FOG_BASE_HEIGHT','64.0'), ('FOG_HEIGHT_FALLOFF','64.0'), ('FOG_RAIN_BOOST','1.0')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //', settings, re.M)
        assert name in props.split('screen.FOG =', 1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$', labels, re.M)
    assert props.count('particles.ordering = after') == 1
    # Numerical invariants over distances, vertical slopes, rain and all controls.
    cases = 0
    for distance, heights, density, start, falloff, base, rain, boost, env in product(
            (0,16,24,64,256,10000), ((0,0),(64,64),(256,256),(0,256),(256,0)),
            (0,.002,.006,.02), (0,24,64), (16,64,128), (32,64,128), (0,.5,1), (0,1,2), (0,.4,1)):
        value = transmission(distance, *heights, density=density, start=start, falloff=falloff,
                             base=base, rain=rain, boost=boost, environment=env)
        assert math.isfinite(value) and math.exp(-80) <= value <= 1
        if not density or distance <= start or not env:
            assert value == 1
        if distance > start:
            mean = segment_density(*heights, distance, start, base, falloff)
            endpoints = [density_at(heights[0]+(heights[1]-heights[0])*start/distance, base, falloff),
                         density_at(heights[1], base, falloff)]
            assert min(endpoints)-1e-15 <= mean <= max(endpoints)+1e-15 <= 1+1e-15
        cases += 1
    for height in (-1000,0,64,128,256):
        samples = [transmission(d, height, height) for d in (0,16,24,25,64,256,10000)]
        assert samples == sorted(samples, reverse=True)
        for distance, start in product((64,256), (0,24)):
            actual = transmission(distance, height, height, start=start)
            expected = math.exp(-clamp(.006*(distance-start)*density_at(height), 0, 80))
            assert abs(actual-expected) < 1e-14
    for a, b in ((0,256),(256,0),(64,128)):
        for keyword, values in (('density',(0,.002,.006,.02)), ('rain',(0,.25,.5,1)), ('boost',(0,.5,1,2))):
            samples = [transmission(300, a, b, rain=.5, **{keyword:v}) if keyword != 'rain'
                       else transmission(300, a, b, rain=v) for v in values]
            assert samples == sorted(samples, reverse=True)
    # Independent analytic integral for moderate exponential segments, including
    # near-distance truncation. Cross-reference-plane cases are bounded above.
    for origin, end, start in product((80,96,128), (80,96,128), (0,24,64)):
        first = origin+(end-origin)*start/256
        k = (end-first)/64
        exact = density_at(first) if abs(k) < 1e-12 else density_at(first)*(-math.expm1(-k))/k
        approx = segment_density(origin, end, 256, start)
        assert abs(approx-exact)/exact < .002
    assert transmission(100, 0, 256, start=64) != transmission(100, 0, 256, start=0)
    for invalid in (math.nan, math.inf, -math.inf):
        for field in ('distance', 'origin', 'end'):
            args = dict(distance=256, origin=64, end=128)
            args[field] = invalid
            assert transmission(**args) == 1
    # A finite vec3 near float32 max can overflow GLSL length to Inf: the explicit
    # rayLength guard (asserted above) uses the same safe identity fallback.
    assert transmission(math.inf) == 1
    assert transmission(0) == 1
    for condition in ({'skylight':False}, {'ceiling':True}, {'fluid':1}, {'fluid':2}, {'fluid':3},
                      {'blindness':1}, {'darkness':1}, {'eye_sky':0}):
        assert environment_weight(**condition) == 0
        assert transmission(1000, environment=environment_weight(**condition)) == 1
    assert environment_weight() == 1
    # Rigid camera rotation and a different player-coordinate anchor must recover
    # identical world heights/ray length. Moving the physical eye legitimately changes fog.
    origin, endpoint = (31.25,81.62,-8.5), (55.0,117.0,-128.0)
    world_ray = tuple(b-a for a,b in zip(origin,endpoint))
    distance = math.sqrt(sum(x*x for x in world_ray))
    expected = transmission(distance, origin[1], endpoint[1])
    for anchor, yaw, pitch in product(((31.25,80,-8.5),(-500.75,-16.25,900.5),(0,0,0)),
                                      (-2.0,0,.5),(-1.0,0,.8)):
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        rotation = ((cy,sy*sp,sy*cp),(0,cp,-sp),(-sy,cy*sp,cy*cp))
        view = tuple(sum(rotation[j][i]*world_ray[j] for j in range(3)) for i in range(3))
        translation = tuple(origin[i]-anchor[i] for i in range(3))
        player = tuple(sum(rotation[i][j]*view[j] for j in range(3))+translation[i] for i in range(3))
        int_y = math.floor(anchor[1])
        fract_y = anchor[1]-int_y
        recovered_origin = int_y+fract_y+translation[1]
        recovered_end = int_y+fract_y+player[1]
        recovered_distance = math.sqrt(sum(x*x for x in view))
        assert close((recovered_origin,recovered_end,recovered_distance), (origin[1],endpoint[1],distance))
        assert abs(transmission(recovered_distance,recovered_origin,recovered_end)-expected) < 1e-12
    # Fog enters after lighting. Shadow visibility changes the transmitted scene,
    # never the added atmosphere, which remains visible even for a black surface.
    scene, atmosphere, background = (.1,.8,2.0), (.3,.2,.7), (.6,.1,.4)
    for t in (0,.2,.7,1):
        result = fog_color(scene, atmosphere, t)
        assert close(fog_color((0,0,0), atmosphere, t), tuple((1-t)*x for x in atmosphere))
        if t == 0:
            assert result == atmosphere
        if t == 1:
            assert result == scene
        for alpha in (0,.1,.5,1):
            source = late_color(scene, atmosphere, t, (770,771))
            composed = tuple(alpha*x+(1-alpha)*b for x,b in zip(source,background))
            if alpha == 0:
                assert composed == background
            if alpha == 1:
                assert composed == result
            assert late_color(scene, atmosphere, t, (1,0)) == result
            for blend in ((1,1),(770,1)):
                source = late_color(scene, atmosphere, t, blend)
                factor = alpha if blend[0] == 770 else 1
                expected_add = tuple(b+factor*c*t for b,c in zip(background,scene))
                assert close(tuple(b+factor*x for b,x in zip(background,source)), expected_add)
                assert late_color((0,0,0),atmosphere,t,blend) == (0,0,0)
            squared = late_color(scene, atmosphere, t, (768,1))
            assert close(tuple(x*x for x in squared), tuple(c*c*t for c in scene))
        for unknown in ((0,0),(768,771),(774,1),(770,0)):
            assert late_color(scene, atmosphere, t, unknown) == scene
    print('PASS: M9 {} prior shader/property files pinned; fog-off/legacy identity and exact pass scope'.format(pinned))
    print('PASS: M9 {} bounded transmission cases; distance/density/rain controls and truncated height integral'.format(cases))
    print('PASS: M9 world-height camera invariance, invalid-input fallback and environment/vision/cave bypass')
    print('PASS: M9 post-light fog, alpha endpoints, opaque/additive/SRC_COLOR blends and unknown-blend bypass')
    print('LIMIT: analytical fog approximation; no Minecraft/Iris/GPU runtime validation or performance measurement')
