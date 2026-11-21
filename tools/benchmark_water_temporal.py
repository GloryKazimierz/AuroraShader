"""K isolated recombine GPU timer: no Minecraft FPS claim or feedback timing."""
import hashlib,json,math,statistics,struct,tempfile
from pathlib import Path
from compile_glsl import ROOT
from validate_gpu import Runner,quote,write_text,require,shader_digest
from validate_gpu_water_temporal import temporal_scene,set_uniform
from validate_gpu_depth import matrix_uniform
from validate_water_depth import perspective_matrix,inverse_matrix


def measure(runner,width=1280,height=720):
    scene=temporal_scene(3,height);t=scene['textures']
    projection=perspective_matrix(50,width/height,.05,128)
    set_uniform(scene,'gbufferProjection','m4',matrix_uniform(projection))
    set_uniform(scene,'gbufferPreviousProjection','m4',matrix_uniform(projection))
    set_uniform(scene,'gbufferProjectionInverse','m4',matrix_uniform(inverse_matrix(projection)))
    formats=dict(colortex0='RGBA16F',colortex3='RGBA16F',colortex7='RGBA32F',colortex8='RGBA8',colortex12='RGBA32F',depthtex0='R32F')
    inputs=[]
    for name,fmt in formats.items():
        path=runner.scratch/(name+'.raw');tw,th=(width//2,height//2) if name=='colortex3' else (width,height)
        with path.open('xb') as stream:
            for y in range(th):
                if name=='colortex0':row=[tuple(c+(.01 if (x+y)%2 else -.01) for c in (.3,.4,.2))+(.5,) for x in range(tw)]
                elif name=='colortex3':row=[(2,1,.5,1)]*tw
                elif name=='colortex8':row=[(1/255,0,1,0)]*tw
                elif name=='colortex12':
                    row=[(.3,.4,.2,t['colortex7'][y][1][3])]*tw
                    if y==0:row[:2]=[(200.,float(width),float(height),1.),t[name][0][1]]
                else:row=[t[name][y][1]]*tw
                stream.write(struct.pack('<'+str(tw*4)+'f',*(v for p in row for v in p)))
        inputs.append(f'texture {quote(name)} {tw} {th} {fmt} {quote(path)}')
    uniforms=['uniform {} {} {}'.format(quote(n),k,' '.join(map(str,v))) for n,k,v in scene['uniforms']]
    results={}
    for enabled in (0,1):
        label='temporal_on' if enabled else 'recombine_only'
        pair=runner.pair('composite5',dict(WATER_OPTICS=1,WATER_TEMPORAL=enabled,IRIS_FEATURE_PER_BUFFER_BLENDING=True))
        output=runner.scratch/(label+'.raw');spec=runner.scratch/(label+'.txt')
        lines=['shaders {} {}'.format(*map(quote,pair)),f'target {width} {height} RGBA16F {quote(output)}']
        if enabled:lines.append('color_target 1 1 RGBA32F')
        write_text(spec,'\n'.join(lines+inputs+uniforms)+'\n')
        result=runner.call('--time-render',spec);samples=[n/1e6 for n in result['gpu_nanoseconds']]
        require(len(samples)==25 and all(math.isfinite(v) and v>0 for v in samples),'Bad timer samples')
        with output.open('rb') as stream:
            stream.seek(16*((height//2)*width+width//2));center=struct.unpack('<4f',stream.read(16))
            stream.seek(0);digest=hashlib.file_digest(stream,'sha256').hexdigest()
        results[label]=dict(samples_ms=samples,median_ms=statistics.median(samples),p95_ms=sorted(samples)[23],center=center,sha256=digest)
    require(results['temporal_on']['sha256']!=results['recombine_only']['sha256'],'Temporal timing path had no effect')
    return results

if __name__=='__main__':
    before=shader_digest()
    with tempfile.TemporaryDirectory(prefix='K-gpu-time-',dir=ROOT.parent) as d:
        runner=Runner(Path(d),r'C:\msys64\ucrt64\bin\g++.exe');results=measure(runner)
    require(before==shader_digest(),'Shader modified during timing')
    report=dict(shader_digest=before,gl=runner.gl,resolution=[1280,720],warmup=6,samples=25,results=results,
                scope='GL_TIME_ELAPSED for isolated full-resolution recombine, almost all confirmed horizontal water, valid stationary history, two MRTs when enabled. No other passes, CPU/upload/readback time, feedback sequence, Minecraft or FPS claim.')
    path=ROOT/'docs/validation/K_timing.json';require(not path.exists(),'Refusing existing timer report')
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for k,v in results.items():print(k, v['median_ms'],v['p95_ms'])
