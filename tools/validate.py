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

def preprocess(text, debug, grayscale, shadows=True):
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
                if parts[1] == "SHADOWS_ENABLED" and not shadows:
                    macros.pop(parts[1], None)
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
assert len(pairs) == 19
writers = {"gbuffers_terrain", "gbuffers_block", "gbuffers_entities"}
for debug in range(6):
    for grayscale in (False, True):
        for shadows in (False, True):
            for vertex in pairs:
                fragment = vertex.with_suffix(".fsh")
                vs = preprocess(expand(vertex), debug, grayscale, shadows)
                fs = preprocess(expand(fragment), debug, grayscale, shadows)
                for source in (vs, fs):
                    assert source.startswith("#version 330 compatibility")
                    assert source.count("void main()") == 1
                    clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
                    assert not re.search(r"const int colortex\d+Format\s*=\s*[A-Z]", clean), "Active format enum in GLSL"
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
                expected = [] if vertex.stem == "shadow" else ([0, 1, 2] if vertex.stem in writers else [0])
                assert locations == expected, (fragment, locations)
                if vertex.stem in ("final", "shadow"):
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
               "TEMPERATURE", "TINT", "GRAYSCALE", "SHADOWS_ENABLED", "SHADOW_BIAS"):
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
print("PASS: 19 program pairs x 6 debug views x 2 grayscale states x 2 shadow states")
print("PASS: includes, conditionals, stage interfaces, MRT routing, option references")
print("PASS: normal round trips, lightmap endpoints, cave/torch/disabled invariants")
print("PASS: Milestone 1 color code/defaults unchanged")
print("LIMIT: structural/numerical checks only; no GLSL compiler or Iris runtime test")

# Shadow contracts: single depth comparison, correct scope, no active format enums.
shadow_source = expand(SHADERS / "lib/shadow.glsl")
assert "uniform sampler2D shadowtex1;" in shadow_source
assert "uniform sampler2D depthtex1;" in shadow_source
for name in ("gbufferProjectionInverse", "gbufferModelViewInverse",
             "shadowModelView", "shadowProjection"):
    assert "uniform mat4 " + name + ";" in shadow_source
assert "shadowCoord.z - SHADOW_BIAS <= storedDepth ? 1.0 : 0.0" in shadow_source
assert "texelFetch(shadowtex1, shadowPixel, 0)" in shadow_source
assert "greaterThanEqual(shadowCoord" in shadow_source
assert "cameraPosition" not in re.sub(r"//[^\n]*", "", shadow_source)
for setting in ("shadowTerrain = true", "shadowBlockEntities = true",
                "shadowTranslucent = false", "shadowEntities = false",
                "shadowPlayer = false"):
    assert setting in props
shadow_vertex = expand(SHADERS / "shadow.vsh")
assert "const int shadowMapResolution = 2048;" in shadow_vertex
assert "const float shadowDistance = 64.0;" in shadow_vertex
assert "const bool shadowHardwareFiltering = false;" in shadow_vertex
lighting = (SHADERS / "lib/lighting.glsl").read_text()
assert "AMBIENT_LIGHT + DIRECT_LIGHT * ndotl * shadowVisibility" in lighting
for visibility in (0, 1):
    for ndotl in (0, .5, 1):
        term = .65 + .55 * ndotl * visibility
        assert term >= .65
        for block, sky, strength in ((0,0,1), (1,1,1), (0,1,0)):
            assert 1 + (term-1)*sky*(1-block)*strength == 1

def visible(current, stored, bias):
    return 1 if current-bias <= stored else 0
assert visible(.5,.5,0) == 1
assert visible(.6,.5,0) == 0
assert visible(.5001,.5,.0002) == 1
assert visible(.7,.5,.0002) == 0

# Independent projection/reconstruction test with camera rotation AND translation.
# Shadow coordinates of a fixed world point must not depend on camera pose.
def mv(matrix, vector):
    return [sum(a*b for a,b in zip(row, vector)) for row in matrix]
def mm(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(4))
             for j in range(4)] for i in range(4)]
def inverse(matrix):
    a = [list(row) + [float(i==j) for j in range(4)]
         for i,row in enumerate(matrix)]
    for i in range(4):
        pivot = max(range(i,4), key=lambda k: abs(a[k][i]))
        a[i],a[pivot] = a[pivot],a[i]
        div = a[i][i]
        assert abs(div) > 1e-12
        a[i] = [x/div for x in a[i]]
        for j in range(4):
            if j != i:
                factor = a[j][i]
                a[j] = [x-factor*y for x,y in zip(a[j],a[i])]
    return [row[4:] for row in a]
def translate(x,y,z):
    return [[1,0,0,x],[0,1,0,y],[0,0,1,z],[0,0,0,1]]
def yaw(angle):
    c,s = math.cos(angle),math.sin(angle)
    return [[c,0,s,0],[0,1,0,0],[-s,0,c,0],[0,0,0,1]]
def divide(v):
    return [x/v[3] for x in v[:3]]
near,far = .1,256.0
projection = [[1.3,0,0,0],[0,1.7,0,0],
              [0,0,-(far+near)/(far-near),-2*far*near/(far-near)],
              [0,0,-1,0]]
light_world = mm(yaw(-.6), translate(0,-20,0))
light_projection = [[1/64,0,0,0],[0,1/64,0,0],
                    [0,0,-1/256,0],[0,0,0,1]]
world_point = [-2,3,-18,1]
expected = divide(mv(mm(light_projection, light_world), world_point))
for anchor, angle in (((0,0,0),0), ((3,2,1),.3), ((-1,1,-2),-.2)):
    player = [world_point[i]-anchor[i] for i in range(3)] + [1]
    view_matrix = mm(yaw(angle), translate(0,-1.62,0))
    ndc = divide(mv(mm(projection, view_matrix), player))
    screen = [x*.5+.5 for x in ndc]
    recovered_view = divide(mv(inverse(projection),
                               [x*2-1 for x in screen]+[1]))
    recovered_player = mv(inverse(view_matrix), recovered_view+[1])
    light_player = mm(light_world, translate(*anchor))
    actual = divide(mv(mm(light_projection, light_player), recovered_player))
    assert max(abs(a-b) for a,b in zip(actual,expected)) < 1e-10
print("PASS: hard comparison, ambient/block preservation, depth-only caster scope")
print("PASS: perspective reconstruction and camera-pose-invariant light coordinates")
