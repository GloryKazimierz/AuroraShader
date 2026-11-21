"""W1 matched pre-fog scene snapshot reference and exact historical adapters.

The CPU oracle defines sample eligibility, without simulating GLSL execution or
texture storage. Native-driver fixtures separately test the actual mixed MRT.
"""
import math
import re
import subprocess
from itertools import product
from pathlib import Path
from validate_water_filtered_waves import restore_water_filtered_source

M19_BASELINE = '74c7164874e446ebd8e763f146286c2c6908b820'
INVALID_SNAPSHOT = ((0.0, 0.0, 0.0, 0.0), 1.0)
SNAPSHOT_INCLUDE = '#include "/lib/water_scene_snapshot.glsl"\n'
SNAPSHOT_UNIFORM = 'uniform sampler2D depthtex2;\n'
SNAPSHOT_DECLARATIONS = '''// Water tracing infrastructure: full-resolution, read-only throughout later geometry.
// Buffer 5 stores pre-camera-fog linear radiance and validity; buffer 6 stores matched depth.
/*
const int colortex5Format = RGBA16F;
const int colortex6Format = R32F;
*/
const bool colortex5Clear = true;
const bool colortex6Clear = true;
const vec4 colortex5ClearColor = vec4(0.0);
const vec4 colortex6ClearColor = vec4(1.0, 0.0, 0.0, 0.0);

'''
SNAPSHOT_OUTPUTS = '''layout(location = 1) out vec4 waterSceneColor;
layout(location = 2) out float waterSceneDepth;
'''
SNAPSHOT_INITIALIZERS = '''    waterSceneColor = vec4(0.0);
    waterSceneDepth = 1.0;
'''
SNAPSHOT_CALL = '''        // Capture the same lit surface before applying camera-to-surface atmosphere.
        // Later reflection/transmission rays need their own path-dependent attenuation.
        encodeWaterSceneSnapshot(color.rgb, surface.a, surfaceDepth,
            texelFetch(depthtex2, pixel, 0).r, waterSceneColor, waterSceneDepth);
'''


def encode_snapshot(radiance, validity, depth1, depth2, mode=1, debug=0):
    """Return (linear RGBA with validity alpha, raw depth), before format storage.

    Samples need known surface metadata, finite nonnegative half-float RGB,
    non-sky depth1 and an admissible pre-hand depth2. A nearer depth1 is excluded
    conservatively, since its color may belong to a hand over stale metadata.
    """
    eligible = (mode != 0 and debug == 0 and math.isfinite(validity) and validity > .5
                and len(radiance) == 3 and all(math.isfinite(x) and 0 <= x <= 65504 for x in radiance)
                and math.isfinite(depth1) and math.isfinite(depth2)
                and 0 <= depth1 < 1 and 0 <= depth2 <= 1 and depth1 >= depth2)
    return (tuple(radiance) + (1.0,), depth1) if eligible else INVALID_SNAPSHOT


def restore_water_snapshot_plumbing(source):
    """Idempotently remove just the exact W1 main-body additions for older pins."""
    for addition in (SNAPSHOT_INITIALIZERS, SNAPSHOT_CALL):
        assert source.count(addition) <= 1, 'Duplicated W1 plumbing'
        source = source.replace(addition, '', 1)
    return source


def restore_water_snapshot_source(relative, source):
    """Restore precisely the approved deferred additions to the immutable M19 source."""
    relative = relative.replace('\\', '/')
    if relative.startswith('shaders/'):
        relative = relative[len('shaders/'):]
    source = restore_water_filtered_source(relative, source)
    if relative == 'deferred.fsh':
        for addition in (SNAPSHOT_INCLUDE, SNAPSHOT_UNIFORM, SNAPSHOT_DECLARATIONS,
                         SNAPSHOT_OUTPUTS, SNAPSHOT_INITIALIZERS, SNAPSHOT_CALL):
            assert source.count(addition) == 1, 'Missing or changed W1 addition: ' + addition
            source = source.replace(addition, '', 1)
        targets = '/* RENDERTARGETS: 0,5,6 */'
        assert source.count(targets) == 1
        source = source.replace(targets, '/* RENDERTARGETS: 0 */', 1)
    return source


def validate_snapshot_math():
    rgb_cases = ((0, 0, 0), (.01, .5, 1), (8, 2, .1), (65504, 0, 65504))
    cases = 0
    for rgb, validity, depth in product(rgb_cases, (.500001, 1, 2), (0, .01, .5, .9999999)):
        result = encode_snapshot(rgb, validity, depth, depth)
        assert result == (tuple(rgb) + (1.0,), depth)
        # Dark geometry remains a valid hit; validity is not coverage/luminance.
        assert result[0][3] == 1
        cases += 1
    for depth1, depth2 in product((0, .001, .4, .9, .9999999, 1), repeat=2):
        result = encode_snapshot((1, 2, 3), 1, depth1, depth2)
        assert (result != INVALID_SNAPSHOT) == (depth2 <= depth1 < 1)
        if result != INVALID_SNAPSHOT:
            assert result[1] == depth1
        cases += 1
    # Each malformed input must invalidate BOTH buffers, without leaking stale data.
    for invalid in (math.nan, math.inf, -math.inf):
        for channel in range(3):
            rgb = [1, 2, 3]
            rgb[channel] = invalid
            assert encode_snapshot(rgb, 1, .5, .5) == INVALID_SNAPSHOT
        assert encode_snapshot((1, 2, 3), invalid, .5, .5) == INVALID_SNAPSHOT
        assert encode_snapshot((1, 2, 3), 1, invalid, .5) == INVALID_SNAPSHOT
        assert encode_snapshot((1, 2, 3), 1, .5, invalid) == INVALID_SNAPSHOT
    for bad in (-1, -.000001, 65504.01, 1e30):
        for channel in range(3):
            rgb = [1, 2, 3]
            rgb[channel] = bad
            assert encode_snapshot(rgb, 1, .5, .5) == INVALID_SNAPSHOT
    for validity in (-100, 0, .5):
        assert encode_snapshot((1, 2, 3), validity, .5, .5) == INVALID_SNAPSHOT
    for depth in (-1, -.000001, 1, 1.000001, 100):
        assert encode_snapshot((1, 2, 3), 1, depth, 0) == INVALID_SNAPSHOT
    for depth in (-1, -.000001, 1.000001, 100):
        assert encode_snapshot((1, 2, 3), 1, .5, depth) == INVALID_SNAPSHOT
    for mode, debug in product((0, 1), range(7)):
        result = encode_snapshot((2, 1, 0), 1, .5, .5, mode, debug)
        assert (result == INVALID_SNAPSHOT) == (mode == 0 or debug != 0)
    # The contract returns raw nonlinear depth, not linearized or half-precision depth.
    depth = 1 - 2**-24
    assert encode_snapshot((0, 0, 0), 1, depth, depth)[1] == depth < 1
    print('PASS: W1 {} valid/hand/sky cases; black validity, HDR limits, nonfinite inputs and coherent bypasses'.format(cases))


def validate_water_snapshot(root, expand, preprocess, compact, function_body):
    shaders = Path(root) / 'shaders'
    def read(relative):
        return (shaders / relative).read_text(encoding='utf-8')
    old_files = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only',
                                         M19_BASELINE, 'shaders']).decode().splitlines()
    assert len(old_files) == 99
    current_files = {str(path.relative_to(root)).replace('\\', '/')
                     for path in shaders.rglob('*') if path.is_file()}
    assert current_files == set(old_files) | {'shaders/lib/water_scene_snapshot.glsl','shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'}
    for path in old_files:
        previous = subprocess.check_output(['git', '-C', str(root), 'show', M19_BASELINE + ':' + path]).decode('utf-8').replace('\r\n', '\n')
        assert restore_water_snapshot_source(path, read(path[len('shaders/'):])) == previous, path
    deferred = read('deferred.fsh')
    helper = read('lib/water_scene_snapshot.glsl')
    code = compact(helper)
    main = compact(function_body(deferred, 'main'))
    # Main output/alpha restoration is pinned above. These bind the new data flow
    # to lit radiance, matching texels and the pre-camera-fog capture point.
    assert main.index('color=scene;') < main.index('waterSceneColor=vec4(0.0);') < main.index('if(surface.a>0.5)')
    assert main.index('waterSceneDepth=1.0;') < main.index('if(surface.a>0.5)')
    assert main.index('lightScene(') < main.index('applyCelestialPalette(') < main.index('texelFetch(depthtex1,pixel,0).r') < main.index('encodeWaterSceneSnapshot(') < main.index('applyAtmosphericFog(')
    assert main.count('encodeWaterSceneSnapshot(') == 1
    assert 'encodeWaterSceneSnapshot(color.rgb,surface.a,surfaceDepth,texelFetch(depthtex2,pixel,0).r,waterSceneColor,waterSceneDepth);' in main
    assert 'snapshotColor=vec4(radiance,1.0);' in code and 'snapshotDepth=opaqueDepth;' in code
    assert 'if(opaqueDepth<preHandDepth)return;' in code
    for forbidden in ('uniform', 'sampler', 'texture(', 'texelFetch(', 'gl_FragCoord', 'gl_FragDepth', 'applyAtmosphericFog('):
        assert forbidden not in code, forbidden
    for mode, debug in product((0, 1), range(7)):
        selected = preprocess(expand(shaders / 'deferred.fsh'), debug, False, overrides={'SCENE_COLOR_MODE':mode})
        body = compact(function_body(selected, 'encodeWaterSceneSnapshot'))
        if mode == 0 or debug != 0:
            assert body == 'snapshotColor=vec4(0.0);snapshotDepth=1.0;return;'
        else:
            assert 'snapshotColor=vec4(radiance,1.0);' in body
        uniforms = re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;', selected, re.M)
        assert len(uniforms) == len(set(uniforms))
        assert uniforms.count('depthtex1') == uniforms.count('depthtex2') == 1
    # Default full-resolution ping-pong is intentional. Only deferred writes 5/6;
    # there are no consumers yet, resize/flip overrides, or user-facing controls.
    props = read('shaders.properties')
    assert not re.search(r'^(?:size\.buffer\.colortex[56]|flip\.\w+\.colortex[56])\s*=', props, re.M)
    for path in shaders.rglob('*'):
        if not path.is_file() or path.name in ('deferred.fsh','water_screen_reflection.glsl'):
            continue
        assert not re.search(r'\bcolortex[56]\b', path.read_text(encoding='utf-8')), str(path)
    assert restore_water_snapshot_plumbing(restore_water_snapshot_plumbing(deferred)) == restore_water_snapshot_plumbing(deferred)
    print('PASS: W1 all 99 M19 shader/property/language files pinned after exact deferred-only restoration; one new helper')
    print('PASS: W1 RGBA16F/R32F MRT 0,5,6, coherent clears, pre-fog matched texels, legacy/debug invalidation and unchanged controls')
    validate_snapshot_math()
    print('LIMIT: snapshot infrastructure only; no consumers, SSR, physical transmission, Iris runtime or performance claim')
