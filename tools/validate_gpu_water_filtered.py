"""W2 native derivative, filtered-wave and actual-fragment compatibility checks.

Uses synthetic geometry and driver derivatives. This is not Minecraft/Iris runtime.
"""
import functools
import math
import re
import subprocess

from compile_glsl import ROOT, SHADERS, expand
from validate_gpu import write_text, require
from validate_gpu_depth import matrix_uniform
from validate_water_waves import f32, anchored_tile, matrix_vector, unit, wave_normal_from_gradient
from validate_water_filtered_waves import filtered_gradient, pixel_filter, WAVES
from validate_water_depth import inverse_matrix, perspective_matrix

BASELINE = '5d3e917'


def filtered_wave_tests(runner, compare):
    helper = '#version 330 compatibility\n' + expand(SHADERS/'lib/water_filtered_waves.glsl')
    direct = helper + '''
uniform sampler2D testWave;
uniform sampler2D testFootprint;
layout(location=0) out vec4 color;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec2 wave=texelFetch(testWave,p,0).xy;
    vec4 footprint=texelFetch(testFootprint,p,0);
    float value=waterWavePixelFilter(wave,footprint.xy,footprint.zw);
    color=vec4(value,value,value,1.0);
}
'''
    # Thresholds independent of production wave vectors, plus anisotropic real waves.
    specimens=[((128,0),(q,0),(0,0)) for q in
               (0,1e-7,.01,.2499,.25,.2501,.4999,.5,.5001,-.25,-.5,1e30)]
    specimens += [((kx,kz),dx,dy) for kx,kz,_,_ in WAVES for dx,dy in
                  (((.0625,0),(0,.0625)),((.25,.125),(-.0625,.5)),
                   ((2,0),(0,.015625)),((0,8),(.25,0)))]
    specimens += [((128,0),dx,dy) for dx,dy in
                  (((math.nan,0),(0,0)),((math.inf,0),(0,0)),((0,0),(0,math.nan)),
                   ((0,0),(math.inf,0)))]
    width,height=8,5
    require(len(specimens)==width*height,'Filter fixture size')
    def rows(items,w=width): return [items[i:i+w] for i in range(0,len(items),w)]
    waves=[tuple(map(f32,k))+(0,1) for k,_,_ in specimens]
    footprints=[tuple(map(f32,dx+dy)) for _,dx,dy in specimens]
    expected=[]
    for k,f in zip(waves,footprints):
        value=pixel_filter(k[:2],f[:2],f[2:])
        expected.append((value,value,value,1))
    actual=runner.render('filtered-wave-pixel-filter',runner.pair('composite',wrapper=direct),
                         width,height,[('testWave',rows(waves),'RGBA32F'),
                                       ('testFootprint',rows(footprints),'RGBA32F')])
    comparisons=[compare(actual,rows(expected),'filtered-wave-pixel-filter',absolute=4e-7)]
    flat=[p for row in actual for p in row]
    for got,want in zip(flat,expected):
        if want[0]==0: require(got==(0,0,0,1),'Rejected footprint must be exactly zero')
        require(0<=got[0]<=1,'Pixel filter outside [0,1]')

    common='''
uniform vec3 testOrigin;
uniform vec3 testStepX;
uniform vec3 testStepY;
uniform vec3 testNormal;
uniform float testEligibility;
uniform int testDiscard;
layout(location=0) out vec4 color;
void main() {
    vec3 viewPosition=testOrigin+testStepX*gl_FragCoord.x+testStepY*gl_FragCoord.y;
    vec2 worldDx=(mat3(gbufferModelViewInverse)*dFdx(viewPosition)).xz;
    vec2 worldDy=(mat3(gbufferModelViewInverse)*dFdy(viewPosition)).xz;
    // Deliberately discard AFTER derivatives; adjacent surviving pixels still need them.
    if (testDiscard!=0 && (int(gl_FragCoord.x)+int(gl_FragCoord.y))%3==0) discard;
    color=vec4(waterFilteredWaveNormal(testNormal,viewPosition,testEligibility,worldDx,worldDy),1.0);
}
'''
    normal_wrapper=helper+common
    legacy_wrapper=helper+common.replace(
        'waterFilteredWaveNormal(testNormal,viewPosition,testEligibility,worldDx,worldDy)',
        'waterWaveNormal(testNormal,viewPosition,testEligibility)')
    derivative_wrapper=helper+common.replace(
        'vec4(waterFilteredWaveNormal(testNormal,viewPosition,testEligibility,worldDx,worldDy),1.0)',
        'vec4(worldDx,worldDy)')
    cases=[
        dict(label='near',stepx=(.03125,0,0),stepy=(0,0,.03125),derivative=True),
        dict(label='mid',stepx=(.125,0,0),stepy=(0,0,.125),derivative=True),
        dict(label='grazing',stepx=(.0625,0,0),stepy=(0,0,4),derivative=True),
        dict(label='far',stepx=(16,0,0),stepy=(0,0,16),derivative=True),
        dict(label='tile-seam',origin=(127.75,0,127.75),stepx=(.0625,0,0),stepy=(0,0,.0625),derivative=True),
        dict(label='rotated',inverse=((0,0,1),(0,1,0),(-1,0,0)),derivative=True),
        dict(label='nonuniform',inverse=((.5,0,0),(0,2,0),(0,0,4)),derivative=True),
        dict(label='translation',translation=(.25,1.625,-.125)),
        dict(label='negative-anchor',anchor=(-129,64,-1)),
        dict(label='world-limit',anchor=(30000000,64,-30000000)),
        dict(label='integer-extremes',anchor=(-2147483648,0,2147483647)),
        dict(label='static',speed=0),dict(label='fast',speed=2),
        dict(label='cycle-left',seconds=199.999),dict(label='cycle-right',seconds=200.001),
        dict(label='reset-left',seconds=3599.999),dict(label='reset-right',seconds=3600.001),
        dict(label='bad-time',seconds=math.nan),dict(label='infinite-time',seconds=math.inf),
        dict(label='negative-time',seconds=-1),
        dict(label='maximum',strength=1),dict(label='partial',eligibility=.25),
        dict(label='excluded',eligibility=0),dict(label='zero',strength=0),
        dict(label='disabled',enabled=0),dict(label='original',detail=0),
        dict(label='original-grazing',detail=0,stepy=(0,0,4)),
        dict(label='discard',discard=1,derivative=True),
        dict(label='singular',inverse=((0,0,0),(0,0,0),(0,0,0))),
    ]
    width,height=12,10
    sentinel=(-11931.25,-719.5,-37.25,-13)
    normal_samples=0; exact_bypass=0; derivative_samples=0; detail_changed=0
    for case in cases:
        label='filtered-wave-'+case['label']
        inverse=case.get('inverse',((1,0,0),(0,1,0),(0,0,1)))
        translation=case.get('translation',(0,0,0))
        matrix=tuple(tuple(inverse[r][c] if r<3 and c<3 else translation[r] if r<3 and c==3
                           else 1 if r==c==3 else 0 for c in range(4)) for r in range(4))
        origin=case.get('origin',(-.75,1.625,-1.75))
        sx=case.get('stepx',(.0625,0,.03125));sy=case.get('stepy',(-.03125,0,.0625))
        dx3=matrix_vector(inverse,sx);dy3=matrix_vector(inverse,sy)
        dx=(dx3[0],dx3[2]);dy=(dy3[0],dy3[2])
        anchor=case.get('anchor',(0,64,0));fraction=(.25,.625,.75)
        time=f32(case.get('seconds',17));speed=case.get('speed',1)
        # Match the actual option's floating-point tokens (0.0/0.3/0.6/1.0).
        # Intel 31.0.101.3962 misfolds synthetic clamp(1,0.0,1.0) to the
        # FP32 bit pattern of int1; that unlisted token is not an Iris UI value.
        strength=float(case.get('strength',.6));eligibility=case.get('eligibility',1)
        normal_matrix=tuple(tuple(inverse[j][i] for j in range(3)) for i in range(3))
        normal=tuple(map(f32,unit(matrix_vector(normal_matrix,(0,1,0))) or (0,1,0)))
        options=dict(WATER_SURFACE_DETAIL=case.get('detail',1),WATER_WAVES=case.get('enabled',1),
                     WATER_WAVE_STRENGTH=strength,WATER_WAVE_SPEED=speed)
        uniforms=[('cameraPositionInt','i3',anchor),('cameraPositionFract','f3',fraction),
                  ('frameTimeCounter','f1',(time,)),('gbufferModelViewInverse','m4',matrix_uniform(matrix)),
                  ('testOrigin','f3',origin),('testStepX','f3',sx),('testStepY','f3',sy),
                  ('testNormal','f3',normal),('testEligibility','f1',(eligibility,)),
                  ('testDiscard','i1',(case.get('discard',0),))]
        bypass=not options['WATER_WAVES'] or strength==0 or eligibility==0 or case['label']=='singular'
        optional=[]
        if not options['WATER_WAVES'] or strength==0:
            optional=[name for name,_,_ in uniforms if name not in ('testNormal','testDiscard')]
        elif speed==0: optional=['frameTimeCounter']
        got=runner.render(label,runner.pair('composite',options,normal_wrapper),width,height,
                          uniforms=uniforms,optional=optional)
        if options['WATER_SURFACE_DETAIL']==0:
            old=runner.render(label+'-reference',runner.pair('composite',options,legacy_wrapper),
                              width,height,uniforms=uniforms,optional=optional)
            comparisons.append(compare(got,old,label+'-exact-original'))
            expected=old
        else:
            expected=[]
            for y in range(height):
                row=[]
                for x in range(width):
                    if case.get('discard') and (x+y)%3==0:
                        row.append(sentinel);continue
                    position=tuple(f32(o+a*(x+.5)+b*(y+.5)) for o,a,b in zip(origin,sx,sy))
                    player=tuple(v+t for v,t in zip(matrix_vector(inverse,position),translation))
                    gradient=filtered_gradient(anchored_tile(anchor,fraction,player),time,speed,dx,dy,fp32=True)
                    n=wave_normal_from_gradient(normal,gradient,normal_matrix,strength=strength,
                                                eligibility=eligibility,enabled=bool(options['WATER_WAVES']))
                    row.append(n+(1,))
                expected.append(row)
            # Dyadic positions/matrices eliminate footprint cancellation in these fixtures.
            # Remaining clock/phase transcendental FP32 roundoff has the same bounded
            # 6e-5 allowance as M14; exact bypass and far-flat cases remain exact.
            exact=bypass or case['label']=='far'
            comparisons.append(compare(got,expected,label,absolute=0 if exact else 6e-5))
        for y in range(height):
            for x in range(width):
                if case.get('discard') and (x+y)%3==0:
                    require(got[y][x]==sentinel,label+': discard coverage changed')
                else:
                    require(got[y][x][3]==1,label+': alpha/coverage mismatch')
                    if bypass:
                        require(got[y][x]==normal+(1,),label+': bypass is not exact')
                        exact_bypass+=1
                    normal_samples+=1
        if case.get('derivative'):
            dopt=[name for name,_,_ in uniforms if name not in
                  ('gbufferModelViewInverse','testOrigin','testStepX','testStepY','testDiscard')]
            derivative=runner.render(label+'-derivative',runner.pair('composite',options,derivative_wrapper),
                                     width,height,uniforms=uniforms,optional=dopt)
            want=[[sentinel if case.get('discard') and (x+y)%3==0 else dx+dy
                   for x in range(width)] for y in range(height)]
            comparisons.append(compare(derivative,want,label+'-actual-derivative'))
            derivative_samples+=width*height
        if case['label']=='near':
            legacy=runner.render(label+'-old-comparison',runner.pair('composite',options,legacy_wrapper),
                                 width,height,uniforms=uniforms)
            detail_changed=sum(got[y][x]!=legacy[y][x] for y in range(height) for x in range(width))
            require(detail_changed>0,'Near detail did not alter normals')
    integrated=actual_fragment_tests(runner,compare)
    return dict(filter_samples=len(specimens),normal_cases=len(cases),normal_samples=normal_samples,
                exact_bypass_samples=exact_bypass,derivative_samples=derivative_samples,
                changed_near_normals=detail_changed,comparisons=comparisons,actual_fragment=integrated,
                scope='Actual helper and dFdx/dFdy on dyadic affine synthetic fields; tile seam, anisotropy, discard and transforms. Not Minecraft rasterization.')


@functools.lru_cache(maxsize=None)
def historical(relative):
    source=subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':shaders/'+relative]).decode('utf-8')
    return re.sub(r'^#include "([^"]+)"\s*$',lambda m:historical(m[1].lstrip('/')),source,flags=re.M)


def actual_fragment_tests(runner,compare):
    runner.sequence += 1
    vertex=runner.scratch/f'w2-synthetic-water-{runner.sequence:05d}.vert'
    write_text(vertex,'''#version 330 compatibility
uniform int testMaterial;
out vec2 lmcoord;
out vec2 texcoord;
out vec4 glcolor;
out vec3 normalView;
flat out int waterSurface;
void main(){
    gl_Position=gl_Vertex;
    texcoord=gl_MultiTexCoord0.xy;
    lmcoord=vec2(.5/16.0,15.5/16.0);
    glcolor=vec4(1.0);
    normalView=vec3(0.0,1.0,0.0);
    waterSurface=testMaterial;
}
''')
    width,height=12,10
    projection=inverse_matrix(perspective_matrix(70,width/height,1,192))
    uniforms=[('testMaterial','i1',(1,)),('viewWidth','f1',(width,)),('viewHeight','f1',(height,)),
              ('gbufferProjectionInverse','m4',matrix_uniform(projection)),
              ('gbufferModelViewInverse','m4',matrix_uniform(((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1)))),
              ('cameraPositionInt','i3',(0,64,0)),('cameraPositionFract','f3',(.25,.625,.75)),
              ('frameTimeCounter','f1',(17,)),('sunPosition','f3',(0,1,0)),('upPosition','f3',(0,1,0)),
              ('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),('isEyeInWater','i1',(0,)),
              ('blindness','f1',(0,)),('darknessFactor','f1',(0,)),('rainStrength','f1',(0,)),
              ('blendFunc','i4',(770,771,1,0)),('fogColor','f3',(.2,.3,.4))]
    texture=[[(.125,.25,.375,0 if (x+y)%3==0 else .5) for x in range(width)] for y in range(height)]
    textures=[('gtexture',texture,'RGBA32F'),('lightmap',[[(1,1,1,1)]],'RGBA32F')]
    common=dict(WATER_SCREEN_REFLECTIONS=0,FOG_ENABLED=0,WATER_DEPTH_TINT=0,WATER_TINT_STRENGTH=0.0,WATER_REFLECTION_STRENGTH=1.0)
    comparisons=[];changed=0
    for label,options in (
            ('original',dict(WATER_SURFACE_DETAIL=0)),
            ('disabled',dict(WATER_SURFACE_DETAIL=1,WATER_WAVES=0)),
            ('zero',dict(WATER_SURFACE_DETAIL=1,WATER_WAVE_STRENGTH=0.0)),
            ('detailed',dict(WATER_SURFACE_DETAIL=1))):
        options=dict(common,**options)
        _,fragment=runner.pair('gbuffers_water',options)
        _,old_fragment=runner.pair('gbuffers_water',options,historical('gbuffers_water.fsh'))
        # All listed but optimized-out bindings are justified compile-time disabled paths.
        optional=['fogColor'] # SKY_STYLE1 does not use vanilla fallback.
        if options.get('WATER_WAVES')==0 or options.get('WATER_WAVE_STRENGTH')==0:
            optional+=['cameraPositionInt','cameraPositionFract','frameTimeCounter','gbufferModelViewInverse']
        actual=runner.render('water-fragment-'+label,(vertex,fragment),width,height,textures,uniforms,optional=optional)
        baseline=runner.render('water-fragment-old-'+label,(vertex,old_fragment),width,height,textures,uniforms,optional=optional)
        if label!='detailed':
            comparisons.append(compare(actual,baseline,'water-fragment-'+label+'-exact-W1'))
        for y in range(height):
            for x in range(width):
                require(all(math.isfinite(v) for v in actual[y][x]),'Nonfinite actual water fragment')
                require(actual[y][x][3]==baseline[y][x][3],'Actual fragment alpha/discard changed')
                if (x+y)%3==0: require(actual[y][x]==baseline[y][x],'Actual fragment discard changed')
                if label=='detailed' and actual[y][x]!=baseline[y][x]: changed+=1
    require(changed>0,'Actual detailed fragment produced no visible RGB difference')
    return dict(configurations=4,pixels_per_configuration=width*height,changed_detailed_pixels=changed,
                comparisons=comparisons,scope='Actual pack fragment with synthetic water vertex/material/atlas inputs; original, off and zero exact against W1.')
