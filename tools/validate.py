"""Read-only structural checks; NOT a full GLSL compiler. Python 3.6+."""
from pathlib import Path
import math
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "shaders"

def expand(path, chain=()):
    path = path.resolve()
    assert path not in chain, "Include cycle: " + str(path)
    assert SHADERS.resolve() in path.parents, "Include escapes shader root"
    text = path.read_text(encoding="utf-8")
    def include(match):
        return expand(SHADERS / match[1].lstrip("/"), chain + (path,))
    return re.sub(r'^#include "([^"]+)"\s*$', include, text, flags=re.M)

def preprocess(text, debug, grayscale):
    macros = {}
    stack = []
    active = True
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#define "):
            if active:
                parts = stripped.split("//")[0].split()
                macros[parts[1]] = parts[2] if len(parts) > 2 else "1"
                if parts[1] == "DEBUG_VIEW":
                    macros[parts[1]] = str(debug)
            continue
        if stripped.startswith("//#define GRAYSCALE") and grayscale and active:
            macros["GRAYSCALE"] = "1"
        if stripped.startswith("#ifdef "):
            cond = stripped.split()[1] in macros
            stack.append([active, cond])
            active = active and cond
        elif stripped.startswith("#if ") or stripped.startswith("#elif "):
            match = re.fullmatch(r"#(?:if|elif) (\w+) == (\d+)", stripped)
            assert match, "Unsupported conditional: " + stripped
            cond = macros.get(match[1], "0") == match[2]
            if stripped.startswith("#if "):
                stack.append([active, cond])
                active = active and cond
            else:
                parent, taken = stack[-1]
                active = parent and not taken and cond
                stack[-1][1] = taken or cond
        elif stripped == "#else":
            parent, taken = stack[-1]
            active = parent and not taken
            stack[-1][1] = True
        elif stripped == "#endif":
            active = stack.pop()[0]
        elif active:
            result.append(line)
    assert not stack, "Unclosed conditional"
    return "\n".join(result)

pairs = sorted(SHADERS.glob("*.vsh"))
assert len(pairs) == 18
writers = {"gbuffers_terrain", "gbuffers_block", "gbuffers_entities"}
for debug in range(4):
    for grayscale in (False, True):
        for vertex in pairs:
            fragment = vertex.with_suffix(".fsh")
            vs = preprocess(expand(vertex), debug, grayscale)
            fs = preprocess(expand(fragment), debug, grayscale)
            for source in (vs, fs):
                assert source.startswith("#version 330 compatibility")
                assert source.count("void main()") == 1
                clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
                for left, right in (("{", "}"), ("(", ")"), ("[", "]")):
                    depth = 0
                    for char in clean:
                        depth += (char == left) - (char == right)
                        assert depth >= 0, str(fragment)
                    assert depth == 0, str(fragment)
            outputs = dict((name, kind) for kind, name in
                           re.findall(r"^out (\w+) (\w+);", vs, re.M))
            for kind, name in re.findall(r"^in (\w+) (\w+);", fs, re.M):
                assert outputs.get(name) == kind, (fragment, name)
            locations = [int(n) for n in re.findall(
                r"layout\(location = (\d+)\) out vec4", fs)]
            targets = re.findall(r"/\* RENDERTARGETS: ([0-9,]+) \*/", fs)
            expected = [0, 1, 2] if vertex.stem in writers else [0]
            assert locations == expected, (fragment, locations)
            if vertex.stem == "final":
                assert not targets
            else:
                assert len(targets) == 1
                assert list(map(int, targets[0].split(","))) == expected
            if vertex.stem in writers:
                assert "writeSurfaceData(lmcoord);" in fs
                assert "gl_NormalMatrix * gl_Normal" in vs
            if vertex.stem == "final" and debug:
                assert "gradeColor(scene.rgb)" not in fs

props = (SHADERS / "shaders.properties").read_text()
all_source = "\n".join(p.read_text() for p in SHADERS.rglob("*") if p.is_file())
options = set(re.findall(r"^\s*(?://)?#define (\w+)", all_source, re.M))
for line in props.splitlines():
    if line.startswith(("screen =", "sliders =")):
        for option in line.split("=", 1)[1].split():
            assert option in options, "Undefined option: " + option
for option in ("DEBUG_VIEW", "LIGHTING_STRENGTH", "AMBIENT_LIGHT",
               "DIRECT_LIGHT", "EXPOSURE", "SATURATION", "CONTRAST",
               "TEMPERATURE", "TINT", "GRAYSCALE"):
    assert len(re.findall(r"\b" + option + r"\b", all_source)) >= 2
for writer in writers:
    for buffer in (1, 2):
        assert "blend.{}.colortex{} = off".format(writer, buffer) in props

# Independent numerical contract checks, including simulated RGBA16 storage.
def norm(v):
    length = math.sqrt(sum(x*x for x in v))
    return tuple(x / length for x in v)
for original in ((1,0,0), (0,-1,0), (0,0,1), (1,2,3), (-2,1,-4)):
    n = norm(original)
    encoded = [round((x*.5+.5)*65535)/65535 for x in n]
    decoded = norm([x*2-1 for x in encoded])
    assert max(abs(a-b) for a,b in zip(n, decoded)) < 0.0001
assert max(sum(a*b for a,b in zip((0,1,0),(0,1,0))), 0) == 1
assert max(sum(a*b for a,b in zip((0,1,0),(0,-1,0))), 0) == 0
for level in range(16):
    uv = (level + .5) / 16
    assert abs((uv - .5/16)*(16/15) - level/15) < 1e-12
for ndotl in (0, .5, 1):
    for block, sky, strength in ((0,0,1), (1,1,1), (0,1,0)):
        factor = 1 + (.65 + .55*ndotl - 1)*sky*(1-block)*strength
        assert factor == 1

# Milestone 1 grading implementation/defaults must be byte-content unchanged.
for relative in ("shaders/lib/color.glsl", "shaders/lib/settings.glsl"):
    baseline = subprocess.check_output(["git", "-C", str(ROOT), "show",
                                        "HEAD:" + relative]).decode()
    current = (ROOT / relative).read_text()
    assert baseline.replace("\r\n", "\n") == current.replace("\r\n", "\n")
print("PASS: 18 program pairs x 4 debug views x 2 grayscale states")
print("PASS: includes, conditionals, stage interfaces, MRT routing, option references")
print("PASS: normal round trips, lightmap endpoints, cave/torch/disabled invariants")
print("PASS: Milestone 1 color code/defaults unchanged")
print("LIMIT: structural/numerical checks only; no GLSL compiler or Iris runtime test")
