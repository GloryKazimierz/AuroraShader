'''M18 native-driver helper fixtures; no Minecraft vertex attributes or chunk draws.'''
import math

from compile_glsl import SHADERS, expand
from validate_foliage import (IDENTITY4, MAX_FIELD, f32, foliage_clip,
                              foliage_displacement, inverse_matrix, matrix_vector)


def matrix_uniform(matrix):
    return [matrix[row][col] for col in range(4) for row in range(4)]


def quantized(values):
    return tuple(f32(x) for x in values)


def foliage_tests(runner,compare):
    header='#version 330 compatibility\n'+expand(SHADERS/'lib/foliage.glsl')+'''
uniform sampler2D testPositions;
uniform sampler2D testMaterials;
uniform sampler2D testMidBlock;
layout(location=0) out vec4 color;
'''
    displacement=header+'''
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    color=vec4(foliageDisplacement(texelFetch(testPositions,p,0).xyz,
        texelFetch(testMaterials,p,0).xy,texelFetch(testMidBlock,p,0)),1.0);
}
'''
    clip=header+'''
uniform sampler2D testBaseline;
uniform mat4 testInverse;
uniform mat4 testModelView;
uniform mat4 testProjection;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    color=foliageWindClip(texelFetch(testBaseline,p,0),texelFetch(testPositions,p,0),
        testInverse,testModelView,testProjection,texelFetch(testMaterials,p,0).xy,
        texelFetch(testMidBlock,p,0));
}
'''
    # Each row includes real classifiers, roots/tips, quantization and rejection cases.
    specs=[(10002,0,0),(10002,-1,math.nan),(10003,0,32),(10003,-1,31),
           (10003,0,30),(10003,0,0),(10003,0,-32),(10004,0,32),
           (10004,0,-32),(10005,0,32),(10005,-1,-32),(10005,0,math.nan),
           (10001,1,0),(10001,0,0),(10002,1,0),(10002,2,0),
           (10002.5,0,0),(0,0,0),(math.nan,0,0),(10002,math.nan,0),
           (10003,0,math.inf),(10003,0,-64),(10002,0,0),(10002,0,0)]
    width,height=8,3
    def rows(pixels):
        return [pixels[y*width:(y+1)*width] for y in range(height)]
    positions=[(f32((i%8)*7.25-20.125),1.625,f32((i//8)*13.5-17.75),1) for i in range(24)]
    positions[9]=positions[8]  # Tall lower top and upper bottom share this world point.
    positions[22]=(math.nan,0,0,1); positions[23]=(0,math.inf,0,1)
    materials=rows([quantized((kind,fluid,0,1)) for kind,fluid,_ in specs])
    mid=rows([quantized((0,y,0,0)) for _,_,y in specs])
    cases=[]
    for anchor in ((0,64,0),(-1,64,-129),(128,64,127),(30000000,100,-30000000),
                   (-2147483648,0,2147483647)):
        for seconds in (0,17,3599.999):
            cases.append(dict(anchor=anchor,seconds=seconds))
    cases += [dict(seconds=t,speed=s) for t in (199.999,200.001,3600.001) for s in (0,1,2)]
    cases += [dict(strength=0),dict(strength=.25),dict(strength=1),dict(enabled=0),
              dict(mode=0),dict(debug=5),dict(seconds=math.nan),dict(seconds=math.inf),
              dict(seconds=-1),dict(fraction=(math.nan,.625,.75)),dict(fraction=(.25,math.nan,.75))]
    comparisons=[]; exact=0; bounds=0
    for index,case in enumerate(cases):
        options=dict(camera_int=case.get('anchor',(-129,64,128)),
                     camera_fract=case.get('fraction',(.25,.625,.75)),
                     seconds=f32(case.get('seconds',17)),speed=case.get('speed',1),
                     strength=case.get('strength',.5),enabled=case.get('enabled',1),
                     mode=case.get('mode',1),debug=case.get('debug',0),fp32_time=True)
        uniforms=[('cameraPositionInt','i3',options['camera_int']),
                  ('cameraPositionFract','f3',options['camera_fract']),
                  ('frameTimeCounter','f1',(options['seconds'],))]
        config=dict(FOLIAGE_WIND=options['enabled'],FOLIAGE_WIND_STRENGTH=float(options['strength']),
                    FOLIAGE_WIND_SPEED=options['speed'],SCENE_COLOR_MODE=options['mode'],DEBUG_VIEW=options['debug'])
        textures=[('testPositions',rows(positions),'RGBA32F'),('testMaterials',materials,'RGBA32F'),
                  ('testMidBlock',mid,'RGBA32F')]
        bypass=not options['enabled'] or not options['mode'] or options['debug'] or options['strength']==0
        optional=[n for n,_,_ in textures+uniforms] if bypass else ['frameTimeCounter'] if options['speed']==0 else []
        label='foliage-field-{}'.format(index)
        actual=runner.render(label,runner.pair('composite',config,displacement),width,height,textures,uniforms,optional=optional)
        expected=rows([foliage_displacement(p[:3],materials[i//8][i%8][:2],mid[i//8][i%8],**options)+(1,)
                       for i,p in enumerate(positions)])
        # Harmonic phases can reach 53 cycles before fract. FP32 phase ULPs produce
        # a few microblocks of error against the independent double spatial oracle.
        comparisons.append(compare(actual,expected,label,absolute=1e-5))
        for i in range(24):
            a,e=actual[i//8][i%8],expected[i//8][i%8]
            if e==(0,0,0,1):
                if a!=e: raise RuntimeError(label+': nonexact displacement bypass')
                exact+=1
            if a[1]!=0 or a[3]!=1: raise RuntimeError(label+': vertical motion or coverage')
            amplitude=.08 if specs[i][0]==10002 else .20
            if math.hypot(a[0],a[2])>amplitude*options['strength']*MAX_FIELD+1e-7:
                raise RuntimeError(label+': analytic displacement bound exceeded')
            bounds+=1
        if actual[1][0]!=actual[1][1]: raise RuntimeError(label+': tall grass split apart')
    # Clip tests exercise real helper matrix operations, including a nontrivial w.
    # Dyadic matrix entries isolate pass-transform behavior from inverse rounding.
    terrain=((0,0,-1,.5),(0,1,0,-.25),(1,0,0,.125),(0,0,0,1))
    shadow=((.5,0,0,-1),(0,0,2,.5),(0,-1,0,.25),(0,0,0,1))
    projection=((1,.25,0,.5),(0,2,.125,-1),(.5,0,1,0),(.125,0,.25,1))
    matrices=[dict(label='terrain',model=terrain),dict(label='shadow',model=shadow),
              dict(label='identity',model=IDENTITY4),dict(label='homogeneous',model=terrain,homogeneous=2),
              dict(label='off',model=terrain,enabled=0),dict(label='zero',model=terrain,strength=0),
              dict(label='legacy',model=terrain,mode=0),dict(label='debug',model=terrain,debug=6),
              dict(label='zero-w',model=terrain,zero_w=True),dict(label='invalid-inverse',model=terrain,bad_inverse=True),
              dict(label='invalid-projection',model=terrain,bad_projection=True)]
    baseline=rows([(i*.125-.5,.25,.5,1.0+i*.0625) for i in range(24)])
    # Invalid player inputs are already tested above; use finite view inputs here.
    clean=list(positions);clean[22]=(1,2,3,1);clean[23]=(-1,-2,-3,1)
    clip_comparisons=[]; clip_exact=0
    for case in matrices:
        model=case['model']; inverse=inverse_matrix(model); proj=projection
        views=[quantized(tuple(c*case.get('homogeneous',1) for c in matrix_vector(model,p))) for p in clean]
        if case.get('zero_w'): inverse=tuple(tuple(0 if r==3 else v for v in row) for r,row in enumerate(inverse))
        if case.get('bad_inverse'): inverse=((math.nan,0,0,0),)+inverse[1:]
        if case.get('bad_projection'): proj=((math.nan,0,0,0),)+proj[1:]
        opts=dict(camera_int=(-129,64,128),camera_fract=(.25,.625,.75),seconds=17,
                  strength=case.get('strength',.5),enabled=case.get('enabled',1),
                  mode=case.get('mode',1),debug=case.get('debug',0),fp32_time=True)
        config=dict(FOLIAGE_WIND=opts['enabled'],FOLIAGE_WIND_STRENGTH=float(opts['strength']),
                    SCENE_COLOR_MODE=opts['mode'],DEBUG_VIEW=opts['debug'])
        textures=[('testPositions',rows(views),'RGBA32F'),('testMaterials',materials,'RGBA32F'),
                  ('testMidBlock',mid,'RGBA32F'),('testBaseline',baseline,'RGBA32F')]
        uniforms=[('testInverse','m4',matrix_uniform(inverse)),('testModelView','m4',matrix_uniform(model)),
                  ('testProjection','m4',matrix_uniform(proj)),('cameraPositionInt','i3',opts['camera_int']),
                  ('cameraPositionFract','f3',opts['camera_fract']),('frameTimeCounter','f1',(17,))]
        bypass=not opts['enabled'] or not opts['mode'] or opts['debug'] or opts['strength']==0
        optional=[n for n,_,_ in textures+uniforms if n!='testBaseline'] if bypass else []
        label='foliage-clip-'+case['label']
        actual=runner.render(label,runner.pair('composite',config,clip),width,height,textures,uniforms,optional=optional)
        expected=rows([foliage_clip(baseline[i//8][i%8],v,inverse,model,proj,
                                  materials[i//8][i%8][:2],mid[i//8][i%8],**opts) for i,v in enumerate(views)])
        clip_comparisons.append(compare(actual,expected,label,absolute=2e-5))
        for y in range(height):
            for x in range(width):
                if expected[y][x]==baseline[y][x]:
                    if actual[y][x]!=baseline[y][x]: raise RuntimeError(label+': nonexact clip bypass')
                    clip_exact+=1
    return dict(displacement_cases=len(cases),displacement_samples=bounds,exact_zero_samples=exact,
                clip_cases=len(matrices),clip_samples=len(matrices)*width*height,exact_clip_bypasses=clip_exact,
                comparisons=comparisons,clip_comparisons=clip_comparisons,
                input='Actual shared GLSL helpers in synthetic fragment wrappers; no Iris attribute binding, chunk mesh, shadow rasterization or frame timing')
