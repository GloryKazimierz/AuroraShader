"""Read-only structural checks; NOT a full GLSL compiler. Python 3.6+."""
from pathlib import Path
import math
from itertools import product
from functools import lru_cache
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "shaders"
# Runtime-tested Milestone 3B: stable even after this branch is committed.
BASELINE = "5aa154dbce823e954f63d25f91f3acbb9566c9c9"
GRID_BASELINE = "220cf1b38e3e6d6cc65aa3ead0e8be671b10d148"
BIAS_BASELINE = "0d4bd999d4e48fb62e30aa05e914c1531469cde1"

@lru_cache(maxsize=None)
def expand(path, chain=()):
    path = path.resolve()
    assert path not in chain, "Include cycle: " + str(path)
    assert SHADERS.resolve() in path.parents, "Include escapes shader root"
    text = path.read_text(encoding="utf-8")
    def include(match):
        return expand(SHADERS / match[1].lstrip("/"), chain + (path,))
    return re.sub(r'^#include "([^"]+)"\s*$', include, text, flags=re.M)

def preprocess(text, debug, grayscale, shadows=True, filtering=1, softness=1.0, bias_mode=0):
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
                if parts[1] == "SHADOW_BIAS_MODE":
                    macros[parts[1]] = str(bias_mode)
                if parts[1] == "SHADOW_FILTER":
                    macros[parts[1]] = str(filtering)
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
    return "\n".join(result).replace("SHADOW_SOFTNESS", str(softness))

pairs = sorted(SHADERS.glob("*.vsh"))
assert len(pairs) == 19
writers = {"gbuffers_terrain", "gbuffers_block", "gbuffers_entities"}
for debug, grayscale, shadows, filtering, softness, bias_mode in product(
        range(7), (False,True), (False,True), (0,1,2,3), (0.0,.5,1.0,1.5,2.0), (0,1)):
    for vertex in pairs:
        fragment = vertex.with_suffix(".fsh")
        vs = preprocess(expand(vertex), debug, grayscale, shadows, filtering, softness, bias_mode)
        fs = preprocess(expand(fragment), debug, grayscale, shadows, filtering, softness, bias_mode)
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
               "TEMPERATURE", "TINT", "GRAYSCALE", "SHADOWS_ENABLED", "SHADOW_BIAS", "SHADOW_FILTER", "SHADOW_SOFTNESS"):
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
                                        BASELINE + ":" + relative]).decode()
    current = (ROOT / relative).read_text()
    assert baseline.replace("\r\n", "\n") == current.replace("\r\n", "\n")
print("PASS: 19 program pairs x 7 debug views x 2 bias modes x 2 grayscale states x 2 shadow states x 4 filters x 5 softness values")
print("PASS: includes, conditionals, stage interfaces, MRT routing, option references")
print("PASS: normal round trips, lightmap endpoints, cave/torch/disabled invariants")
print("PASS: Milestone 1 color code/defaults unchanged")
print("LIMIT: static structural/numerical validation is NOT Minecraft/Iris/GPU runtime validation")

# Shadow contracts: single depth comparison, correct scope, no active format enums.
shadow_source = expand(SHADERS / "lib/shadow.glsl")
assert "uniform sampler2D shadowtex1;" in shadow_source
assert "uniform sampler2D depthtex1;" in shadow_source
for name in ("gbufferProjectionInverse", "gbufferModelViewInverse",
             "shadowModelView", "shadowProjection"):
    assert "uniform mat4 " + name + ";" in shadow_source
assert "receiverDepth - effectiveBias <= storedDepth ? 1.0 : 0.0" in shadow_source
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

# PCF numerical oracle. Counts logical comparisons separately from texture reads:
# every out-of-map tap is lit and performs no fetch, but stays in the denominator.
MODES = ((0, 0, 1), (1, 1, 9), (2, 2, 25))
SOFTNESSES = (0.0, .5, 1.0, 1.5, 2.0)
# Read actual literal offsets; every matched offset must belong to a comparison.
poisson_source = preprocess(shadow_source,5,False,True,3)
POISSON_OFFSETS = tuple((float(x),float(y)) for x,y in re.findall(
    r"visibility \+= compareShadow\(shadowCoord\.xy \+ vec2\(\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\) \* tapStepUV, shadowCoord\.z, effectiveBias, mapSize\);",
    poisson_source))
assert len(POISSON_OFFSETS) == 8
assert len(set(POISSON_OFFSETS)) == 8
assert all(x*x+y*y <= 1 for x,y in POISSON_OFFSETS)
assert all(abs(sum(p[axis] for p in POISSON_OFFSETS)/8) < .001 for axis in (0,1))
assert min(math.hypot(a[0]-b[0],a[1]-b[1]) for i,a in enumerate(POISSON_OFFSETS)
           for b in POISSON_OFFSETS[i+1:]) > .6
assert {(x > 0,y > 0) for x,y in POISSON_OFFSETS} == {(False,False),(False,True),(True,False),(True,True)}

def reference_filter(grid, uv, current=.5, bias=.0002, mode=1, softness=1.0):
    assert mode in (0, 1, 2, 3)
    height, width = len(grid), len(grid[0])
    offsets = [(0, 0)] if mode == 0 else [
        (x, y) for y in range(-mode, mode+1) for x in range(-mode, mode+1)]
    if mode == 3:
        offsets = POISSON_OFFSETS
    lit, reads = 0.0, 0
    for x, y in offsets:
        u, v = uv[0]+x*softness/width, uv[1]+y*softness/height
        if not (0 <= u < 1 and 0 <= v < 1):
            lit += 1.0
            continue
        reads += 1
        lit += float(current-bias <= grid[int(v*height)][int(u*width)])
    return lit / len(offsets), len(offsets), reads

# A wide map keeps the 5x5/softness-2 footprint inside for interior tests.
size = 16
lit_map = [[.8]*size for _ in range(size)]
dark_map = [[.2]*size for _ in range(size)]
edge = [[.2 if x < 8 else .8 for x in range(size)] for _ in range(size)]
probe_uvs = ((.01,.01), (7.5/16,8.5/16), (8.5/16,8.5/16), (.99,.99))
for mode, radius, count in MODES:
    for softness in SOFTNESSES:
        for grid, expected in ((lit_map,1), (dark_map,0)):
            assert reference_filter(grid,(.5,.5),mode=mode,softness=softness) == (expected,count,count)
        for uv in probe_uvs:
            value, comparisons, reads = reference_filter(edge,uv,mode=mode,softness=softness)
            assert comparisons == count and 0 <= reads <= count
            assert 0 <= value <= 1
            if mode == 0:
                assert (value,comparisons,reads) == reference_filter(edge,uv,mode=0,softness=1)
        for uv in probe_uvs:
            assert reference_filter(edge,uv,mode=mode,softness=0)[0] == reference_filter(edge,uv,mode=0)[0]
    # These independent analytic results distinguish compare-then-average from
    # averaging depth first (which would produce only a binary edge result).
    for uv, expected in (((7.5/16,8.5/16), radius/(2*radius+1)),
                         ((8.5/16,8.5/16), (radius+1)/(2*radius+1))):
        assert abs(reference_filter(edge,uv,mode=mode)[0]-expected) < 1e-12
    # At every corner only (radius+1)^2 taps are in bounds: 1/1, 4/9, 9/25.
    for uv in ((.5/16,.5/16), (15.5/16,.5/16), (.5/16,15.5/16), (15.5/16,15.5/16)):
        value, comparisons, reads = reference_filter(dark_map,uv,mode=mode)
        expected_reads = (radius+1)**2
        assert (comparisons,reads) == (count,expected_reads)
        assert abs(value-(count-expected_reads)/count) < 1e-12
    # A straight map edge also treats taps beyond either axis as lit.
    assert abs(reference_filter(dark_map,(.5/16,.5),mode=mode)[0]-radius/(2*radius+1)) < 1e-12
for uv in ((-1e-6,.5),(1.0,.5),(.5,-1e-6),(.5,1.0)):
    assert reference_filter(dark_map,uv,mode=0) == (1,1,0)
assert reference_filter(dark_map,(0,0),mode=0) == (0,1,1)

# Tie the source's actual inclusive loop bounds and accumulation to the oracle.
# These are structural contracts, not a GLSL interpreter/compiler.
def function_body(source, name):
    match = re.search(r"\b" + name + r"\([^)]*\)\s*\{", source)
    assert match, "Missing function: " + name
    start, depth = match.end(), 1
    for index in range(start, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[start:index]
    raise AssertionError("Unclosed function: " + name)

def compact(source):
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S))

for mode, radius, count in MODES:
    for softness in SOFTNESSES:
        source = preprocess(shadow_source,5,False,True,mode,softness)
        body = compact(function_body(source,"filterShadow")).replace(",effectiveBias,", ",")
        assert body.count("compareShadow(") == 1
        assert "textureSize(shadowtex1,0)" in body
        if mode == 0:
            assert "for(" not in body and "kernelRadius" not in body
            assert "tapStepUV" not in body
            assert "returncompareShadow(shadowCoord.xy,shadowCoord.z,mapSize);" in body
        else:
            actual_radius = int(re.search(r"constintkernelRadius=(\d+);",body)[1])
            assert actual_radius == radius
            assert (2*actual_radius+1)**2 == count
            for axis in ('x','y'):
                assert "for(int{0}=-kernelRadius;{0}<=kernelRadius;++{0})".format(axis) in body
            assert body.count("for(") == 2
            assert "vec2texelSize=1.0/vec2(mapSize);" in body
            assert "tapStepUV=texelSize*"+str(softness)+";" in body
            assert "offsetUV=vec2(float(x),float(y))*tapStepUV;" in body
            assert "floatvisibility=0.0;" in body and "floatsampleCount=0.0;" in body
            assert "visibility+=compareShadow(shadowCoord.xy+offsetUV,shadowCoord.z,mapSize);" in body
            assert "sampleCount+=1.0;" in body
            assert "returnvisibility/sampleCount;" in body
            assert "texelFetch" not in body

# Compare complete tested functions, not a prefix or the moving HEAD commit.
previous_shadow = subprocess.check_output([
    "git","-C",str(ROOT),"show",BASELINE+":shaders/lib/shadow.glsl"]).decode()
def legacy_shadow_body(source, name):
    body = compact(function_body(source,name))
    if name == "compareShadow":
        return body.replace("effectiveBias", "SHADOW_BIAS")
    if name == "shadowVisibility":
        return body.replace("floateffectiveBias=effectiveShadowBias(normalView,lightDirectionView);", "").replace(
            "filterShadow(shadowCoord,effectiveBias)", "filterShadow(shadowCoord)")
    return body
for name in ("compareShadow","shadowVisibility","rawShadowDepth"):
    assert compact(function_body(previous_shadow,name)) == legacy_shadow_body(shadow_source,name), name
for relative in ("shaders/lib/position.glsl", "shaders/lib/lighting.glsl",
                 "shaders/lib/gbuffer_write.glsl",
                 "shaders/shadow.vsh", "shaders/shadow.fsh", "shaders/deferred.vsh",
                 "shaders/final.vsh"):
    baseline = subprocess.check_output(["git","-C",str(ROOT),"show",BASELINE+":"+relative]).decode()
    assert baseline.replace("\r\n","\n") == (ROOT/relative).read_text().replace("\r\n","\n"), relative
settings = (SHADERS/"lib/shadow_settings.glsl").read_text()
assert re.search(r"^#define SHADOWS_ENABLED(?: //.*)?$",settings,re.M)
assert re.search(r"^#define SHADOW_BIAS 0\.0002 //",settings,re.M)
assert re.search(r"^#define SHADOW_FILTER 1 // \[0 1 2 3\]",settings,re.M)
assert re.search(r"^#define SHADOW_SOFTNESS 1\.0 // \[0\.0 0\.5 1\.0 1\.5 2\.0\]",settings,re.M)
language = (SHADERS/"lang/en_us.lang").read_text()
for mode, label in ((0,"Hard"),(1,"3x3 PCF"),(2,"5x5 PCF"),(3,"Poisson PCF")):
    assert re.search(r"^value\.SHADOW_FILTER\."+str(mode)+"="+re.escape(label)+r"\s*$",language,re.M)
for option in ("SHADOW_FILTER","SHADOW_SOFTNESS"):
    assert re.search(r"^option\."+option+r"=.+$",language,re.M)
    assert option in props.split("screen =",1)[1].splitlines()[0].split()
assert "SHADOW_SOFTNESS" in props.split("sliders =",1)[1].splitlines()[0].split()
print("PASS: Hard/3x3/5x5 have 1/9/25 logical taps; bounded fetch counts checked")
print("PASS: all-lit, all-shadowed, 1/3-2/3 and 2/5-3/5 edges, all four corners")
print("PASS: all five softness values; zero equals Hard and Hard ignores softness")
print("PASS: pinned Milestone 3B transforms, bounds, caster scope, lighting and debug 0-5 unchanged")
print("PASS: four filter labels, UI references and defaults")

# Poisson contract: eight explicit comparisons, average of visibility not depths.
for softness in SOFTNESSES:
    body = compact(function_body(preprocess(shadow_source,5,False,True,3,softness),"filterShadow"))
    assert body.count("compareShadow(") == body.count("visibility+=") == 8
    assert "floatvisibility=0.0;" in body and "returnvisibility/8.0;" in body
    assert "vec2tapStepUV="+str(softness)+"/vec2(mapSize);" in body
    assert "for(" not in body and "texelFetch" not in body
    for grid, expected in ((lit_map,1),(dark_map,0)):
        assert reference_filter(grid,(.5,.5),mode=3,softness=softness) == (expected,8,8)
    for uv in probe_uvs:
        value, taps, reads = reference_filter(edge,uv,mode=3,softness=softness)
        assert 0 <= value <= 1 and taps == 8 and 0 <= reads <= 8
        assert reference_filter(edge,uv,mode=3,softness=0)[0] == reference_filter(edge,uv,mode=0)[0]
# Analytic tap counts at a vertical edge for the fixed pattern (not a copied sum).
assert reference_filter(edge,(7.5/16,8.5/16),mode=3) == (.25,8,8)
assert reference_filter(edge,(8.5/16,8.5/16),mode=3) == (.75,8,8)
diagonal = [[.8 if x+y >= 16 else .2 for x in range(size)] for y in range(size)]
assert reference_filter(diagonal,(8.5/16,8.5/16),mode=3) == (5/8,8,8)
assert reference_filter(dark_map,(.5/16,.5/16),mode=3) == (.5,8,4)
# Broader cases include non-square maps, fractional UVs, bias and every softness.
pattern = [[.2 if (x+2*y)%3 else .8 for x in range(16)] for y in range(12)]
for softness, u, v, bias in product(SOFTNESSES,(0,.013,.49,.5,.531,.999),
                                   (0,.02,.41,.5,.731,.999),(0,.0002,.002)):
    value, taps, reads = reference_filter(pattern,(u,v),mode=3,softness=softness,bias=bias)
    assert 0 <= value <= 1 and taps == 8 and 0 <= reads <= 8
    if softness == 0:
        assert value == reference_filter(pattern,(u,v),mode=0,bias=bias)[0]
# Prove each prior mode's preprocessed filter body is unchanged against M4.
grid_settings = subprocess.check_output([
    "git","-C",str(ROOT),"show",GRID_BASELINE+":shaders/lib/shadow_settings.glsl"]).decode()
grid_shadow = subprocess.check_output([
    "git","-C",str(ROOT),"show",GRID_BASELINE+":shaders/lib/shadow.glsl"]).decode()
for mode, _, _ in MODES:
    for softness in SOFTNESSES:
        old = preprocess(grid_settings+grid_shadow,5,False,True,mode,softness)
        new = preprocess(shadow_source,5,False,True,mode,softness)
        assert compact(function_body(old,"filterShadow")) == compact(function_body(new,"filterShadow")).replace(",effectiveBias,", ",")
print("PASS: Poisson 8 separated disk taps, centered pattern, compare-then-average")
print("PASS: Poisson lit/dark, straight/diagonal edge, boundary and zero-softness cases")
print("PASS: Hard/3x3/5x5 filter math preserved against Milestone 4 (shared bias parameter only)")

# M6: guard the narrowly scoped API adaptation against the latest M5 baseline.
def baseline_file(relative):
    return subprocess.check_output(["git","-C",str(ROOT),"show",BIAS_BASELINE+":"+relative]).decode()
legacy_shadow = baseline_file("shaders/lib/shadow.glsl")
legacy_settings = baseline_file("shaders/lib/shadow_settings.glsl")
for mode, softness, bias_mode in product(range(4),SOFTNESSES,(0,1)):
    before = preprocess(legacy_settings+legacy_shadow,5,False,True,mode,softness)
    after = preprocess(shadow_source,5,False,True,mode,softness,bias_mode)
    old_body = compact(function_body(before,"filterShadow"))
    new_body = compact(function_body(after,"filterShadow"))
    assert old_body == new_body.replace(",effectiveBias,", ",")
    # Reject per-tap recomputation or any alternate bias argument.
    assert new_body.count(",effectiveBias,mapSize)") == (8 if mode == 3 else 1)
receiver = compact(function_body(shadow_source,"shadowVisibility"))
assert receiver.count("effectiveShadowBias(normalView,lightDirectionView)") == 1
assert "returnfilterShadow(shadowCoord,effectiveBias);" in receiver
# Deferred only decodes its existing view normal once and passes it with the
# existing view-space celestial light. Lambert/ambient/block math stays pinned.
deferred = compact(function_body((SHADERS/"deferred.fsh").read_text(),"main"))
assert "shadowVisibility(pixel,normalView,shadowLightPosition)" in deferred
restored = deferred.replace("vec3normalView=decodeNormal(surface.rgb);", "").replace(
    "shadowVisibility(pixel,normalView,shadowLightPosition)", "shadowVisibility(pixel)").replace(
    "lightScene(scene.rgb,normalView,levels,visibility)",
    "lightScene(scene.rgb,decodeNormal(surface.rgb),levels,visibility)")
assert restored == compact(function_body(baseline_file("shaders/deferred.fsh"),"main"))
lighting_settings = (SHADERS/"lib/lighting_settings.glsl").read_text()
assert compact(lighting_settings) == compact(baseline_file("shaders/lib/lighting_settings.glsl"))
for debug in range(6):
    old = preprocess(baseline_file("shaders/lib/lighting_settings.glsl")+baseline_file("shaders/final.fsh"),debug,False)
    new = preprocess(lighting_settings+(SHADERS/"final.fsh").read_text(),debug,False)
    assert compact(function_body(old,"main")) == compact(function_body(new,"main")).replace(
        "shadowVisibility(pixel,normalView,shadowLightPosition)", "shadowVisibility(pixel)")
restored_props = props.replace("SHADOW_BIAS SHADOW_BIAS_MODE SHADOW_BIAS_MIN SHADOW_BIAS_MAX SHADOW_FILTER",
                              "SHADOW_BIAS SHADOW_FILTER").replace(
    "SHADOW_BIAS SHADOW_BIAS_MIN SHADOW_BIAS_MAX LIGHTING_STRENGTH", "SHADOW_BIAS LIGHTING_STRENGTH")
assert restored_props == baseline_file("shaders/shaders.properties").replace("\r\n","\n")

bias_source = (SHADERS/"lib/shadow_bias.glsl").read_text()
constant_source = preprocess(settings+bias_source,0,False,bias_mode=0)
assert compact(function_body(constant_source,"effectiveShadowBias")) == "returnSHADOW_BIAS;"
angle_source = preprocess(settings+bias_source,0,False,bias_mode=1)
assert compact(function_body(angle_source,"effectiveShadowBias")) == (
    "vec2bounds=shadowBiasBounds();floatangleFactor=1.0-shadowBiasNdotL(normalView,lightDirectionView);"
    "returnclamp(mix(bounds.x,bounds.y,angleFactor),bounds.x,bounds.y);")
assert "return clamp(dot(normalUnit, lightUnit), 0.0, 1.0);" in bias_source
for term in ("isnan(normalView)","isinf(normalView)","isnan(lightDirectionView)","isinf(lightDirectionView)",
             "normalScale <= 1e-6 || lightScale <= 1e-6", "normalize(normalView / normalScale)",
             "normalize(lightDirectionView / lightScale)", "if (span <= 1e-8) return 0.0;"):
    assert term in bias_source
assert compact(function_body(bias_source,"shadowBiasBounds")) == (
    "returnclamp(vec2(min(SHADOW_BIAS_MIN,SHADOW_BIAS_MAX),max(SHADOW_BIAS_MIN,SHADOW_BIAS_MAX)),0.0,0.002);")

def clamp(x,lo,hi):
    return min(hi,max(lo,x))
def bias_bounds(lo,hi):
    return clamp(min(lo,hi),0,.002),clamp(max(lo,hi),0,.002)
def receiver_ndotl(normal,light):
    if not all(math.isfinite(v) for v in normal+light):
        return 0.0
    ns,ls = max(map(abs,normal)),max(map(abs,light))
    if ns <= 1e-6 or ls <= 1e-6:
        return 0.0
    n,l = norm([v/ns for v in normal]),norm([v/ls for v in light])
    return clamp(sum(a*b for a,b in zip(n,l)),0,1)
def receiver_bias(ndotl,mode=1,constant=.0002,lo=.0001,hi=.0005):
    if mode == 0:
        return constant
    lo,hi = bias_bounds(lo,hi)
    return clamp(lo+(hi-lo)*(1-clamp(ndotl,0,1)),lo,hi)
def debug_bias(bias,lo,hi):
    lo,hi = bias_bounds(lo,hi)
    return 0 if hi-lo <= 1e-8 else clamp((bias-lo)/(hi-lo),0,1)
BIAS_VALUES = (0,.00005,.0001,.0002,.0005,.001,.002)
for lo,hi in product(BIAS_VALUES,repeat=2):
    minimum,maximum = bias_bounds(lo,hi)
    results = [receiver_bias(n,lo=lo,hi=hi) for n in (1,.75,.5,.25,0)]
    assert all(math.isfinite(x) and minimum <= x <= maximum for x in results)
    assert results == sorted(results)
    assert abs(results[0]-minimum) < 1e-12 and abs(results[-1]-maximum) < 1e-12
    for result in results:
        assert math.isfinite(debug_bias(result,lo,hi)) and 0 <= debug_bias(result,lo,hi) <= 1
    if lo == hi:
        assert debug_bias(lo,lo,hi) == 0
assert bias_bounds(-.001,.1) == (0,.002)
assert receiver_bias(-1) == receiver_bias(0)
assert receiver_bias(2) == receiver_bias(1)
assert abs(debug_bias(.0002,.0001,.0005)-.25) < 1e-12
# Directions use the same space, remain normalized, and have finite fallbacks.
for n,expected in (((0,1,0),1),((1,0,0),0),((0,-1,0),0),((0,0,0),0),
                   ((0,1e30,0),1),((0,1e-30,0),0),((float('nan'),0,0),0),
                   ((float('inf'),0,0),0)):
    value = receiver_ndotl(n,(0,100,0))
    assert math.isfinite(value) and value == expected
    assert math.isfinite(receiver_bias(value))
for bad_light in ((0,0,0),(float('inf'),0,0),(0,float('nan'),0)):
    assert receiver_ndotl((0,1,0),bad_light) == 0
n,l = norm((1,2,3)),norm((-2,3,1))
for angle in (-2,-.3,0,.5,2):
    rotated_n = tuple(mv(yaw(angle),list(n)+[0])[:3])
    rotated_l = tuple(mv(yaw(angle),list(l)+[0])[:3])
    assert abs(receiver_ndotl(rotated_n,rotated_l)-receiver_ndotl(n,l)) < 1e-12
# Comparison-sensitive depths and both signs of the edge avoid trivial tests.
for mode,softness,constant in product(range(4),SOFTNESSES,BIAS_VALUES):
    for uv in probe_uvs:
        for depth in (.2,.20005,.2002,.8,.8002):
            for facing in (1,.75,.5,.25,0):
                value = receiver_bias(facing,mode=0,constant=constant)
                assert reference_filter(edge,uv,current=depth,bias=value,mode=mode,softness=softness) == reference_filter(
                    edge,uv,current=depth,bias=constant,mode=mode,softness=softness)
                angled = receiver_bias(facing)
                visibility = reference_filter(edge,uv,current=depth,bias=angled,mode=mode,softness=softness)[0]
                assert 0 <= visibility <= 1
                if softness == 0:
                    assert visibility == reference_filter(edge,uv,current=depth,bias=angled,mode=0)[0]
for option,default in (("SHADOW_BIAS_MODE","0"),("SHADOW_BIAS_MIN","0.0001"),("SHADOW_BIAS_MAX","0.0005")):
    assert re.search(r"^#define "+option+" "+re.escape(default)+r" //",settings,re.M)
    assert re.search(r"^option\."+option+r"=.+$",language,re.M)
    assert option in props.split("screen =",1)[1].splitlines()[0].split()
assert "#define SHADOW_BIAS_MODE 0 // [0 1]" in settings
assert "value.SHADOW_BIAS_MODE.0=Constant" in language
assert "value.SHADOW_BIAS_MODE.1=Angle-Aware" in language
assert "[0 1 2 3 4 5 6]" in lighting_settings
assert "value.DEBUG_VIEW.6=Effective Shadow Bias" in language
for mode in (0,1):
    debug_source = preprocess(expand(SHADERS/"final.fsh"),6,False,bias_mode=mode)
    debug_main = compact(function_body(debug_source,"main"))
    assert "gradeColor" not in debug_main
    assert "vec3debugColor=vec3(0.0);" in debug_main and "surface.a>0.5" in debug_main
    assert "texelFetch(depthtex1,pixel,0).r<1.0" in debug_main
    assert "shadowBiasDebug(effectiveShadowBias(normalView,shadowLightPosition))" in debug_main
print("PASS: M6 shared bias for 1/9/25/8 taps; constant mode exactly preserves M5 filter/receiver math")
print("PASS: angle bias bounds, monotonicity, reversed/equal bounds, invalid vectors and camera rotation")
print("PASS: legacy direct/ambient/block lighting and debug 0-5 preserved; safe ungraded debug 6")
print("LIMIT: static structural/numerical validation is NOT Minecraft/Iris/GPU runtime validation")
