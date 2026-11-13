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
    lines[1:1] = ['#define MC_RENDER_STAGE_STARS 5', '#define MC_RENDER_STAGE_VOID 6']
    return '\n'.join(lines) + '\n'

def configurations():
    for path in sorted(SHADERS.glob('*.vsh')):
        yield path.stem, {}
    for style, blend, sunset, night in product((0, 1), (0.0, 1.0), (0.0, 1.5), (0.5, 2.0)):
        yield 'gbuffers_skybasic', dict(SKY_STYLE=style, SKY_BLEND=blend,
                                       SUNSET_GLOW=sunset, NIGHT_BRIGHTNESS=night)
    for palette, bias, filtering, shadows, strength in product((0, 1), (0, 1), range(4), (False, True), (0.0, 1.0)):
        yield 'deferred', dict(LIGHT_PALETTE=palette, SHADOW_BIAS_MODE=bias,
                               SHADOW_FILTER=filtering, SHADOWS_ENABLED=shadows,
                               LIGHTING_STRENGTH=strength)
    for debug, filtering, bias in product(range(7), range(4), (0, 1)):
        yield 'final', dict(DEBUG_VIEW=debug, SHADOW_FILTER=filtering, SHADOW_BIAS_MODE=bias)
    yield 'final', dict(GRAYSCALE=True)

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
