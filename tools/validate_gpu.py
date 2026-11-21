"""Optional Windows native OpenGL driver checks; NOT Iris or Minecraft testing.

python -B tools/validate_gpu.py --cxx C:/msys64/ucrt64/bin/g++.exe
Uses an installed compiler, never downloads dependencies or launches Minecraft.
All generated source, binaries and pixels live in a fresh directory beside the
project on the same drive and are removed after the run. A report is opt-in.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from compile_glsl import ROOT, SHADERS, configure, configurations, expand
from validate_bloom import area_downsample, bilinear, blur_axis, combine, extract_bright
from validate_color_pipeline import shoulder
from validate_atmosphere import encode
from validate_water_waves import anchored_tile, f32, matrix_vector, unit, wave_gradient, wave_normal_from_gradient

LIMIT = ('Native OpenGL synthetic inputs only: no Iris patcher, Minecraft world, '
         'render-order/texture-binding integration, screenshots or performance measurement.')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def quote(value):
    # std::quoted uses C++ escaping, not JSON \uXXXX escapes. Keep UTF-8 literal.
    value = str(value).replace('\\', '/') if isinstance(value, Path) else str(value)
    require(not any(ord(c) < 32 for c in value), 'Control character in manifest field')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def write_text(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def half(value):
    return struct.unpack('<e', struct.pack('<e', value))[0]


def image_map(image, operation):
    return [[operation(pixel) for pixel in row] for row in image]


def quantize(image):
    return image_map(image, lambda pixel: tuple(half(x) for x in pixel))


def rgba(image, alpha=0.0):
    return image_map(image, lambda pixel: tuple(pixel[:3]) + (alpha,))


def half_ulp(value):
    return 2.0 ** max(-24, math.frexp(abs(value))[1] - 11) if value else 2.0 ** -24


def compare(actual, expected, label, half_units=0, absolute=0.0, relative=0.0):
    require(len(actual) == len(expected) and all(len(a) == len(e) for a, e in zip(actual, expected)),
            label + ': image dimensions differ')
    largest = 0.0
    worst_fraction = 0.0
    channels = 0
    for y, (a_row, e_row) in enumerate(zip(actual, expected)):
        for x, (a_pixel, e_pixel) in enumerate(zip(a_row, e_row)):
            require(len(a_pixel) == len(e_pixel) == 4, label + ': requires RGBA')
            for channel, (a, e) in enumerate(zip(a_pixel, e_pixel)):
                require(math.isfinite(a) and math.isfinite(e), '{}: nonfinite at {},{},{}'.format(label,x,y,channel))
                error = abs(a - e)
                tolerance = absolute + relative * abs(e) + half_units * half_ulp(e)
                require(error <= tolerance, '{}: pixel {},{} channel {}: GPU {} expected {} tolerance {}'.format(
                    label, x, y, channel, a, e, tolerance))
                largest = max(largest, error)
                worst_fraction = max(worst_fraction, error / tolerance if tolerance else 0.0)
                channels += 1
    return dict(label=label, channels=channels, max_absolute_error=largest,
                max_tolerance_fraction=worst_fraction, tolerance=dict(half_ulps=half_units, absolute=absolute, relative=relative))


class Runner:
    def __init__(self, scratch, cxx):
        self.scratch = scratch
        self.executable = scratch / 'aurora-gpu.exe'
        self.sequence = 0
        self.gl = None
        self.last_manifest = None
        self.last_output = None
        self.environment = dict(os.environ, TMP=str(scratch), TEMP=str(scratch), TMPDIR=str(scratch))
        command = [cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-static',
                   str(ROOT/'tools/gpu_harness.cpp'), '-lopengl32', '-lgdi32', '-luser32',
                   '-o', str(self.executable)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding='utf-8', errors='replace', timeout=120, env=self.environment)
        require(result.returncode == 0, 'Harness build failed:\n' + result.stdout)
        require(not result.stdout.strip(), 'Harness build produced diagnostics:\n' + result.stdout)
        self.build = dict(compiler=Path(cxx).name, flags=command[1:7], diagnostics=result.stdout)

    def call(self, *arguments, expected_failure=None):
        result = subprocess.run([str(self.executable)] + [str(x) for x in arguments],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding='utf-8', errors='replace', timeout=600, env=self.environment)
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError('Harness returned invalid JSON:\n' + result.stdout + result.stderr)
        require(isinstance(payload, dict), 'Harness JSON must be an object')
        require(not result.stderr.strip(), 'Harness stderr: ' + result.stderr)
        if expected_failure is not None:
            require(result.returncode != 0 and payload.get('ok') is False, 'Expected harness rejection: ' + expected_failure)
            require(payload.get('stage') == expected_failure, 'Wrong failure stage: ' + json.dumps(payload))
        else:
            require(result.returncode == 0 and payload.get('ok') is True, json.dumps(payload, ensure_ascii=False))
            require(isinstance(payload.get('gl'), dict), 'No driver identity in successful result')
        if payload.get('gl') is not None:
            if self.gl is None:
                self.gl = payload['gl']
            require(payload['gl'] == self.gl, 'Driver identity changed between tests')
        return payload

    def pair(self, program, options=None, wrapper=None):
        self.sequence += 1
        stem = 'source-{:05d}'.format(self.sequence)
        vertex, fragment = self.scratch/(stem+'.vert'), self.scratch/(stem+'.frag')
        write_text(vertex, configure(expand(SHADERS/(program+'.vsh')), options or {}))
        source = expand(SHADERS/(program+'.fsh')) if wrapper is None else wrapper
        write_text(fragment, configure(source, options or {}))
        return vertex, fragment

    def render(self, label, pair, width, height, textures=(), uniforms=(), storage='RGBA32F', optional=(),
               extra_targets=(), read_target=0):
        self.sequence += 1
        stem = 'render-{:05d}'.format(self.sequence)
        output = self.scratch/(stem+'.raw')
        manifest = self.scratch/(stem+'.txt')
        lines = ['shaders {} {}'.format(*map(quote, pair)),
                 'target {} {} {} {}'.format(width, height, storage, quote(output))]
        lines += ['color_target {} {} {}'.format(slot, attachment, fmt) for slot,attachment,fmt in extra_targets]
        lines.append('read_target {}'.format(read_target))
        for index, (name, image, texture_storage) in enumerate(textures):
            tex_height, tex_width = len(image), len(image[0])
            require(all(len(row) == tex_width for row in image), 'Ragged input image')
            flat = [value for row in image for pixel in row for value in pixel]
            require(len(flat) == tex_width*tex_height*4, 'Input must be RGBA')
            path = self.scratch/(stem+'-input-{}.raw'.format(index))
            with path.open('xb') as stream:
                stream.write(struct.pack('<{}f'.format(len(flat)), *flat))
            lines.append('texture {} {} {} {} {}'.format(quote(name), tex_width, tex_height, texture_storage, quote(path)))
        for name, kind, values in uniforms:
            lines.append('uniform {} {} {}'.format(quote(name),kind,' '.join(str(x) for x in values)))
        write_text(manifest, '\n'.join(lines)+'\n')
        payload = self.call('--render', manifest)
        require(isinstance(payload.get('inactive_bindings'),list),label+': missing binding report')
        require(set(payload['inactive_bindings']).issubset(set(optional)),
                label+': unexpected inactive bindings: '+str(payload['inactive_bindings']))
        require((payload.get('width'), payload.get('height'), payload.get('format')) == (width,height,storage), label+': result metadata differs')
        require(payload.get('row_order') == 'bottom_to_top' and payload.get('pixel_type') == 'RGBA_float32_little_endian', label+': unexpected pixel protocol')
        targets=[dict(slot=0,attachment=0,format=storage)] + [
            dict(slot=slot,attachment=attachment,format=fmt) for slot,attachment,fmt in sorted(extra_targets)]
        require(payload.get('color_targets')==targets,label+': framebuffer routing differs')
        selected=next(target for target in targets if target['slot']==read_target)
        require(payload.get('read_target')==read_target and payload.get('read_format')==selected['format'],
                label+': selected read attachment differs')
        data = output.read_bytes()
        require(len(data) == width*height*16, label+': output byte count differs')
        flat = struct.unpack('<{}f'.format(width*height*4), data)
        image = [[tuple(flat[(y*width+x)*4:(y*width+x+1)*4]) for x in range(width)] for y in range(height)]
        self.last_manifest, self.last_output = manifest, output
        return image


def driver_compile(runner, selected=None):
    entries = []
    configs = list(configurations() if selected is None else selected)
    for index, (program, options) in enumerate(configs):
        pair = runner.pair(program, options)
        entries.append('{} {} {}'.format(quote('{}-{}'.format(index, program)), *map(quote, pair)))
    manifest = runner.scratch/'compile-matrix.txt'
    write_text(manifest, '\n'.join(entries)+'\n')
    print('Running {} program pairs through the native driver...'.format(len(configs)), flush=True)
    result = runner.call('--compile-batch', manifest)
    require(result.get('compiled') == result.get('case_count') == len(configs), 'Driver compile count differs')
    return dict(configurations=len(configs), program_pairs=len(list(SHADERS.glob('*.vsh'))),
                input=('Actual expanded pack pairs with the existing offline option matrix; Iris transforms absent' if selected is None
                       else 'Actual expanded pack pairs with parsed quality profiles; Iris transforms absent'))


def harness_controls(runner):
    # Positive controls prove coverage, row orientation, UVs and RGBA channels.
    copy = '#version 330 compatibility\nuniform sampler2D sampleImage;\nin vec2 texcoord;\nlayout(location=0) out vec4 color;\nvoid main(){ color=texture(sampleImage,texcoord); }\n'
    pair = runner.pair('composite', wrapper=copy)
    source = [[(x/4.0,y/4.0,(x+3*y)/16.0,(1+x+y)/8.0) for x in range(3)] for y in range(2)]
    results = []
    for storage in ('RGBA32F','RGBA16F'):
        image = runner.render('copy-'+storage,pair,3,2,[('sampleImage',source,storage)],storage=storage)
        results.append(compare(image,source,'copy-'+storage))
    saved = runner.last_output.read_bytes()
    runner.call('--render',runner.last_manifest,expected_failure='output')
    require(runner.last_output.read_bytes() == saved, 'Overwrite rejection altered output')
    # Invalid shaders and raw-image lengths must fail, rather than count as passes.
    bad_pair = runner.pair('composite', wrapper='#version 330 compatibility\nvoid main(){ this_is_not_GLSL; }\n')
    runner.call('--compile',*bad_pair,expected_failure='shader compilation')
    bad_raw = runner.scratch/'short-input.raw'
    bad_raw.write_bytes(b'\0'*4)
    manifest = runner.scratch/'short-input.txt'
    write_text(manifest,'shaders {} {}\ntarget 1 1 RGBA32F {}\ntexture "sampleImage" 1 1 RGBA32F {}\n'.format(
        *map(quote,pair),quote(runner.scratch/'short-output.raw'),quote(bad_raw)))
    runner.call('--render',manifest,expected_failure='texture input')
    require(not (runner.scratch/'short-output.raw').exists(), 'Bad input unexpectedly produced output')
    # Unequal sampler weights expose missing/wrong texture-unit assignments.
    dual = copy.replace('uniform sampler2D sampleImage;','uniform sampler2D sampleImage;\nuniform sampler2D secondImage;').replace(
        'color=texture(sampleImage,texcoord);','color=texture(sampleImage,texcoord)*0.25+texture(secondImage,texcoord)*0.75;')
    second=image_map(source,lambda p:(2-p[1],4-p[0],1+p[2],.5))
    image=runner.render('two-samplers',runner.pair('composite',wrapper=dual),3,2,
                        [('sampleImage',source,'RGBA32F'),('secondImage',second,'RGBA32F')])
    expected=[[tuple(a*.25+b*.75 for a,b in zip(p,q)) for p,q in zip(r,s)] for r,s in zip(source,second)]
    results.append(compare(image,expected,'two-samplers'))
    # Distinct rows/columns test matrix upload convention independently of water math.
    matrix_source='#version 330 compatibility\nuniform mat4 testMatrix;\nlayout(location=0) out vec4 color;\nvoid main(){color=testMatrix*vec4(gl_FragCoord.xy,2.0,1.0);}\n'
    matrix_pair=runner.pair('composite',wrapper=matrix_source)
    matrix=((1,.5,0,2),(0,2,.25,-1),(.125,0,3,.5),(0,0,0,.375))
    column_major=[matrix[r][c] for c in range(4) for r in range(4)]
    image=runner.render('matrix-and-coverage',matrix_pair,5,3,uniforms=[('testMatrix','m4',column_major)])
    expected=[[matrix_vector(matrix,(x+.5,y+.5,2,1)) for x in range(5)] for y in range(3)]
    results.append(compare(image,expected,'matrix-and-coverage'))
    # A deliberate type mismatch must produce a GL error; a link mismatch must fail.
    bad_uniform=runner.scratch/'bad-uniform.txt'
    write_text(bad_uniform,'shaders {} {}\ntarget 1 1 RGBA32F {}\nuniform "testMatrix" f1 1\n'.format(
        *map(quote,matrix_pair),quote(runner.scratch/'bad-uniform.raw')))
    runner.call('--render',bad_uniform,expected_failure='uniform type')
    mismatch='#version 330 compatibility\nin vec3 texcoord;\nlayout(location=0) out vec4 color;\nvoid main(){color=vec4(texcoord,1.0);}\n'
    link_pair=runner.pair('composite',wrapper=mismatch)
    runner.call('--compile',*link_pair,expected_failure='program link')
    # A typo could still sample unit zero correctly. Binding audit must catch it.
    try:
        runner.render('misspelled-binding',pair,3,2,[('sampleImag',source,'RGBA32F')])
    except RuntimeError as error:
        require('unexpected inactive bindings' in str(error),'Wrong inactive-binding rejection: '+str(error))
    else:
        raise RuntimeError('Runner accepted misspelled sampler binding')
    # Discard every fragment: the sentinel must survive and zero-output checks fail.
    discard='#version 330 compatibility\nlayout(location=0) out vec4 color;\nvoid main(){discard;}\n'
    image=runner.render('discard-control',runner.pair('composite',wrapper=discard),3,2)
    sentinel=[[(-11931.25,-719.5,-37.25,-13.0)]*3 for _ in range(2)]
    results.append(compare(image,sentinel,'discard-preserves-clear'))
    try:
        compare(image,[[(0,0,0,0)]*3 for _ in range(2)],'missing-draw')
    except RuntimeError as error:
        require('missing-draw: pixel' in str(error),'Wrong missing-draw rejection: '+str(error))
    else:
        raise RuntimeError('Runner accepted an unwritten target as zero shader output')
    return dict(comparisons=results, rejected=['existing output without modification','invalid GLSL','truncated raw texture',
                                              'uniform type mismatch','varying link mismatch','misspelled inactive sampler','unwritten zero target'])


def bloom_tests(runner):
    comparisons = []
    # Odd sizes force fractional area footprints and include the final row/column.
    # Binary-exact half inputs isolate arithmetic/storage error from upload rounding.
    for width,height in ((7,5),(3,3),(8,6)):
        source = [[((x+2*y)%7*.5,(3*x+y)%5*.25,(x+y)%3*.125,(1+(x+2*y)%7)/8.0)
                   for x in range(width)] for y in range(height)]
        source[-1][-1] = (8.0,4.0,2.0,.375)
        sw,sh = width//2,height//2
        dummy = [[(0,0,0,0)]*sw for _ in range(sh)]
        for threshold,knee,strength in ((1.0,.5,.08),(.5,0.0,.2),(2.0,1.0,.08)):
            label = 'bloom-{}x{}-t{}-k{}-s{}'.format(width,height,threshold,knee,strength)
            options = dict(BLOOM_THRESHOLD=threshold,BLOOM_SOFT_KNEE=knee,BLOOM_STRENGTH=strength)
            extract = runner.render(label+'-extract',runner.pair('composite1',options),sw,sh,
                                    [('colortex0',source,'RGBA16F'),('colortex3',dummy,'RGBA16F')],storage='RGBA16F')
            expected_extract = quantize(rgba(area_downsample(source,sw,sh,lambda p: extract_bright(p[:3],threshold,knee))))
            comparisons.append(compare(extract,expected_extract,label+'-extract',half_units=2,absolute=2e-6))
            horizontal = runner.render(label+'-horizontal',runner.pair('composite2',options),sw,sh,
                                       [('colortex3',extract,'RGBA16F')],storage='RGBA16F')
            comparisons.append(compare(horizontal,quantize(rgba(blur_axis(extract,True))),label+'-horizontal',half_units=2,absolute=2e-6))
            vertical = runner.render(label+'-vertical',runner.pair('composite3',options),sw,sh,
                                     [('colortex4',horizontal,'RGBA16F')],storage='RGBA16F')
            comparisons.append(compare(vertical,quantize(rgba(blur_axis(horizontal,False))),label+'-vertical',half_units=2,absolute=2e-6))
            combined = runner.render(label+'-combine',runner.pair('composite4',options),width,height,
                                     [('colortex0',source,'RGBA16F'),('colortex3',vertical,'RGBA16F')],storage='RGBA16F')
            expected = quantize([[combine(source[y][x],bilinear(vertical,(x+.5)/width,(y+.5)/height),strength=strength)
                                  for x in range(width)] for y in range(height)])
            comparisons.append(compare(combined,expected,label+'-combine',half_units=2,absolute=2e-6))
            # Independent end-to-end oracle also catches errors accumulating across passes.
            cpu_blur = quantize(rgba(blur_axis(quantize(rgba(blur_axis(expected_extract,True))),False)))
            end_to_end = quantize([[combine(source[y][x],bilinear(cpu_blur,(x+.5)/width,(y+.5)/height),strength=strength)
                                    for x in range(width)] for y in range(height)])
            comparisons.append(compare(combined,end_to_end,label+'-chain',half_units=4,absolute=4e-6))
            require(all(combined[y][x][3] == source[y][x][3] for y in range(height) for x in range(width)),label+': alpha changed')
    source = [[(.25,.5,2.0,.375),(1.0,0.0,.5,.875)]]
    bloom = [[(4.0,2.0,1.0,0.0)]]
    for option in (dict(BLOOM_ENABLED=0),dict(BLOOM_STRENGTH=0.0),dict(SCENE_COLOR_MODE=0),dict(DEBUG_VIEW=5)):
        label = 'bloom-bypass-'+next(iter(option))
        image = runner.render(label,runner.pair('composite4',option),2,1,
                              [('colortex0',source,'RGBA16F'),('colortex3',bloom,'RGBA16F')],storage='RGBA16F',optional=('colortex3',))
        comparisons.append(compare(image,source,label))
    return dict(graphs=9, passes_per_graph=4, comparisons=comparisons,
                storage='RGBA16F inputs and every intermediate; float32 readback; bottom row first')


def water_tests(runner):
    wrapper = '#version 330 compatibility\n'+expand(SHADERS/'lib/water_waves.glsl')+'''
uniform sampler2D testPositions;
uniform vec3 testNormal;
uniform float testEligibility;
layout(location=0) out vec4 color;
void main() {
    vec3 viewPosition=texelFetch(testPositions,ivec2(gl_FragCoord.xy),0).xyz;
    color=vec4(waterWaveNormal(testNormal,viewPosition,testEligibility),1.0);
}
'''
    identity = ((1,0,0),(0,1,0),(0,0,1))
    positions = [[(x*7.25-20.125,1.625,z*13.5-17.75,1.0) for x in range(7)] for z in range(3)]
    cases = []
    for anchor in ((0,64,0),(-1,64,-129),(128,64,127),(30000000,100,-30000000),
                   (-2147483648,0,2147483647)):
        for seconds in (0.0,17.0,3599.999):
            cases.append(dict(anchor=anchor,seconds=seconds))
    cases += [dict(seconds=t,speed=s) for t in (199.999,200.001,3600.001) for s in (0,1,2)]
    cases += [dict(strength=0.0),dict(enabled=0),dict(eligibility=0.0),dict(eligibility=.25),dict(strength=1.0),
              dict(seconds=math.nan),dict(seconds=math.inf),dict(seconds=-1.0)]
    # Inverse model-view rotation, scale and translation; normal matrix is its transpose.
    c,s = math.cos(.7),math.sin(.7)
    cases += [dict(inverse=((c,0,s),(0,1,0),(-s,0,c)),translation=(.25,1.625,-.125)),
              dict(inverse=((.5,0,0),(0,2,0),(0,0,3)),translation=(.25,1.625,-.125)),
              dict(inverse=((0,0,0),(0,0,0),(0,0,0)))]
    comparisons = []
    samples = 0
    for index,case in enumerate(cases):
        anchor=case.get('anchor',(-129,64,128)); fraction=(.25,.625,.75)
        seconds=f32(case.get('seconds',17.0)); speed=case.get('speed',1)
        strength=case.get('strength',.6); enabled=case.get('enabled',1); eligibility=case.get('eligibility',1.0)
        inverse=tuple(tuple(f32(x) for x in row) for row in case.get('inverse',identity))
        translation=case.get('translation',(0,0,0))
        normal_matrix=tuple(tuple(inverse[j][i] for j in range(3)) for i in range(3))
        normal=unit(matrix_vector(normal_matrix,(0,1,0))) or (0,1,0)
        normal=tuple(f32(x) for x in normal)
        matrix=[inverse[row][col] if row<3 and col<3 else translation[row] if col==3 and row<3
                else 1 if row==col==3 else 0 for col in range(4) for row in range(4)]
        options=dict(WATER_WAVES=enabled,WATER_WAVE_STRENGTH=strength,WATER_WAVE_SPEED=speed)
        uniforms=[('cameraPositionInt','i3',anchor),('cameraPositionFract','f3',fraction),
                  ('frameTimeCounter','f1',(seconds,)),('gbufferModelViewInverse','m4',matrix),
                  ('testNormal','f3',normal),('testEligibility','f1',(eligibility,))]
        label='water-{}'.format(index)
        optional=[]
        if not enabled or strength==0:
            optional=['testPositions','testEligibility','gbufferModelViewInverse','cameraPositionInt','cameraPositionFract','frameTimeCounter']
        elif speed==0:
            optional=['frameTimeCounter']
        actual=runner.render(label,runner.pair('composite',options,wrapper),7,3,
                             [('testPositions',positions,'RGBA32F')],uniforms,optional=optional)
        expected=[]
        for row in positions:
            result=[]
            for position in row:
                player=tuple(x+t for x,t in zip(matrix_vector(inverse,position[:3]),translation))
                gradient=wave_gradient(anchored_tile(anchor,fraction,player),seconds,speed,fp32=True)
                n=wave_normal_from_gradient(normal,gradient,normal_matrix,strength=strength,
                                            eligibility=eligibility,enabled=bool(enabled))
                result.append(n+(1.0,))
            expected.append(result)
        bypass=not enabled or strength==0 or eligibility==0 or not any(x for row in inverse for x in row)
        comparisons.append(compare(actual,expected,label,absolute=0 if bypass else 6e-5))
        require(all(pixel[3]==1.0 for row in actual for pixel in row),label+': draw coverage/alpha')
        samples+=21
    return dict(cases=len(cases),normal_samples=samples,comparisons=comparisons,
                input='Actual shared helper called by synthetic fragment wrapper; real water geometry/rasterization absent')


def final_tests(runner):
    source=[[(0,0,0,.125),(.0031308,.002,.001,.25),(.25,.125,.5,.375),(.6,.3,.15,.5),
             (1,.5,.25,.625),(4,2,1,.75),(16,.125,.0625,.875)]]
    source=image_map(source,lambda p:tuple(f32(x) for x in p))
    comparisons=[]
    for mapping,knee,exposure,gray in ((1,.6,0.0,False),(1,.4,-2.0,False),(1,.8,2.0,False),
                                     (0,.6,0.0,False),(1,.6,0.0,True)):
        options=dict(TONE_MAPPING=mapping,TONEMAP_KNEE=knee,EXPOSURE=exposure,GRAYSCALE=gray)
        actual=runner.render('final',runner.pair('final',options),7,1,[('colortex0',source,'RGBA32F')])
        expected=[]
        for pixel in source[0]:
            rgb=tuple(encode(x) for x in shoulder(tuple(max(x,0)*2**exposure for x in pixel[:3]),knee,mapping))
            if gray:
                luminance=sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))
                rgb=(luminance,)*3
            expected.append(tuple(min(1,max(0,c)) for c in rgb)+(pixel[3],))
        comparisons.append(compare(actual,[expected],'final-'+str(options),absolute=3e-6,relative=2e-5))
        require(all(a[3]==e[3] for a,e in zip(actual[0],source[0])),'Final changed alpha')
    return dict(cases=len(comparisons),comparisons=comparisons,
                input='Actual final program with synthetic linear scene, neutral grading except requested grayscale')


def shader_digest():
    digest=hashlib.sha256()
    for path in sorted(p for p in SHADERS.rglob('*') if p.is_file()):
        digest.update(path.relative_to(SHADERS).as_posix().encode('utf-8')+b'\0')
        digest.update(path.read_bytes().replace(b'\r\n',b'\n')+b'\0')
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',help='Installed MinGW g++ compiler; no download')
    parser.add_argument('--suite',choices=('all','probe','compile','render','depth','profiles','foliage','celestial','snapshot','filtered-waves','screen-reflections','water-debug','water-transport','water-stability'),default='all')
    parser.add_argument('--report',help='New JSON report path under the project; existing files are never overwritten')
    parser.add_argument('--debug-plate',help='Save the selected water suite comparison to a new project PNG')
    args=parser.parse_args()
    plate_path=None
    if args.debug_plate:
        plate_path=(ROOT/args.debug_plate).resolve()
        require(args.suite in ('water-debug','water-transport','water-stability') and ROOT.resolve() in plate_path.parents
                and plate_path.suffix.lower()=='.png' and plate_path.parent.is_dir()
                and not plate_path.exists(),'Water debug plate requires a new project PNG path')

    require(os.name=='nt','This optional WGL runner requires Windows; no GPU checks performed')
    cxx=args.cxx or shutil.which('g++')
    require(cxx is not None and Path(cxx).is_file(),'Installed g++ unavailable; pass --cxx. No GPU checks performed.')
    report_path=None
    if args.report:
        report_path=(ROOT/args.report).resolve()
        require(ROOT.resolve() in report_path.parents,'Report must remain inside this project')
        require(not report_path.exists(),'Refusing to overwrite report: '+str(report_path))
    parent=ROOT.parent.resolve()
    scratch=Path(tempfile.mkdtemp(prefix='aurora-gpu-',dir=str(parent))).resolve()
    def safe_scratch():
        require(scratch.parent==parent and scratch.name.startswith('aurora-gpu-') and scratch.resolve()==scratch,
                'Unexpected temporary path; refusing cleanup')
    safe_scratch()
    report=dict(schema=1,started_utc=datetime.now(timezone.utc).isoformat(),suite=args.suite,
                shader_sha256=shader_digest(),scope=LIMIT,ok=False)
    try:
        runner=Runner(scratch,str(Path(cxx).resolve()))
        probe=runner.call('--probe')
        report['gl']=probe['gl']; report['build']=runner.build
        require(not any(name in runner.gl['renderer'].lower() for name in
                        ('gdi generic','llvmpipe','softpipe','swrast','software rasterizer')),
                'Software renderer detected; not recording hardware GPU success')
        print('Driver: {} / {} / {}'.format(runner.gl['vendor'],runner.gl['renderer'],runner.gl['version']),flush=True)
        if args.suite in ('all','compile','profiles'):
            selected=None
            if args.suite=='profiles':
                from validate_settings_profiles import load_profiles, profile_configurations
                report['quality_profiles']=load_profiles(ROOT)
                selected=profile_configurations(ROOT)
            report['driver_compile']=driver_compile(runner,selected)
            print('PASS: native driver program matrix',flush=True)
        if args.suite in ('all','render','depth'):
            from validate_gpu_depth import depth_tests
            cases=[] if args.suite=='depth' else [('controls',harness_controls),('bloom',bloom_tests),('water',water_tests),('final',final_tests)]
            cases.append(('water_depth',lambda driver: depth_tests(driver,compare)))
            for name,function in cases:
                report[name]=function(runner)
                print('PASS: '+name+' synthetic driver checks',flush=True)
        if args.suite in ('all','render','foliage'):
            from validate_gpu_foliage import foliage_tests
            report['foliage']=foliage_tests(runner,compare)
            print('PASS: foliage synthetic driver checks',flush=True)
        if args.suite in ('all','render','celestial'):
            from validate_gpu_celestial_glow import celestial_glow_tests
            report['celestial_glow']=celestial_glow_tests(runner,compare)
            print('PASS: celestial glow synthetic driver checks',flush=True)
        if args.suite in ('all','render','snapshot'):
            from validate_gpu_water_snapshot import snapshot_tests
            if args.suite=='snapshot':
                report['controls']=harness_controls(runner)
            report['water_snapshot']=snapshot_tests(runner,compare)
            print('PASS: matched water-scene snapshot and MRT checks',flush=True)
        if args.suite in ('all','render','filtered-waves'):
            from validate_gpu_water_filtered import filtered_wave_tests
            if args.suite=='filtered-waves':
                report['controls']=harness_controls(runner)
            report['water_filtered_waves']=filtered_wave_tests(runner,compare)
            print('PASS: filtered water waves and actual derivative checks',flush=True)
        if args.suite in ('all','render','screen-reflections'):
            from validate_gpu_water_screen_reflection import screen_reflection_tests
            if args.suite=='screen-reflections':
                report['controls']=harness_controls(runner)
            report['water_screen_reflection']=screen_reflection_tests(runner,compare)
            print('PASS: screen-space water reflection checks',flush=True)
        if args.suite in ('all','render','water-debug'):
            from validate_gpu_water_debug import debug_tests
            report['water_debug']=debug_tests(runner,plate_path)
            print('PASS: actual water capture and final debug displays',flush=True)
        if args.suite in ('all','render','water-transport'):
            from validate_gpu_water_transport import transport_tests
            from validate_gpu_water_capture import capture_tests
            if args.suite=='water-transport':
                report['controls']=harness_controls(runner)
            report['water_optics_capture']=capture_tests(runner)
            report['water_transport']=transport_tests(runner,plate_path)
            print('PASS: water optical transport on the native driver',flush=True)
        if args.suite in ('all','render','water-stability'):
            from validate_gpu_water_reflection_stability import stability_tests
            report['water_reflection_stability']=stability_tests(runner,plate_path)
            print('PASS: reflection footprint and known roof occlusion',flush=True)
        require(shader_digest()==report['shader_sha256'],'Shader source changed during validation; report invalid')
        report['ok']=True
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
    finally:
        safe_scratch()
        shutil.rmtree(str(scratch))
    if report_path:
        report_path.parent.mkdir(parents=True,exist_ok=True)
        write_text(report_path,json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print('Report: '+str(report_path),flush=True)
    print('PASS: requested native OpenGL suite completed; generated files removed.',flush=True)
    print('LIMIT: '+LIMIT,flush=True)


if __name__=='__main__':
    main()
