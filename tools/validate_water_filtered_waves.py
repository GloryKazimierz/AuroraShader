"""W2 filtered water-wave references, numerical integration and historical pins."""
import math
import re
import struct
import subprocess
from functools import lru_cache
from itertools import product
from pathlib import Path
from validate_water_screen_reflection import REFLECTION_OPTIONS, restore_water_screen_reflection_source

W1_BASELINE = '5d3e91761beaa3747052c11aa429e27be8d42df4'
FILTER_OPTIONS = {'WATER_SURFACE_DETAIL'}
FILTER_LABELS = {'option.WATER_SURFACE_DETAIL', 'value.WATER_SURFACE_DETAIL.0',
                 'value.WATER_SURFACE_DETAIL.1', 'option.WATER_SURFACE_DETAIL.comment'}
WAVES = ((11,3,.06,10), (4,-9,.04,-13), (7,13,.03,7),
         (49,19,.006,24), (-83,31,.0035,-31), (151,97,.0015,43))
TAU = 2 * math.pi
MAX_GRADIENT = sum(amplitude * TAU / 128 * math.hypot(kx,kz) for kx,kz,amplitude,_ in WAVES)


def f32(value):
    try:
        return struct.unpack('f', struct.pack('f', value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def cycle(seconds, speed=1, fp32=False):
    seconds = max(seconds, 0) if math.isfinite(seconds) else 0
    value = f32(f32(seconds) * f32(speed / 200)) if fp32 else seconds * speed / 200
    return value - math.floor(value)


def valid_footprint(dx, dy):
    return len(dx) == len(dy) == 2 and all(math.isfinite(x) and abs(x) <= 65536 for x in tuple(dx) + tuple(dy))


def sinc(value):
    """Exact mathematical sinc; independent of the GLSL small-angle polynomial."""
    if not math.isfinite(value):
        return 0.0
    return 1.0 if value == 0 else math.sin(value) / value


def nyquist_taper(cycles_per_pixel):
    if not math.isfinite(cycles_per_pixel):
        return 0.0
    frequency = abs(cycles_per_pixel)
    if frequency <= .25:
        return 1.0
    if frequency >= .5:
        return 0.0
    # Hermite interpolation of value/slope (1,0) -> (0,0), evaluated separately
    # from the exact area average. This deliberately suppresses near-Nyquist energy.
    t = (frequency - .25) / .25
    return (1 - t) ** 2 * (1 + 2 * t)


def pixel_filter(wave_vector, dx, dy):
    if not valid_footprint(dx, dy) or not all(math.isfinite(x) for x in wave_vector):
        return 0.0
    qx = sum(k*x for k,x in zip(wave_vector, dx)) / 128
    qy = sum(k*x for k,x in zip(wave_vector, dy)) / 128
    return sinc(math.pi*qx) * sinc(math.pi*qy) * nyquist_taper(max(abs(qx), abs(qy)))


def filtered_gradient(tile, seconds=0, speed=1, dx=(0,0), dy=(0,0), fp32=False):
    """World-block slope; fp32 models clock math only, as in the M14 reference."""
    if not valid_footprint(dx, dy) or not all(math.isfinite(x) for x in tile):
        return (0.0, 0.0)
    time = cycle(seconds, speed, fp32)
    result = [0.0, 0.0]
    for kx,kz,amplitude,harmonic in WAVES:
        phase = kx*tile[0] + kz*tile[1] + harmonic*time
        phase -= math.floor(phase)
        gain = amplitude * TAU / 128 * math.cos(TAU*phase) * pixel_filter((kx,kz), dx, dy)
        result[0] += gain * kx
        result[1] += gain * kz
    return tuple(result)


def quadrature_gradient(tile, seconds, speed, dx, dy, samples=96):
    """Dense midpoint integration over the projected pixel parallelogram.

    No sinc formula appears in this oracle. Each wave is integrated from its
    virtual-height derivative; the independent Nyquist taper is applied afterward.
    """
    if not valid_footprint(dx, dy):
        return (0.0, 0.0)
    time = cycle(seconds, speed)
    result = [0.0, 0.0]
    offsets = [(index + .5) / samples - .5 for index in range(samples)]
    for kx,kz,amplitude,harmonic in WAVES:
        qx = (kx*dx[0] + kz*dx[1]) / 128
        qy = (kx*dy[0] + kz*dy[1]) / 128
        cutoff = nyquist_taper(max(abs(qx), abs(qy)))
        if not cutoff:
            continue
        average = sum(math.cos(TAU * (kx*tile[0] + kz*tile[1] + harmonic*time + qx*x + qy*y))
                      for x in offsets for y in offsets) / (samples * samples)
        gain = amplitude * TAU / 128 * average * cutoff
        result[0] += gain * kx
        result[1] += gain * kz
    return tuple(result)


def validate_filtered_math():
    footprints = (((0,0),(0,0)), ((.04,0),(0,.04)), ((.2,0),(0,.1)),
                  ((.05,.15),(-.2,.03)), ((.4,0),(0,.3)), ((1.5,.2),(.3,2.0)))
    maximum_error = 0.0
    integrated = 0
    for tile,seconds,(dx,dy) in product(((.13,.47),(.91,.04)), (0,17), footprints):
        actual = filtered_gradient(tile,seconds,1,dx,dy)
        expected = quadrature_gradient(tile,seconds,1,dx,dy)
        maximum_error = max(maximum_error, max(abs(a-b) for a,b in zip(actual, expected)))
        assert max(abs(a-b) for a,b in zip(actual, expected)) < 2e-6
        assert math.hypot(*actual) <= MAX_GRADIENT + 1e-12
        integrated += 1
    assert nyquist_taper(.25) == 1 and nyquist_taper(.5) == 0
    assert nyquist_taper(.375) == .5
    tapers = [nyquist_taper(index / 1000) for index in range(1001)]
    assert all(0 <= right <= left <= 1 for left,right in zip(tapers,tapers[1:]))
    for boundary in (.25,.5):
        assert abs(nyquist_taper(boundary-1e-6)-nyquist_taper(boundary+1e-6)) < 1e-9
    for value in (0, 1e-10, .000999, .001001, .2, math.pi*.499):
        assert sinc(value) == sinc(-value)
        assert abs(sinc(value)) <= 1
    for wave in WAVES:
        vector=wave[:2]
        assert pixel_filter(vector,(0,0),(0,0)) == 1
        for dx,dy in footprints:
            weight=pixel_filter(vector,dx,dy)
            assert 0 <= weight <= 1
            assert abs(weight-pixel_filter(vector,dy,dx)) < 1e-14
            assert abs(weight-pixel_filter(vector,tuple(-x for x in dx),dy)) < 1e-14
        # Single-axis frequency sweep crosses the full-strength/taper/zero regions.
        for frequency in (0,.1,.25,.375,.499,.5,1,100):
            dx=(frequency*128/vector[0],0)
            expected=sinc(math.pi*frequency)*nyquist_taper(frequency)
            assert abs(pixel_filter(vector,dx,(0,0))-expected) < 1e-12
    for invalid in (math.nan, math.inf, -math.inf, 65536.01, -65536.01):
        assert not valid_footprint((invalid,0),(0,0))
        assert filtered_gradient((.13,.47),17,1,(invalid,0),(0,0)) == (0,0)
        assert filtered_gradient((.13,.47),17,1,(0,0),(0,invalid)) == (0,0)
    assert valid_footprint((65536,0),(0,-65536))
    assert filtered_gradient((.13,.47),17,1,(65536,0),(0,65536)) == (0,0)
    for invalid in (math.nan,math.inf,-math.inf):
        assert filtered_gradient((invalid,.4)) == (0,0)
    seams=0
    maximum_wrap_delta=0.0
    for tile,seconds,speed,(dx,dy) in product(((0,0),(.13,.47),(.99999,.99999)),(0,17),(0,1,2),footprints):
        expected=filtered_gradient(tile,seconds,speed,dx,dy)
        for shift in ((1,0),(0,1),(-1,0),(0,-1)):
            actual=filtered_gradient((tile[0]+shift[0],tile[1]+shift[1]),seconds,speed,dx,dy)
            assert max(abs(a-b) for a,b in zip(actual,expected)) < 1e-11
            seams += 1
        for period in (200,3600):
            actual=filtered_gradient(tile,seconds+period,speed,dx,dy)
            assert max(abs(a-b) for a,b in zip(actual,expected)) < 1e-11
            before=filtered_gradient(tile,period-.001,speed,dx,dy,True)
            after=filtered_gradient(tile,.001,speed,dx,dy,True)
            maximum_wrap_delta=max(maximum_wrap_delta,max(abs(a-b) for a,b in zip(before,after)))
            seams += 1
    assert maximum_wrap_delta < .001
    for invalid in (-1,math.nan,math.inf,-math.inf):
        assert cycle(invalid)==0
    assert filtered_gradient((.13,.47),0,0) != (0,0)
    assert math.isfinite(cycle(3e38,2,True))
    print('PASS: W2 {} dense box integrations; max slope error {:.6g}; independent sinc/anisotropic/Nyquist checks'.format(integrated,maximum_error))
    print('PASS: W2 {} tile/time seams; invalid/oversized footprints; float32 clock-wrap delta {:.6g}'.format(seams,maximum_wrap_delta))
    print('PASS: W2 six-wave slope bound {:.9g}; rigid-camera tilt at full/default strength {:.6g}/{:.6g} degrees'.format(MAX_GRADIENT,math.degrees(math.atan(MAX_GRADIENT)),math.degrees(math.atan(MAX_GRADIENT*.6))))


FOOTPRINT_INITIALIZERS = '''    vec2 waterWorldDx = vec2(0.0);
    vec2 waterWorldDy = vec2(0.0);
'''
FOOTPRINT_DERIVATIVES = '''    // Derivatives require continuous coordinates and uniform control flow. Do
    // this before alpha discard and every material/environment/reflection gate.
    vec2 waterScreenUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 waterViewPosition = reconstructViewPosition(waterScreenUV, gl_FragCoord.z);
    waterWorldDx = (mat3(gbufferModelViewInverse) * dFdx(waterViewPosition)).xz;
    waterWorldDy = (mat3(gbufferModelViewInverse) * dFdy(waterViewPosition)).xz;
'''
FOOTPRINT_PREAMBLE = ('#ifdef APPLY_WATER_STYLE\n' + FOOTPRINT_INITIALIZERS
                      + '#if WATER_SURFACE_DETAIL == 1\n#define AURORA_WATER_CONTINUOUS_VIEW\n'
                      + FOOTPRINT_DERIVATIVES + '#endif\n#endif\n')
OLD_VIEW = '''    vec2 fogUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 fogView = reconstructViewPosition(fogUV, gl_FragCoord.z);
'''
REUSED_VIEW = '    vec3 fogView = waterViewPosition;\n'
VIEW_BRANCH = '#ifdef AURORA_WATER_CONTINUOUS_VIEW\n' + REUSED_VIEW + '#else\n' + OLD_VIEW + '#endif\n'
OLD_STYLE_CALL = '    color.rgb = applyWaterStyle(color.rgb, fogView, normalView, lmcoord, waterSurface, blendFunc, fogColor);\n'
NEW_STYLE_CALL = OLD_STYLE_CALL.replace('fogColor);', 'fogColor, waterWorldDx, waterWorldDy);')
OLD_STYLE_SIGNATURE = '                     int waterSurface, ivec4 blendState, vec3 vanillaFog) {\n'
NEW_STYLE_SIGNATURE = '                     int waterSurface, ivec4 blendState, vec3 vanillaFog,\n                     vec2 waterWorldDx, vec2 waterWorldDy) {\n'
OLD_NORMAL_CALL = '    normal = waterWaveNormal(normal, viewPosition, upwardSurface);\n'
NEW_NORMAL_CALL = '    normal = waterFilteredWaveNormal(normal, viewPosition, upwardSurface, waterWorldDx, waterWorldDy);\n'


def replace_exact(source, current, previous):
    assert source.count(current) == 1, 'Missing or changed W2 source fragment: ' + current
    return source.replace(current, previous, 1)


def restore_water_filtered_plumbing(source):
    """Idempotently restore only W2's raw/preprocessed geometry main additions."""
    for current, previous in ((FOOTPRINT_PREAMBLE,''),
                              (FOOTPRINT_INITIALIZERS + FOOTPRINT_DERIVATIVES,''),
                              (FOOTPRINT_INITIALIZERS,''), (VIEW_BRANCH,OLD_VIEW),
                              (REUSED_VIEW,OLD_VIEW), (NEW_STYLE_CALL,OLD_STYLE_CALL)):
        assert source.count(current) <= 1, 'Duplicated W2 geometry plumbing'
        source = source.replace(current, previous, 1)
    return source


def restore_water_filtered_source(relative, source):
    """Remove precisely W2's shader wiring, water-menu token and four new labels."""
    relative = relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_water_screen_reflection_source(relative,source)
    if relative == 'lib/water.glsl':
        for current,previous in (('#include "/lib/water_filtered_waves.glsl"\n',''),
                                 (NEW_STYLE_SIGNATURE,OLD_STYLE_SIGNATURE),
                                 (NEW_NORMAL_CALL,OLD_NORMAL_CALL)):
            source = replace_exact(source,current,previous)
    if relative == 'lib/geometry/lit_fragment.glsl':
        for current,previous in ((FOOTPRINT_PREAMBLE,''),(VIEW_BRANCH,OLD_VIEW),
                                 (NEW_STYLE_CALL,OLD_STYLE_CALL)):
            source = replace_exact(source,current,previous)
    if relative == 'shaders.properties':
        source = replace_exact(source,' WATER_WAVES WATER_SURFACE_DETAIL WATER_WAVE_STRENGTH ',
                               ' WATER_WAVES WATER_WAVE_STRENGTH ')
    if relative in ('lang/en_us.lang','lang/zh_cn.lang'):
        marker = '\noption.WATER_SURFACE_DETAIL='
        assert source.count(marker) == 1
        prefix,tail = source.split(marker,1)
        keys = [line.split('=',1)[0] for line in ('option.WATER_SURFACE_DETAIL='+tail).splitlines()]
        assert len(keys) == len(FILTER_LABELS) and set(keys) == FILTER_LABELS
        source = prefix
    return source


def filtered_normal_from_gradient(base_normal, gradient,
                                  normal_matrix=((1,0,0),(0,1,0),(0,0,1)),
                                  strength=.6, eligibility=1, enabled=True, fp32_length=False):
    # Import on use: older validators depend on the newest restore adapter, so
    # a module-level import of the M14 reference would create a dependency cycle.
    from validate_water_waves import wave_normal_from_gradient
    if not enabled or not math.isfinite(eligibility) or strength <= 0 or eligibility <= 0 or tuple(gradient) == (0,0):
        return base_normal
    return wave_normal_from_gradient(base_normal,gradient,normal_matrix,strength,eligibility,enabled,fp32_length)


def validate_water_filtered_waves(root, expand, preprocess, compact, function_body):
    from validate_settings_profiles import (option_definitions,parse_properties,parse_language,
                                            menu_options,load_profiles,matching_profiles,PROFILE_KEYS)
    from validate_water_waves import anchored_tile, matrix_vector, unit
    root=Path(root)
    shaders=root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    def body(source,name):
        return compact(function_body(source,name))
    @lru_cache(maxsize=None)
    def previous(relative):
        return subprocess.check_output(['git','-C',str(root),'show',W1_BASELINE+':shaders/'+relative]).decode('utf-8').replace('\r\n','\n')
    @lru_cache(maxsize=None)
    def expanded_previous(relative):
        return re.sub(r'^#include "([^"]+)"\s*$',lambda match:expanded_previous(match[1].lstrip('/')),
                      previous(relative),flags=re.M)
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',W1_BASELINE,'shaders']).decode().splitlines()
    assert len(old_files)==100
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files==set(old_files)|{'shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'}
    for path in old_files:
        relative=path[len('shaders/'):]
        assert restore_water_filtered_source(relative,read(relative))==previous(relative),relative
    helper=read('lib/water_filtered_waves.glsl')
    code=compact(helper)
    directions=[tuple(map(float,pair)) for pair in re.findall(r'vec2\(([-\d.]+),\s*([-\d.]+)\)',helper.split('const vec2 directions[6] =',1)[1].split(';',1)[0])]
    amplitudes=tuple(map(float,re.search(r'const float amplitudes\[6\] = float\[6\]\(([^)]+)\)',helper)[1].split(',')))
    harmonics=tuple(map(float,re.search(r'const float harmonics\[6\] = float\[6\]\(([^)]+)\)',helper)[1].split(',')))
    assert tuple((kx,kz,a,h) for (kx,kz),a,h in zip(directions,amplitudes,harmonics))==WAVES
    for forbidden in ('sampler','texture(','texelFetch(','depthtex','colortex','dFdx(','dFdy(','gl_Position','gl_FragDepth'):
        assert forbidden not in code,forbidden
    assert 'if(frequency>=0.5)return0.0;' in code
    assert 'waterWaveSinc(angles.x)*waterWaveSinc(angles.y)' in code
    assert 'boxAverage*(1.0-smoothstep(0.25,0.5,frequency))' in code
    assert 'if(all(equal(slope,vec2(0.0))))returnbaseNormal;' in code
    assert 'vec2tile=fract((anchor+cameraPositionFract.xz+playerPosition.xz)/128.0);' in code
    # Derivatives are in uniform fragment flow, before discard and water/material
    # gates. They act on continuous view coordinates, then transform as directions.
    geometry=read('lib/geometry/lit_fragment.glsl')
    main=body(geometry,'main')
    assert main.index('dFdx(waterViewPosition)') < main.index('discard;') < main.index('applyWaterStyle(')
    assert main.index('dFdy(waterViewPosition)') < main.index('discard;')
    assert main.count('dFdx(')==main.count('dFdy(')==1
    assert '(mat3(gbufferModelViewInverse)*dFdx(waterViewPosition)).xz' in main
    assert '(mat3(gbufferModelViewInverse)*dFdy(waterViewPosition)).xz' in main
    assert 'color.a=' not in main and 'gl_FragDepth' not in main
    assert body(restore_water_filtered_source('lib/water.glsl',read('lib/water.glsl')),'applyWaterStyle') == body(previous('lib/water.glsl'),'applyWaterStyle')
    # Every current state retains the old stage main after only exact W2 plumbing
    # restoration. Detail off additionally invokes exactly the original normal.
    for detail,mode,waves,style,debug in product((0,1),(0,1),(0,1),(0,1),range(7)):
        options={'WATER_SURFACE_DETAIL':detail,'SCENE_COLOR_MODE':mode,'WATER_WAVES':waves,'WATER_STYLE':style}
        selected=preprocess(expand(shaders/'gbuffers_water.fsh'),debug,False,overrides=options)
        old=preprocess(expanded_previous('gbuffers_water.fsh'),debug,False,overrides=options)
        assert body(restore_water_filtered_plumbing(selected),'main')==body(old,'main')
        normal=body(selected,'waterFilteredWaveNormal')
        if not detail:
            assert normal=='returnwaterWaveNormal(baseNormal,viewPosition,surfaceEligibility);'
            assert 'dFdx(' not in body(selected,'main') and 'dFdy(' not in body(selected,'main')
        elif not waves:
            assert normal=='returnbaseNormal;'
        if not mode or not style or debug:
            assert body(selected,'applyWaterStyle')=='returnscene;'
    for path in shaders.glob('*.fsh'):
        selected=preprocess(expand(path),0,False)
        assert ('waterFilteredWaveNormal(' in selected)==(path.stem=='gbuffers_water'),path.name
        uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms)==len(set(uniforms)),path.name
    for path in shaders.glob('*.vsh'):
        assert 'waterFilteredWaveNormal(' not in preprocess(expand(path),0,False),path.name
    options={key:value for key,value in option_definitions(root).items() if key not in REFLECTION_OPTIONS}
    props=parse_properties(restore_water_screen_reflection_source('shaders.properties',read('shaders.properties')))
    controls,screens=menu_options(props,options)
    assert len(options)==len(controls)==58 and len(screens)==12
    assert options['WATER_SURFACE_DETAIL']==dict(kind='number',default='1',values=('0','1'))
    profiles=load_profiles(root)
    controlled=PROFILE_KEYS|{'FOLIAGE_WIND'}
    assert all(set(profile)==controlled for profile in profiles.values())
    assert len(set(options)-controlled)==51
    defaults={key:value['default'] for key,value in options.items()}
    for name,profile in profiles.items():
        for detail in ('0','1'):
            assert matching_profiles(profiles,dict(defaults,**profile,WATER_SURFACE_DETAIL=detail))==(name,)
    en,zh=(parse_language(restore_water_screen_reflection_source('lang/'+language,read('lang/'+language))) for language in ('en_us.lang','zh_cn.lang'))
    assert len(en)==len(zh)==183 and set(en)==set(zh) and FILTER_LABELS<=set(en)
    assert all(re.search(r'[\u3400-\u9fff]',zh[key]) for key in FILTER_LABELS)
    validate_filtered_math()
    # Reuse only the established covector-space convention; the new wave field is
    # independently integrated above. Verify bounded normals and camera poses.
    normal_cases=0
    for tile,dx,dy,strength,eligibility in product(((0,0),(.13,.47),(.99,.01)),((0,0),(.2,.1)),((0,0),(-.1,.2)),(0,.3,.6,1),(0,.25,1)):
        gradient=filtered_gradient(tile,17,1,dx,dy)
        base=(0,1,0)
        actual=filtered_normal_from_gradient(base,gradient,strength=strength,eligibility=eligibility)
        assert abs(sum(x*x for x in actual)-1)<1e-12
        assert math.atan2(math.hypot(actual[0],actual[2]),actual[1]) <= math.atan(MAX_GRADIENT*strength*eligibility)+1e-12
        if not strength or not eligibility:
            assert actual is base
        normal_cases+=1
    base=(.2,.7,.1)
    assert filtered_normal_from_gradient(base,(0,0)) is base
    for bad in (math.nan,math.inf,-math.inf):
        assert filtered_normal_from_gradient(base,(.1,.2),eligibility=bad) is base
    for integer in (-2147483648,2147483647,-30000000,30000000,-129,-1,0,127,128):
        reference=anchored_tile((integer,0,integer),(.375,0,.625),(1.25,0,-2.5))
        for delta in (-128,0,128):
            tile=anchored_tile((integer,0,integer),(.375,0,.625),(delta+1.25,0,delta-2.5))
            assert max(abs(a-b) for a,b in zip(filtered_gradient(tile,17),filtered_gradient(reference,17)))<1e-11
    gradient=filtered_gradient((.13,.47),17,1,(.1,0),(0,.1))
    for yaw,pitch,scales in product((-2,0,.7),(-.8,0,.5),((1,1,1),(.5,2,3),(3,.75,.4))):
        cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        rotation=((cy,0,sy),(sp*sy,cp,-sp*cy),(-cp*sy,sp,cp*cy))
        normal_matrix=tuple(tuple(rotation[i][j]/scales[j] for j in range(3)) for i in range(3))
        base_view=unit(matrix_vector(normal_matrix,(0,1,0)))
        actual=filtered_normal_from_gradient(base_view,gradient,normal_matrix)
        expected=unit(matrix_vector(normal_matrix,(-gradient[0]*.6,1,-gradient[1]*.6)))
        assert max(abs(a-b) for a,b in zip(actual,expected))<1e-12
    print('PASS: W2 all 100 W1 shader/property/language files pinned; only exact authorized wiring and two new helpers')
    print('PASS: W2 pre-discard continuous derivatives, exact detail-off restoration, unchanged material/fog/alpha/geometry and {} bounded normals'.format(normal_cases))
    print('PASS: W2 58 controls, 12 screens, unchanged seven-control profiles retain 51 settings, 183 bilingual keys')
    print('LIMIT: affine pixel filtering and normal-only wave detail; no simulated flow, displacement, SSR, Iris appearance or performance claim')
