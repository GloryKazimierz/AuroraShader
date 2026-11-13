"""M10 bloom source contracts and independent numerical oracles; no GPU execution."""
import math
import re
import struct
import subprocess
from functools import lru_cache
from itertools import product

HALF_MAX = 65504.0
KERNEL = tuple(math.factorial(8)/(math.factorial(i)*math.factorial(8-i)*256) for i in range(9))
M9_BASELINE = '3c5a2ab0cd90aff32d5145dce7ea461917d886af'
BLOOM_PROGRAMS = ('composite', 'composite1', 'composite2', 'composite3')
BLOOM_TARGETS = dict(zip(BLOOM_PROGRAMS, (3,4,3,0)))
BLOOM_PROPERTIES = '''
# M10 bloom scratch attachments: actual half resolution, default per-pass flips.
size.buffer.colortex3 = 0.5 0.5
size.buffer.colortex4 = 0.5 0.5
screen.BLOOM = BLOOM_ENABLED BLOOM_STRENGTH BLOOM_THRESHOLD BLOOM_SOFT_KNEE
screen.BLOOM.columns = 2
'''


def restore_bloom_properties(source):
    """Remove only the exact M10 suffix/menu additions before historical pins."""
    assert source.endswith(BLOOM_PROPERTIES)
    assert source.count('screen = [BLOOM] ') == 1
    assert source.count('sliders = BLOOM_STRENGTH BLOOM_THRESHOLD BLOOM_SOFT_KNEE ') == 1
    return source[:-len(BLOOM_PROPERTIES)].replace('screen = [BLOOM] ', 'screen = ', 1).replace(
        'sliders = BLOOM_STRENGTH BLOOM_THRESHOLD BLOOM_SOFT_KNEE ', 'sliders = ', 1)


def bounded_channel(x):
    return 0.0 if math.isnan(x) else min(HALF_MAX, max(0.0, x))


def extract_bright(rgb, threshold=1.0, knee=.5):
    rgb = tuple(bounded_channel(x) for x in rgb)
    peak = max(rgb)
    threshold = max(threshold, 0.0)
    width = threshold*min(1.0,max(knee,0.0))
    soft = min(max(peak-threshold+width, 0.0), 2*width)
    soft = soft*soft/(4*width) if width > 0.0 else 0.0
    contribution = max(peak-threshold, soft, 0.0)
    ratio = contribution/max(peak, 1e-6)
    return tuple(bounded_channel(x*ratio) for x in rgb)


def overlap(lo, hi, pixel):
    return max(0.0, min(hi, pixel+1)-max(lo, pixel))


def area_downsample(image, output_width, output_height, transform=lambda x: x):
    """Exact source rectangle overlap integration, independent of fixed tap loops."""
    height, width = len(image), len(image[0])
    output = []
    for y in range(output_height):
        row = []
        y0, y1 = y*height/output_height, (y+1)*height/output_height
        for x in range(output_width):
            x0, x1 = x*width/output_width, (x+1)*width/output_width
            total = [0.0, 0.0, 0.0]
            for sy in range(height):
                for sx in range(width):
                    weight = overlap(x0,x1,sx)*overlap(y0,y1,sy)
                    value = transform(image[sy][sx])
                    for c in range(3):
                        total[c] += value[c]*weight
            row.append(tuple(c/((x1-x0)*(y1-y0)) for c in total))
        output.append(row)
    return output


def blur_axis(image, horizontal):
    height, width = len(image), len(image[0])
    result = []
    for y in range(height):
        row = []
        for x in range(width):
            total = [0.0,0.0,0.0]
            for i, weight in enumerate(KERNEL):
                sx = min(width-1,max(0,x+i-4)) if horizontal else x
                sy = y if horizontal else min(height-1,max(0,y+i-4))
                for c in range(3):
                    total[c] += image[sy][sx][c]*weight
            row.append(tuple(total))
        result.append(row)
    return result


def bilinear(image, u, v):
    height, width = len(image), len(image[0])
    x, y = u*width-.5, v*height-.5
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x-ix, y-iy
    result = [0.0,0.0,0.0]
    for dx, dy in product((0,1), repeat=2):
        weight = (fx if dx else 1-fx)*(fy if dy else 1-fy)
        value = image[min(height-1,max(0,iy+dy))][min(width-1,max(0,ix+dx))]
        for c in range(3):
            result[c] += weight*value[c]
    return tuple(result)


def combine(scene, bloom, enabled=True, mode=1, debug=0, strength=.08):
    if not enabled or not mode or debug or strength <= 0:
        return scene
    return tuple(bounded_channel(bounded_channel(c)+strength*bounded_channel(b))
                 for c,b in zip(scene[:3],bloom)) + (scene[3],)


def close(a, b, tolerance=1e-10):
    return all(abs(x-y) <= tolerance for x,y in zip(a,b))


def validate_bloom(root, expand, preprocess, compact, function_body):
    shaders = root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M9_BASELINE+':shaders/'+relative]).decode().replace('\r\n','\n')
    def body(source,name):
        return compact(function_body(source,name))
    old_files = subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',
                                        M9_BASELINE,'shaders']).decode().splitlines()
    old_programs = {p[len('shaders/'):-4] for p in old_files if p.endswith('.vsh')}
    assert len(old_programs) == 20
    assert {p.stem for p in shaders.glob('*.vsh')} == old_programs | set(BLOOM_PROGRAMS)
    assert {p.stem for p in shaders.glob('*.fsh')} == old_programs | set(BLOOM_PROGRAMS)
    pinned = 0
    for path in old_files:
        relative = path[len('shaders/'):]
        if relative.endswith(('.glsl','.vsh','.fsh')):
            assert read(relative) == prior(relative), relative
            pinned += 1
    props = read('shaders.properties')
    assert restore_bloom_properties(props) == prior('shaders.properties')
    labels = read('lang/en_us.lang')
    assert labels.startswith(prior('lang/en_us.lang'))
    assert not re.search(r'^(?:flip\.|program\..*\.enabled)',props,re.M)
    for attachment in (3,4):
        assert props.count('size.buffer.colortex{} = 0.5 0.5'.format(attachment)) == 1
    common = read('lib/bloom.glsl')
    for token in ('isnan(value)?0.0:clamp(value,0.0,65504.0)',
                  'floatthreshold=max(BLOOM_THRESHOLD,0.0);',
                  'floatknee=threshold*clamp(BLOOM_SOFT_KNEE,0.0,1.0);',
                  'if(knee>0.0){floatramp=clamp(peak-threshold+knee,0.0,2.0*knee);soft=ramp*ramp/(4.0*knee);}',
                  'floatcontribution=max(max(peak-threshold,0.0),soft);',
                  'returnbloomSafe(rgb*(contribution/max(peak,0.000001)));',
                  'texelFetch(source,clamp(pixel,ivec2(0),extent-1),0).rgb',
                  'for(inttap=0;tap<9;++tap)',
                  'bloomFetch(source,pixel+(tap-4)*axis)*(weights[tap]/256.0)',
                  'uv*vec2(textureSize(source,0))-0.5', 'ivec2base=ivec2(floor(position));',
                  'vec2weight=fract(position);', 'returnbloomSafe(mix(lower,upper,weight.y));'):
        assert token in compact(common), token
    match = re.search(r'const float weights\[9\] = float\[9\]\(([^)]+)\);',common)
    assert match
    assert tuple(float(x)/256 for x in match[1].split(',')) == KERNEL
    assert sum(KERNEL) == 1 and KERNEL == KERNEL[::-1]
    assert body(common,'bloomSafe') == 'returnvec3(bloomSafeComponent(value.r),bloomSafeComponent(value.g),bloomSafeComponent(value.b));'
    combine_main = body(read('composite3.fsh'),'main')
    assert 'vec4scene=texelFetch(colortex0,pixel,0);' in combine_main
    assert 'vec3glow=upsampleBloom(colortex3,uv);' in combine_main
    assert combine_main.index('color=scene;') < combine_main.index('if(!bloomActive())return;') < combine_main.index('upsampleBloom(') < combine_main.index('bloomSafe(')
    assert 'color=vec4(bloomSafe(bloomSafe(scene.rgb)+max(BLOOM_STRENGTH,0.0)*glow),scene.a);' in combine_main
    assert 'vec2uv=(vec2(pixel)+0.5)/vec2(textureSize(colortex0,0));' in combine_main
    extraction = read('composite.fsh')
    for token in ('textureSize(colortex0,0)', 'textureSize(colortex3,0)',
                  'vec2ratio=vec2(sourceSize)/vec2(outputSize);',
                  'vec2first=floor(gl_FragCoord.xy)*ratio;',
                  'vec2last=min((floor(gl_FragCoord.xy)+1.0)*ratio,vec2(sourceSize));',
                  'for(inty=0;y<3;++y)', 'for(intx=0;x<3;++x)',
                  'if(any(greaterThanEqual(pixel,sourceSize)))continue;',
                  'max(min(last,vec2(pixel+1))-max(first,vec2(pixel)),vec2(0.0))',
                  'if(area>0.0)sum+=extractBloom(texelFetch(colortex0,pixel,0).rgb)*area;',
                  'max((last.x-first.x)*(last.y-first.y),0.000001)',
                  'color=vec4(bloomSafe(sum/totalArea),0.0);'):
        assert token in compact(extraction), token
    assert 'texelFetch(colortex3' not in extraction and 'texture(colortex3' not in extraction
    for number in (3,4):
        assert 'const int colortex{}Format = RGBA16F;'.format(number) in extraction
        assert 'constvec4colortex{}ClearColor=vec4(0.0,0.0,0.0,0.0);'.format(number) in compact(extraction)
    # Allocation and flips: each write targets the opposite side, then becomes
    # the readable side. Source scene survives untouched until composite3.
    expected_reads = ((0,),(3,),(4,),(0,3))
    versions, banks = {0:'scene',3:None,4:None}, {0:0,3:0,4:0}
    for index, program in enumerate(BLOOM_PROGRAMS):
        source = read(program+'.fsh')
        target = BLOOM_TARGETS[program]
        assert re.findall(r'/\* RENDERTARGETS: (\d+) \*/',source) == [str(target)]
        assert 'layout(location = 0) out vec4 color;' in source
        assert read(program+'.vsh') == '#version 330 compatibility\n#include "/lib/fullscreen_vertex.glsl"\n'
        assert 'EXPOSURE' not in compact(source) and 'toneMapScene' not in source and 'linearToSrgb' not in source
        assert all(versions[attachment] is not None for attachment in expected_reads[index])
        if index < 3:
            assert versions[0] == 'scene' and banks[0] == 0
            assert body(source,'main').startswith('color=vec4(0.0);if(!bloomActive())return;')
        else:
            assert versions[3] == 'composite2' and versions[0] == 'scene'
        read_banks = {(attachment,banks[attachment]) for attachment in expected_reads[index]}
        write_bank = (target,1-banks[target])
        assert write_bank not in read_banks
        banks[target] = write_bank[1]
        versions[target] = program
    assert versions[0] == 'composite3' and banks == {0:1,3:0,4:1}
    for name, attachment, axis in (('composite1',3,'ivec2(1,0)'),('composite2',4,'ivec2(0,1)')):
        assert body(read(name+'.fsh'),'main') == ('color=vec4(0.0);if(!bloomActive())return;'
            'color=vec4(blurBloom(colortex'+str(attachment)+',ivec2(gl_FragCoord.xy),'+axis+'),0.0);')
    for mode, enabled, debug in product((0,1),(0,1),range(7)):
        for program in BLOOM_PROGRAMS:
            source = preprocess(expand(shaders/(program+'.fsh')),debug,False,
                                overrides={'SCENE_COLOR_MODE':mode,'BLOOM_ENABLED':enabled})
            expected = 'returnBLOOM_STRENGTH>0.0;' if mode and enabled and not debug else 'returnfalse;'
            assert body(source,'bloomActive') == expected
            clean = re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
            assert not re.search(r'const int colortex\d+Format\s*=\s*[A-Z]',clean)
            assert source.count('bool bloomActive()') == source.count('void main()') == 1
    for name, default in (('BLOOM_ENABLED','1'),('BLOOM_STRENGTH','0.08'),
                          ('BLOOM_THRESHOLD','1.0'),('BLOOM_SOFT_KNEE','0.5')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',read('lib/bloom_settings.glsl'),re.M)
        assert name in props.split('screen.BLOOM =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    # Positive RGB ratios survive a conservative soft-knee extraction.
    extraction_cases = 0
    for threshold,knee,peak,ratios in product((.5,1,1.5,2),(0,.25,.5,1),
            (0,.000001,.1,.25,.5,.75,1,1.5,2,4,64,HALF_MAX),((1,1,1),(1,.2,.05),(.05,1,.4))):
        rgb = tuple(peak*r for r in ratios)
        out = extract_bright(rgb,threshold,knee)
        assert all(math.isfinite(c) and 0 <= c <= before+1e-10 for c,before in zip(out,rgb))
        if peak <= threshold*(1-knee):
            assert out == (0,0,0)
        if out[0] > 0:
            assert abs(out[0]/out[1]-rgb[0]/rgb[1]) < 1e-12
        if knee == 0:
            assert abs(max(out)-max(peak-threshold,0)) < 1e-10
        extraction_cases += 1
    for threshold,knee in product((.5,1,1.5,2),(0,.25,.5,1)):
        values = [extract_bright((p/100,0,0),threshold,knee)[0] for p in range(401)]
        assert all(b >= a-1e-12 for a,b in zip(values,values[1:]))
        for boundary in (threshold*(1-knee),threshold,threshold*(1+knee)):
            lo = extract_bright((max(boundary-1e-7,0),0,0),threshold,knee)[0]
            hi = extract_bright((boundary+1e-7,0,0),threshold,knee)[0]
            assert 0 <= hi-lo < 3e-7
    # Pixel overlap oracle covers every input pixel, including odd trailing edges.
    # Iris truncates the half-size extent: supported source dimensions are >=2.
    area_cases = 0
    for width,height in product((2,3,4,5,7,8,16,17),repeat=2):
        ow,oh = width//2,height//2
        image = [[(float((x+2*y)%7),.25,2.0) for x in range(width)] for y in range(height)]
        down = area_downsample(image,ow,oh)
        for c in range(3):
            input_mean = sum(pixel[c] for row in image for pixel in row)/(width*height)
            output_mean = sum(pixel[c] for row in down for pixel in row)/(ow*oh)
            assert abs(input_mean-output_mean) < 1e-12
        for extent,target in ((width,ow),(height,oh)):
            for pixel in range(extent):
                assert abs(sum(overlap(i*extent/target,(i+1)*extent/target,pixel) for i in range(target))-1) < 1e-12
            for i in range(target):
                lo,hi = i*extent/target,(i+1)*extent/target
                assert sum(overlap(lo,hi,p)>1e-12 for p in range(extent)) <= 3
        assert all(abs(pixel[1]-.25) < 1e-12 and abs(pixel[2]-2) < 1e-12 for row in down for pixel in row)
        area_cases += 1
    isolated = [[(4.,4.,4.),(0.,0.,0.)],[(0.,0.,0.),(0.,0.,0.)]]
    pre = area_downsample(isolated,1,1,lambda c:extract_bright(c,knee=0))[0][0]
    post = extract_bright(area_downsample(isolated,1,1)[0][0],knee=0)
    assert pre == (.75,.75,.75) and post == (0,0,0)
    # Binomial convolution preserves constants and interior impulse energy;
    # clamp-to-edge boundaries intentionally need not conserve total image energy.
    for width,height in ((1,1),(2,3),(7,5),(17,17)):
        constant = [[(.25,1.,HALF_MAX) for _ in range(width)] for _ in range(height)]
        blurred = blur_axis(blur_axis(constant,True),False)
        assert all(close(c,(.25,1.,HALF_MAX)) for row in blurred for c in row)
    impulse = [[(1.,1.,1.) if x == y == 10 else (0.,0.,0.) for x in range(21)] for y in range(21)]
    blurred = blur_axis(blur_axis(impulse,True),False)
    assert abs(sum(c[0] for row in blurred for c in row)-1) < 1e-12
    assert blurred[10][10][0] == (70/256)**2
    for y,x in product(range(21),repeat=2):
        assert blurred[y][x] == blurred[20-y][x] == blurred[y][20-x] == blurred[x][y]
    # Bilinear reconstruction is convex, hits texel centers, and clamps borders.
    grid = [[(0.,1.,2.),(2.,3.,4.)],[(4.,5.,6.),(6.,7.,8.)]]
    assert bilinear(grid,.5,.5) == (3.,4.,5.)
    assert bilinear(grid,.25,.25) == grid[0][0]
    assert bilinear(grid,0,0) == grid[0][0] and bilinear(grid,1,1) == grid[1][1]
    for u,v in product((0,.1,.25,.5,.75,.9,1),repeat=2):
        assert close(bilinear([[(2.,3.,4.)]],u,v),(2.,3.,4.))
        assert all(0 <= c <= 8 for c in bilinear(grid,u,v))
    # Every new attachment/output value must fit a finite half float. Exact
    # disabled copies retain even unusual inputs rather than sanitize them.
    for value in (-math.inf,-1e30,-1,0,.18,1,HALF_MAX,1e30,math.inf,math.nan):
        safe = bounded_channel(value)
        assert 0 <= safe <= HALF_MAX and math.isfinite(struct.unpack('e',struct.pack('e',safe))[0])
        bright = extract_bright((value,value,value))
        assert all(math.isfinite(struct.unpack('e',struct.pack('e',x))[0]) for x in bright)
        result = combine((value,value,value,.35),bright,strength=.2)
        assert result[3] == .35 and all(math.isfinite(struct.unpack('e',struct.pack('e',x))[0]) for x in result[:3])
    original = (math.inf,-.5,1e8,math.nan)
    for enabled,mode,debug,strength in product((False,True),(0,1),range(7),(0,.04,.08,.12,.2)):
        out = combine(original,(1,2,3),enabled,mode,debug,strength)
        if not enabled or not mode or debug or strength == 0:
            assert out is original
        else:
            assert out[3] is original[3]
    print('PASS: M10 {} M9 shader files unchanged; 20 original + 4 bloom program pairs and 3->4->3->0 flip graph'.format(pinned))
    print('PASS: M10 {} extraction cases, soft-knee continuity/ratios, {} odd/even area-weighted sizes'.format(extraction_cases,area_cases))
    print('PASS: M10 binomial constant/impulse invariants, bilinear reconstruction and finite FP16 storage')
    print('PASS: M10 off/zero/debug/legacy exact copies, alpha preservation and exposure remaining in final')
    print('LIMIT: half-size buffers require source dimensions >=2; no Iris/GPU runtime or performance validation')
