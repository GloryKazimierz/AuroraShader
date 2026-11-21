"""Native comparative checks for conservative empty-space reflection skipping."""
from compile_glsl import SHADERS, expand
from validate_gpu import require
from validate_gpu_depth import matrix_uniform
from validate_water_screen_reflection import trace_fixtures


def bounds_tests(runner):
    settings=dict(WATER_OPTICS=1, IRIS_FEATURE_PER_BUFFER_BLENDING=True)
    shader=('#version 330 compatibility\n'+expand(SHADERS/'lib/water_optics_settings.glsl')+'\n'
            +expand(SHADERS/'lib/water_screen_reflection.glsl')+'''
uniform sampler2D queryOrigins, queryDirections;
layout(location=0) out vec4 result;
layout(location=1) out vec4 detail;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy), hitPixel;
    vec3 point, radiance;
    float dist, confidence;
    int steps, reason;
    bool hit=traceWaterSceneClassified(texelFetch(queryOrigins,p,0).xyz,texelFetch(queryDirections,p,0).xyz,
                                      hitPixel,point,radiance,dist,confidence,steps,reason);
    result=vec4(float(reason),vec2(hitPixel),confidence);
    detail=vec4(radiance,hit?dist:float(steps));
}
''')
    passed,skips,hits=0,0,0
    prepass=runner.pair('deferred1',dict(settings,WATER_TRACE_TILES=1))
    pairs={(budget,enabled):runner.pair('composite1',dict(settings,WATER_TRACE_TILES=enabled,
                            WATER_REFLECTION_STEPS=budget),shader)
           for budget in (64,128) for enabled in (0,1)}
    fixtures=list(trace_fixtures())
    # A distant continuous plane and the same frame with one hidden occluder form
    # positive controls for a true empty bound and a mandatory fallback to traversal.
    from copy import deepcopy
    clear=deepcopy(next(f for f in fixtures if f['name']=='unknown-occluder'))
    w,h=len(clear['opaque_depth'][0]),len(clear['opaque_depth'])
    clear['name']='unobstructed sky'
    clear['opaque_depth']=clear['depth']=[[1.0]*w for _ in range(h)]
    clear['color']=[[(0,0,0,0)]*w for _ in range(h)]
    fixtures.append(clear)
    for f in fixtures:
        name=f['name']
        w,h=len(f['opaque_depth'][0]),len(f['opaque_depth'])
        def depth(data):
            return [[(v,0,0,1) for v in row] for row in data]
        surfaces=[('depthtex1',depth(f['opaque_depth']),'R32F'),('colortex6',depth(f['depth']),'R32F'),
                  ('colortex5',f['color'],'RGBA16F')]
        matrices=[('gbufferProjectionInverse','m4',matrix_uniform(f['inverse_projection'])),
                  ('gbufferProjection','m4',matrix_uniform(f['projection']))]
        coarse=runner.render(name+'-bounds',prepass,(w+7)//8,(h+7)//8,surfaces,matrices[:1],storage='R32F')
        queries=[('queryOrigins',[[tuple(q['origin'])+(1,) for q in f['queries']]],'RGBA32F'),
                 ('queryDirections',[[tuple(q['direction'])+(1,) for q in f['queries']]],'RGBA32F')]
        for budget in (64,128):
            observed={}
            for enabled in (0,1):
                textures=surfaces+queries+([('colortex10',coarse,'R32F')] if enabled else [])
                for slot in (0,1):
                    observed[enabled,slot]=runner.render(name,pairs[budget,enabled],len(f['queries']),1,
                        textures,matrices,extra_targets=((1,1,'RGBA32F'),),read_target=slot)[0]
            for a,b,c,d in zip(observed[0,0],observed[1,0],observed[0,1],observed[1,1]):
                require(a==b,name+': hit, status, pixel, or confidence changed')
                require(c[:3]==d[:3],name+': reflected radiance changed')
                if a[0]==1:
                    require(c[3]==d[3],name+': path length changed')
                    hits+=1
                else:
                    require(c[3]==d[3] or (a[0]==0 and d[3]==0),name+': invalid early termination')
                    skips+=d[3]==0 and c[3]>0
                passed+=1
    # 17x11 exercises both full tiles and the last partial row/column. Unknown
    # opaque is still a conservative bound; inconsistent coverage disables a tile.
    from validate_gpu_water_transport import slab_scene
    sample=slab_scene(17,11,depth=2.,pitch=75.)
    surfaces=sample['textures']
    for y in range(11):
        for x in range(17):
            surfaces['colortex5'][y][x]=(0.,0.,0.,0.)
            surfaces['colortex6'][y][x]=(1.,0.,0.,1.)
            surfaces['depthtex1'][y][x]=(1.,0.,0.,1.)
    surfaces['depthtex1'][10][16]=(.5,0.,0.,1.)
    surfaces['colortex5'][0][8]=(.3,0.,0.,0.)
    inputs=[(name,surfaces[name],fmt) for name,fmt in
            (('colortex5','RGBA16F'),('colortex6','R32F'),('depthtex1','R32F'))]
    inverse=[u for u in sample['uniforms'] if u[0]=='gbufferProjectionInverse']
    near,far=.05,128.
    expected=2.*near*far/(far+near)
    for width,height in ((2,1),(3,2)):
        actual=runner.render('odd-depth-bounds',prepass,width,height,inputs,inverse,storage='R32F')
        require(actual[0][0][0]>1e19 and actual[0][1][0]==-1.,'Invalid tile accepted or sky rejected')
        if width==3:
            require(abs(actual[1][2][0]-expected)<1e-6,'Partial tile lost a one-pixel obstacle')
    require(skips>0 and hits>0,'Positive controls did not exercise both paths')
    return dict(scenes=len(fixtures),rays=passed,hits=hits,verified_early_exits=skips,odd_viewport=[17,11],checked_tile_shapes=[[2,1],[3,2]])
