"""Validate the current pack's optical routing, legacy paths and test world.

Use --historical to also replay the original M0 suite on its pinned Git tree.
Offline compile/link and real driver rendering have separate entry points.
"""
import argparse
from functools import lru_cache
from io import BytesIO
from itertools import product
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from compile_glsl import ROOT, SHADERS, expand
from validate_settings_profiles import (option_definitions, parse_properties, parse_language,
                                       load_profiles, menu_options)
from validate_water_lab import main as test_lab

BASE = '648c5fcfb13dbe5d47bfbb07db3b903a882fe6bc'
FEATURE = 'IRIS_FEATURE_PER_BUFFER_BLENDING'
WRITERS = {'gbuffers_terrain', 'gbuffers_block', 'gbuffers_entities'}
BLOOM = {'composite': 'composite1', 'composite1': 'composite2',
         'composite2': 'composite3', 'composite3': 'composite4'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def archive(*paths):
    return ZipFile(BytesIO(subprocess.check_output(
        ['git', '-C', str(ROOT), 'archive', '--format=zip', BASE, *paths])))


def test_history():
    # Use the historical validator and inputs as authored. Git history queries
    # from its temporary root use the same read-only object database.
    db = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute',
                                  '--git-common-dir'], text=True).strip()
    parent = ROOT.parent.resolve()
    with TemporaryDirectory(prefix='aurora-legacy-', dir=parent) as directory:
        dest = Path(directory).resolve()
        require(dest.parent == parent and dest.name.startswith('aurora-legacy-'), 'Unexpected scratch path')
        with archive('shaders', 'tools') as tree:
            for name in tree.namelist():
                require(dest in (dest / name).resolve().parents, 'Invalid historical archive path')
            tree.extractall(dest)
        environment = dict(os.environ, GIT_DIR=db, GIT_WORK_TREE=str(dest))
        subprocess.run([sys.executable, '-B', str(dest/'tools/validate.py')], cwd=dest,
                       env=environment, check=True)


def condition(expr, macros):
    def clause(token):
        token = token.strip()
        defined = re.fullmatch(r'defined\s*\(\s*(\w+)\s*\)', token)
        if defined:
            return defined[1] in macros
        match = re.fullmatch(r'(\w+)\s*(==|!=|>)\s*(\d+)', token)
        require(match, 'Unsupported validation condition: ' + token)
        if match[2] == '>':
            return int(macros.get(match[1],'0')) > int(match[3])
        equal = str(macros.get(match[1], '0')) == match[3]
        return equal if match[2] == '==' else not equal
    return any(all(clause(c) for c in group.split('&&')) for group in expr.split('||'))


@lru_cache(maxsize=256)
def parsed(source):
    lines = []
    # Keep the exact Iris line directives inside comments. Strip explanatory prose.
    for line in source.splitlines():
        line = line.strip()
        if line.startswith('#'):
            line = line.partition('//')[0].rstrip()
        if not line or line.startswith('//'):
            if not line.startswith('//#define '):
                continue
        if line.startswith('/* RENDERTARGETS:') or line.startswith('const int colortex'):
            lines.append(('data', line))
        elif line.startswith(('#if ', '#elif ', '#ifdef ', '#ifndef ', '#define ', '//#define ')):
            op, rest = line.split(None, 1)
            lines.append((op, rest.split('//')[0].strip()))
        elif line in ('#else', '#endif'):
            lines.append((line, ''))
        else:
            body = line.split('//')[0].strip()
            if body:
                lines.append(('data', body))
    return lines


def select(source, options, starting=None):
    # Conditional evaluator for this pack's finite grammar. Fail on any new
    # condition we cannot evaluate. glslang and OpenGL compile the full GLSL.
    macros = dict(starting or {})
    if options.get(FEATURE):
        macros[FEATURE] = '1'
    selected, stack = [], []
    active = True
    for op, arg in parsed(source):
        if op in ('#if', '#ifdef', '#ifndef'):
            value = False
            if active:
                if op == '#if':
                    value = condition(arg, macros)
                elif op == '#ifdef':
                    value = arg in macros
                else:
                    value = arg not in macros
            stack.append((active, value))
            active = active and value
        elif op == '#elif':
            parent, taken = stack[-1]
            active = parent and not taken and condition(arg, macros)
            stack[-1] = (parent, taken or active)
        elif op == '#else':
            parent, taken = stack[-1]
            active = parent and not taken
            stack[-1] = (parent, True)
        elif op == '#endif':
            active = stack.pop()[0]
        elif active and op in ('#define', '//#define'):
            name, *value = arg.split(maxsplit=1)
            replacement = options.get(name, value[0] if value else op == '#define')
            if replacement is False:
                macros.pop(name, None)
            else:
                macros[name] = '1' if replacement is True else str(replacement)
        elif active:
            selected.append(arg)
    require(not stack, 'Unclosed conditional')
    return '\n'.join(selected), macros


def routing(source):
    matches = re.findall(r'/\* RENDERTARGETS: ([\d,]+) \*/', source)
    require(len(matches) <= 1, 'Multiple active draw-buffer declarations')
    return tuple(map(int, matches[0].split(','))) if matches else ()


def semantic_lines(source):
    return tuple(line for line in source.splitlines() if line not in ('/*', '*/'))


def test_pack():
    options = option_definitions(ROOT)
    defaults = {key: spec['default'] for key, spec in options.items()}
    require(defaults['WATER_OPTICS'] == '0' and defaults['WATER_CLARITY'] == '1.0', 'Water defaults')
    props = (SHADERS/'shaders.properties').read_text(encoding='utf-8')
    # Ordinary property comments can contain English text starting with #.
    props = '\n'.join(line for line in props.splitlines() if not line.startswith('# '))
    entries = sorted(p.stem for p in SHADERS.glob('*.vsh'))
    require(set(entries) == {p.stem for p in SHADERS.glob('*.fsh')}, 'Unpaired programs')
    geometry = {p for p in entries if p.startswith('gbuffers_')}
    profiles = load_profiles(ROOT)
    require(profiles and all('WATER_OPTICS' not in p for p in profiles.values()), 'Unexpected profile override')
    checks = 0
    with archive('shaders') as tree:
        @lru_cache(maxsize=None)
        def prior(name):
            source = tree.read('shaders/'+name).decode('utf-8')
            return re.sub(r'^#include "([^"]+)"\s*$',
                          lambda m: prior(m[1].lstrip('/')), source, flags=re.M)
        for before, after in BLOOM.items():
            for suffix in ('.fsh', '.vsh'):
                require(tree.read('shaders/'+before+suffix) == (SHADERS/(after+suffix)).read_bytes(),
                        'Changed bloom program ' + after + suffix)
        old = {Path(n).stem for n in tree.namelist() if n.endswith('.vsh')}
        require(set(entries) == old | {'composite4', 'deferred1', 'prepare1'}, 'Unexpected pass set')
        # Cover every former display selection, both storage modes and all genuine
        # opt-out routes. Compare BOTH live stages, directives and referenced macro
        # values against M0, with the four bloom entry names mapped above.
        cases = [dict(DEBUG_VIEW=j, SCENE_COLOR_MODE=m) for j,m in product(range(10), (0,1))]
        cases.extend([{FEATURE: True, 'WATER_OPTICS': 0}, {'WATER_OPTICS': 1},
                      {FEATURE: True, 'WATER_OPTICS': 1, 'WATER_STYLE': 0},
                      {FEATURE: True, 'WATER_OPTICS': 1, 'DEBUG_VIEW': 9},
                      {FEATURE: True, 'WATER_OPTICS': 1, 'SCENE_COLOR_MODE': 0}])
        for name in sorted(old):
            for ext in ('.vsh','.fsh'):
                old_source = prior(name+ext)
                new_source = expand(SHADERS/(BLOOM.get(name,name)+ext))
                for case in cases:
                    a, ma = select(old_source, case)
                    b, mb = select(new_source, case)
                    require(semantic_lines(a) == semantic_lines(b), f'Legacy stage differs: {name}{ext} {case}')
                    words = set(re.findall(r'\b\w+\b', a))
                    require(all(ma.get(k)==mb.get(k) for k in words), f'Legacy macro differs: {name}{ext} {case}')
                    checks += 1
    print(f'PASS: {checks} live legacy-stage comparisons, four byte-identical bloom pairs', flush=True)
    for supported, enabled, style, hdr, debug in product((False,True),(0,1),(0,1),(0,1),(0,7,8,9)):
        case = {FEATURE:supported, 'WATER_OPTICS':enabled, 'WATER_STYLE':style, 'SCENE_COLOR_MODE':hdr, 'DEBUG_VIEW':debug}
        active = bool(supported and enabled and style and hdr and not debug)
        values = dict(defaults, **case)
        values.pop(FEATURE)
        properties = parse_properties(select(props, case, values)[0])
        require(properties['iris.features.optional']=='PER_BUFFER_BLENDING', 'Missing optional feature')
        require((properties.get('program.composite.enabled', 'true')=='true') == active, 'Resolve scheduling')
        require(menu_options(properties, options)[0].count('WATER_OPTICS') == 1, 'Water option placement')
        for name in geometry | {'deferred','composite'}:
            source, macros = select(expand(SHADERS/(name+'.fsh')), case)
            require(('AURORA_WATER_OPTICS_ACTIVE' in macros) == active, 'Shader/property option mismatch')
            route = routing(source)
            if name in geometry:
                require((8 in route) == active, 'Ownership target in '+name)
                blend = properties.get('blend.'+name+'.colortex8')
                expected = ('off' if name in WRITERS else 'ONE ONE ONE ONE') if active else None
                require(blend == expected, 'Unexpected blend for '+name)
            elif name == 'deferred':
                require(route == ((0,5,6,7,8,9) if active else (0,5,6)), 'Snapshot routing')
                if active:
                    for index, fmt in ((7,'RGBA32F'),(8,'RGBA8'),(9,'R16F')):
                        require(f'const int colortex{index}Format = {fmt};' in source, 'Attachment format')
            else:
                require(route == (0,), 'Full resolution optical output')
        require(('blend.gbuffers_water.colortex7' in properties) == (supported and (active or debug in (7,8,9))),
                'Surface record blend mode')
    for supported, optics, tiles, ssr, debug, hdr, style in product((0,1), repeat=7):
        case={FEATURE:bool(supported),'WATER_OPTICS':optics,'WATER_TRACE_TILES':tiles,
              'WATER_SCREEN_REFLECTIONS':ssr,'DEBUG_VIEW':8*debug,'SCENE_COLOR_MODE':hdr,'WATER_STYLE':style}
        values=dict(defaults, **case)
        values.pop(FEATURE)
        selected=parse_properties(select(props,case,values)[0])
        active=bool(supported and optics and tiles and ssr and not debug and hdr and style)
        require((selected.get('program.deferred1.enabled','true')=='true')==active, 'Depth-bound scheduling')
        require(selected.get('size.buffer.colortex10')==('0.125 0.125' if active else None), 'Depth-bound size')
        source,_=select(expand(SHADERS/'deferred1.fsh'),case)
        require(routing(source)==((10,) if active else (0,)), 'Depth-bound target')
        require(('const int colortex10Format = R32F;' in source)==active, 'Depth-bound format')
    print('PASS: 128 reflection depth-bound scheduling and buffer checks')
    for support,optics,detail,contacts,style,hdr,debug in product((0,1),repeat=7):
        case={FEATURE:bool(support),'WATER_OPTICS':optics,'WATER_SURFACE_DETAIL':detail,
              'WATER_INTERACTIONS':contacts,'WATER_STYLE':style,'SCENE_COLOR_MODE':hdr,'DEBUG_VIEW':debug}
        active=bool(support and optics and detail and contacts and style and hdr and not debug)
        values=dict(defaults,**case)
        values.pop(FEATURE)
        selected=parse_properties(select(props,case,values)[0])
        require((selected.get('program.prepare1.enabled','true')=='true')==active,'Contact scheduling')
        require(selected.get('size.buffer.colortex15')==('16 2' if active else None),'Contact storage dimensions')
        text,_=select(expand(SHADERS/'prepare1.fsh'),case)
        require(routing(text)==((15,) if active else (0,)),'Contact attachment')
        require(('const bool colortex15Clear = false;' in text)==active,'Contact persistence')
    print('PASS: 128 contact/history setting combinations')
    for language in ('en_us','zh_cn'):
        labels = parse_language((SHADERS/'lang'/(language+'.lang')).read_text(encoding='utf-8'))
        require(all('option.'+key in labels for key in options), 'Missing translation for '+language)
    print('PASS: 64 live capability/setting combinations, writer routing, formats, profiles and translations')


def test_foam_routes():
    options=option_definitions(ROOT)
    require(options['WATER_FOAM']['default']=='0','Foam must remain opt-in')
    require(all('WATER_FOAM' not in p for p in load_profiles(ROOT).values()),'Unrequested foam profile override')
    source=expand(SHADERS/'composite.fsh')
    checks=0
    for foam,support,optics,style,hdr,debug in product((0,1,2),(False,True),(0,1),(0,1),(0,1),(0,7)):
        case=dict(WATER_FOAM=foam,IRIS_FEATURE_PER_BUFFER_BLENDING=support,WATER_OPTICS=optics,
                  WATER_STYLE=style,SCENE_COLOR_MODE=hdr,DEBUG_VIEW=debug)
        selected,macros=select(source,case)
        active=bool(foam and support and optics and style and hdr and not debug)
        history=active and foam==2
        require(('AURORA_WATER_FOAM_ACTIVE' in macros)==active,'Foam gate mismatch')
        require(('AURORA_WATER_FOAM_HISTORY' in macros)==history,'Foam history gate mismatch')
        require(routing(selected)==((0,13,14) if history else (0,)),'Foam MRT routing')
        for text in ('const int colortex13Format = RGBA16F;','const int colortex14Format = RG32F;',
                     'const bool colortex13Clear = false;','const bool colortex14Clear = false;',
                     'uniform sampler2D colortex13;','uniform sampler2D colortex14;'):
            require((text in selected)==history,'Unexpected persistent attachment declaration')
        checks+=1
    print(f'PASS: {checks} opt-in foam routing, persistent formats and default-off checks',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical', action='store_true', help='Also replay the complete pinned M0 suite')
    args = parser.parse_args()
    test_pack()
    test_foam_routes()
    test_lab()
    if args.historical:
        print('Replaying original M0 checks from '+BASE, flush=True)
        test_history()
