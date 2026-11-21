"""Measure an isolated water composite draw on Windows using actual GPU timer queries.

The deterministic inputs fill a 1280x720 frame with water above a horizontal bed.
Times include the optional bounds prepass separately. Uploads, CPU and game rendering are excluded.
"""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import shutil
from statistics import median
import struct
from tempfile import TemporaryDirectory

from compile_glsl import ROOT
from validate_gpu import Runner, quote, require, shader_digest, write_text
from validate_gpu_water_transport import slab_scene, FORMATS
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix, perspective_matrix


def measure(runner, scene, width, height):
    names = tuple(scene['textures'])
    # Horizontal planes and a pitched, unrolled camera produce constant depth
    # along each scanline. Use authored constant radiance along that scanline.
    texture_lines = []
    for name in names:
        path = runner.scratch/(name + '.raw')
        with path.open('xb') as stream:
            for row in scene['textures'][name]:
                stream.write(struct.pack('<4f',*row[1])*width)
        fmt = 'RGBA16F' if name == 'colortex0' else FORMATS[name]
        texture_lines.append(f'texture {quote(name)} {width} {height} {fmt} {quote(path)}')
    projection = perspective_matrix(50., width/height, .05, 128.)
    uniforms = {name: (kind, values) for name,kind,values in scene['uniforms']}
    uniforms['gbufferProjection'] = ('m4',matrix_uniform(projection))
    uniforms['gbufferProjectionInverse'] = ('m4',matrix_uniform(inverse_matrix(projection)))
    uniform_lines = ['uniform {} {} {}'.format(quote(name),kind,' '.join(map(str,values)))
                     for name,(kind,values) in uniforms.items()]
    results = {}
    coarse_path=runner.scratch/'bounds.raw'
    pair=runner.pair('deferred1',dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_TRACE_TILES=1))
    cw,ch=(width+7)//8,(height+7)//8
    manifest=runner.scratch/'bounds.txt'
    write_text(manifest,'\n'.join(['shaders {} {}'.format(*map(quote,pair)),
        f'target {cw} {ch} R32F {quote(coarse_path)}',
        *[line for line in texture_lines if any(quote(n) in line for n in ('colortex5','colortex6','depthtex1'))],
        *[line for line in uniform_lines if quote('gbufferProjectionInverse') in line]])+'\n')
    prepass=runner.call('--time-render',manifest)
    ms=[v/1e6 for v in prepass['gpu_nanoseconds']]
    results['bounds'] = dict(samples_ms=ms,median_ms=median(ms),p95_ms=sorted(ms)[-2])
    for label, options in (('copy',{'WATER_OPTICS':0}),
                           ('transport',{'WATER_OPTICS':1,'WATER_SCREEN_REFLECTIONS':0}),
                           ('transport_ssr64',{'WATER_OPTICS':1,'WATER_TRACE_TILES':0}),
                           ('transport_ssr64_bounds',{'WATER_OPTICS':1,'WATER_TRACE_TILES':1})):
        pair = runner.pair('composite1',dict(options, IRIS_FEATURE_PER_BUFFER_BLENDING=True))
        output = runner.scratch/(label+'.raw')
        spec = runner.scratch/(label+'.txt')
        inputs=list(texture_lines)
        if label.endswith('_bounds'):
            inputs.append(f'texture "colortex10" {cw} {ch} R32F {quote(coarse_path)}')
        write_text(spec,'\n'.join(['shaders {} {}'.format(*map(quote,pair)),
                                 f'target {width} {height} RGBA16F {quote(output)}',
                                 *inputs,*uniform_lines])+'\n')
        payload = runner.call('--time-render',spec)
        samples = [v/1e6 for v in payload['gpu_nanoseconds']]
        require(len(samples)==25 and all(math.isfinite(v) and v>0 for v in samples),'Invalid GPU timings')
        with output.open('rb') as stream:
            stream.seek(16 * ((height//2)*width + width//2))
            pixel = struct.unpack('<4f',stream.read(16))
            stream.seek(0)
            image_hash = hashlib.file_digest(stream,'sha256').hexdigest()
        require(all(math.isfinite(c) and c>=0 for c in pixel), 'Invalid center pixel')
        results[label] = dict(samples_ms=samples,median_ms=median(samples),
                              p95_ms=sorted(samples)[math.ceil(.95*len(samples))-1],center=pixel,
                              output_sha256=image_hash)
    require(results['transport_ssr64']['output_sha256']==results['transport_ssr64_bounds']['output_sha256'],
            'Depth acceleration changed the image')
    require(results['copy']['center'][:3]!=results['transport']['center'][:3], 'Water path inactive')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default=shutil.which('g++'))
    parser.add_argument('--report',type=Path,help='New report inside the project')
    args=parser.parse_args()
    digest=shader_digest()
    width,height=1280,720
    parent=ROOT.parent.resolve()
    with TemporaryDirectory(prefix='aurora-water-time-',dir=parent) as directory:
        scratch=Path(directory).resolve()
        require(scratch.parent==parent and scratch.name.startswith('aurora-water-time-'),'Invalid scratch')
        runner=Runner(scratch,args.cxx)
        scene=slab_scene(3,height,depth=2.,pitch=45.)
        result=measure(runner,scene,width,height)
    require(shader_digest()==digest,'Shader changed during benchmark')
    report=dict(date_utc=datetime.now(timezone.utc).isoformat(),shader_sha256=digest,
                gl=runner.gl,width=width,height=height,warmup=6,samples=25,
                scope='GL_TIME_ELAPSED, separate warmed full-screen composite and one-eighth-width/height depth prepass. '
                      'All-miss rays above a two-meter slab. Sum of medians is indicative, not paired frame timing. '
                      'Copy is a bandwidth reference; Iris skips this entire pass when optics is disabled. '
                      'No geometry/other passes, game frame timing, or FPS measurement.',
                results=result)
    if args.report:
        path=(ROOT/args.report).resolve()
        require(ROOT.resolve() in path.parents,'Report must stay in project')
        write_text(path,json.dumps(report,indent=2,allow_nan=False)+'\n')
    for name,values in result.items():
        print(f"{name}: median {values['median_ms']:.3f} ms, p95 {values['p95_ms']:.3f} ms")
