"""Optional offline GLSL compile/link matrix; does not run Iris or a GPU.

Run with: python -B tools/compile_glsl.py
Requires glslangValidator on PATH (or --compiler PATH). No downloads.
"""
from pathlib import Path
from functools import lru_cache
from itertools import product
import argparse
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / 'shaders'

@lru_cache(maxsize=None)
def expand(path, chain=()):
    path = path.resolve()
    if path in chain or SHADERS.resolve() not in path.parents:
        raise ValueError('Invalid include: ' + str(path))
    source = path.read_text(encoding='utf-8')
    return re.sub(r'^#include "([^"]+)"\s*$',
                  lambda m: expand(SHADERS / m[1].lstrip('/'), chain + (path,)),
                  source, flags=re.M)

def configure(source, overrides):
    lines = []
    for line in source.splitlines():
        match = re.match(r'^\s*(?://\s*)?#define\s+(\w+)\b', line)
        if match and match[1] in overrides:
            key, value = match[1], overrides[match[1]]
            line = ('//#define ' + key) if value is False else '#define ' + key + ' ' + str(value)
        lines.append(line)
    # Distinct compile-only placeholders. Iris provides actual stage constants at runtime.
    lines[1:1] = ['#define MC_RENDER_STAGE_SKY 4', '#define MC_RENDER_STAGE_STARS 5', '#define MC_RENDER_STAGE_VOID 6']
    return '\n'.join(lines) + '\n'

def configurations():
    # Every geometry category, prepare and fullscreen path in both storage modes.
    for mode in (0, 1):
        for path in sorted(SHADERS.glob('*.vsh')):
            yield path.stem, dict(SCENE_COLOR_MODE=mode)
        for style, blend, sunset, night in product((0, 1), (0.0, 1.0), (0.0, 1.5), (0.5, 2.0)):
            yield 'gbuffers_skybasic', dict(SCENE_COLOR_MODE=mode, SKY_STYLE=style, SKY_BLEND=blend,
                                           SUNSET_GLOW=sunset, NIGHT_BRIGHTNESS=night)
        for palette, bias, filtering, shadows, strength in product((0, 1), (0, 1), range(4), (False, True), (0.0, 1.0)):
            yield 'deferred', dict(SCENE_COLOR_MODE=mode, LIGHT_PALETTE=palette, SHADOW_BIAS_MODE=bias,
                                   SHADOW_FILTER=filtering, SHADOWS_ENABLED=shadows,
                                   LIGHTING_STRENGTH=strength)
        for debug, filtering, bias in product(range(7), range(4), (0, 1)):
            yield 'final', dict(SCENE_COLOR_MODE=mode, DEBUG_VIEW=debug,
                                SHADOW_FILTER=filtering, SHADOW_BIAS_MODE=bias)
        yield 'final', dict(SCENE_COLOR_MODE=mode, GRAYSCALE=True)
    for mapping, knee, exposure, grayscale in product((0, 1), (.4, .6, .8), (-2.0, 0.0, 2.0), (False, True)):
        yield 'final', dict(SCENE_COLOR_MODE=1, TONE_MAPPING=mapping, TONEMAP_KNEE=knee,
                            EXPOSURE=exposure, GRAYSCALE=grayscale)

    # M9: every pair with fog explicitly enabled/disabled in both scene modes.
    for mode, fog in product((0, 1), repeat=2):
        for path in sorted(SHADERS.glob('*.vsh')):
            yield path.stem, dict(SCENE_COLOR_MODE=mode, FOG_ENABLED=fog)
    # Compile control extremes on each fogged path, avoiding the unrelated shadow
    # Cartesian product already covered above. Runtime blend states are uniforms.
    for program in ('deferred', 'gbuffers_water', 'gbuffers_weather',
                    'gbuffers_textured', 'gbuffers_textured_lit'):
        for density, start, base, falloff, rain in product((0.0, .02), (0.0, 64.0),
                                                         (32.0, 128.0), (16.0, 128.0), (0.0, 2.0)):
            yield program, dict(SCENE_COLOR_MODE=1, FOG_ENABLED=1, FOG_DENSITY=density,
                                FOG_START=start, FOG_BASE_HEIGHT=base,
                                FOG_HEIGHT_FALLOFF=falloff, FOG_RAIN_BOOST=rain)

    # M10: active and bypass code in every scene/debug combination on all passes.
    for program in ('composite', 'composite1', 'composite2', 'composite3'):
        for mode, enabled, debug in product((0, 1), (0, 1), range(7)):
            yield program, dict(SCENE_COLOR_MODE=mode, BLOOM_ENABLED=enabled, DEBUG_VIEW=debug)
        # Every threshold/knee choice with zero and maximum intensity; intermediate
        # strengths use identical shader paths and are covered numerically.
        for strength, threshold, knee in product((0.0, .2), (.5, 1.0, 1.5, 2.0), (0.0, .25, .5, 1.0)):
            yield program, dict(SCENE_COLOR_MODE=1, BLOOM_ENABLED=1, BLOOM_STRENGTH=strength,
                                BLOOM_THRESHOLD=threshold, BLOOM_SOFT_KNEE=knee)

    # M11: every compile-time aurora gate and every exposed intensity/speed choice.
    for mode, enabled, style, debug in product((0, 1), (0, 1), (0, 1), range(7)):
        yield 'gbuffers_skybasic', dict(SCENE_COLOR_MODE=mode, AURORA_ENABLED=enabled,
                                      SKY_STYLE=style, DEBUG_VIEW=debug)
    for intensity, speed, blend in product((0.0, .3, .6, 1.0), (0, 1, 2), (0.0, 1.0)):
        yield 'gbuffers_skybasic', dict(SCENE_COLOR_MODE=1, AURORA_ENABLED=1,
                                      AURORA_INTENSITY=intensity, AURORA_SPEED=speed, SKY_BLEND=blend)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', help='Path to installed glslangValidator')
    args = parser.parse_args()
    compiler = args.compiler or shutil.which('glslangValidator')
    if not compiler:
        raise SystemExit('glslangValidator unavailable; install separately or pass --compiler. No runtime validation performed.')
    configs = list(configurations())
    # Generated source stays on the same drive as the project and out of Git.
    scratch_parent = ROOT.parent.resolve()
    scratch = Path(tempfile.mkdtemp(prefix='aurora-glsl-', dir=str(scratch_parent))).resolve()
    if scratch.parent != scratch_parent or not scratch.name.startswith('aurora-glsl-'):
        raise RuntimeError('Unexpected compiler temporary directory; refusing cleanup')
    try:
        for index, (program, overrides) in enumerate(configs, 1):
            paths = []
            for source_suffix, compile_suffix in (('vsh', 'vert'), ('fsh', 'frag')):
                path = scratch / ('program.' + compile_suffix)
                with path.open('w', encoding='utf-8', newline='\n') as stream:
                    stream.write(configure(expand(SHADERS / (program + '.' + source_suffix)), overrides))
                paths.append(str(path))
            result = subprocess.run([compiler, '-l'] + paths, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True)
            if result.returncode:
                raise RuntimeError('{} {}\n{}'.format(program, overrides, result.stdout))
            if index % 32 == 0:
                print('Compiled {}/{} configurations'.format(index, len(configs)), flush=True)
    finally:
        # Only the freshly created, verified temporary directory is removed.
        if scratch.parent != scratch_parent or not scratch.name.startswith('aurora-glsl-'):
            raise RuntimeError('Unsafe temporary cleanup path')
        shutil.rmtree(str(scratch))
    print('PASS: {} standalone GLSL program-pair compile/link configurations'.format(len(configs)))
    print('LIMIT: no Iris patcher, Minecraft rendering, GPU execution or performance measurement.')

if __name__ == '__main__':
    main()
