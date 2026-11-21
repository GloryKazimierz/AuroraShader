'''W1 real mixed MRT execution and matched water-snapshot reference checks.'''
import math
import re
import subprocess

from compile_glsl import ROOT, SHADERS, expand
from validate_foliage import f32, IDENTITY4
from validate_water_snapshot import encode_snapshot
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix, perspective_matrix

BASELINE='74c7164874e446ebd8e763f146286c2c6908b820'
TARGETS=((1,5,'RGBA16F'),(2,6,'R32F'))


def mrt_controls(runner,compare):
    from validate_gpu import quote, write_text, half
    source='''#version 330 compatibility
layout(location=0) out vec4 primary;
layout(location=1) out vec4 radiance;
layout(location=2) out float depth;
void main() {
    primary=vec4(.125,.25,.5,.75);
    radiance=vec4(1.0+gl_FragCoord.x*.125,2.0+gl_FragCoord.y*.125,.0625,.875);
    depth=.123456791;
}
'''
    pair=runner.pair('composite',wrapper=source)
    expected=[[[((.125,.25,.5,.75) if slot==0 else
                  (1+(x+.5)*.125,2+(y+.5)*.125,.0625,.875) if slot==1 else
                  (f32(.123456791),0,0,1)) for x in range(3)] for y in range(2)] for slot in range(3)]
    comparisons=[]
    for slot in range(3):
        actual=runner.render('mrt-routing-'+str(slot),pair,3,2,extra_targets=TARGETS,read_target=slot)
        comparisons.append(compare(actual,expected[slot],'mrt-routing-'+str(slot)))
    discard=runner.pair('composite',wrapper='#version 330 compatibility\nvoid main(){discard;}\n')
    for slot in (1,2):
        actual=runner.render('mrt-extra-clear-'+str(slot),discard,3,2,extra_targets=TARGETS,read_target=slot)
        sentinel=tuple(half(v) for v in (-11931.25,-719.5,-37.25,-13)) if slot==1 else (-11931.25,0,0,1)
        comparisons.append(compare(actual,[[sentinel]*3 for _ in range(2)],'mrt-extra-clear-'+str(slot)))
    rejections=[('duplicate-slot','color_target 1 5 RGBA16F\ncolor_target 1 6 R32F\n'),
                ('duplicate-attachment','color_target 1 5 RGBA16F\ncolor_target 2 5 R32F\n'),
                ('base-slot','color_target 0 5 RGBA16F\n'),('base-attachment','color_target 1 0 R32F\n'),
                ('range','color_target 8 5 RGBA16F\n'),('missing-read','read_target 2\n'),
                ('duplicate-read','read_target 0\nread_target 0\n'),('read-range','read_target -1\n'),
                ('bad-format','color_target 1 5 BOGUS\n'),
                ('budget','color_target 1 5 RGBA16F\ncolor_target 2 6 R32F\ncolor_target 3 7 R32F\n')]
    for label,body in rejections:
        output=runner.scratch/('mrt-negative-'+label+'.raw')
        manifest=runner.scratch/('mrt-negative-'+label+'.txt')
        size=2048 if label=='budget' else 2
        write_text(manifest,'shaders {} {}\ntarget {} {} RGBA32F {}\n'.format(
            *map(quote,pair),size,size,quote(output))+body)
        runner.call('--render',manifest,expected_failure='manifest')
        if output.exists(): raise RuntimeError('Rejected MRT input wrote an output')
    return dict(comparisons=comparisons,rejected_manifests=len(rejections),
                routing='Simultaneous locations0/1/2 -> physical attachments0/5/6; RGBA32F/RGBA16F/R32F')


def snapshot_tests(runner,compare):
    from validate_gpu import half
    controls=mrt_controls(runner,compare)
    helper='#version 330 compatibility\n'+expand(SHADERS/'lib/water_scene_snapshot.glsl')+'''
uniform sampler2D testRadiance;
uniform sampler2D testDepths;
layout(location=0) out vec4 primary;
layout(location=1) out vec4 snapshot;
layout(location=2) out float snapshotDepth;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec4 source=texelFetch(testRadiance,p,0);
    vec2 depths=texelFetch(testDepths,p,0).rg;
    primary=vec4(0.0);
    encodeWaterSceneSnapshot(source.rgb,source.a,depths.r,depths.g,snapshot,snapshotDepth);
}
'''
    normal=(.125,.25,.5)
    specimens=[((0,0,0),1,.5,.5),(normal,1,.123456791,.123456791),
        (normal,.5,.5,.5),(normal,.4999,.5,.5),(normal,.5001,.5,.5),
        (normal,math.nan,.5,.5),(normal,math.inf,.5,.5),
        ((-.125,.25,.5),1,.5,.5),((math.nan,.25,.5),1,.5,.5),((.125,math.inf,.5),1,.5,.5),
        ((65504,.25,.5),1,.5,.5),((65505,.25,.5),1,.5,.5),
        (normal,1,0,0),(normal,1,.99999994,.99999994),(normal,1,1,1),
        (normal,1,-.1,.5),(normal,1,math.nan,.5),(normal,1,math.inf,.5),
        (normal,1,.5,math.nan),(normal,1,.5,-.1),(normal,1,.5,1.1),(normal,1,.5,math.inf),
        (normal,1,.6,.5),(normal,1,.5,.6),(normal,1,.5,0),(normal,1,.5,1),
        ((.1,.3,2),1,.75,.75),(normal,0,.5,.5)]
    width,height=7,4
    def rows(values,h=height): return [values[y*width:(y+1)*width] for y in range(h)]
    radiance=[tuple(map(f32,rgb))+(f32(valid),) for rgb,valid,_,_ in specimens]
    depths=[(f32(d),f32(h),0,1) for _,_,d,h in specimens]
    comparisons=[];valid=0;invalid=0
    configs=[dict(SCENE_COLOR_MODE=1,DEBUG_VIEW=debug) for debug in range(7)]+[dict(SCENE_COLOR_MODE=0,DEBUG_VIEW=0)]
    for config in configs:
        expected_color=[];expected_depth=[]
        for p,d in zip(radiance,depths):
            color,z=encode_snapshot(p[:3],p[3],d[0],d[1],mode=config['SCENE_COLOR_MODE'],debug=config['DEBUG_VIEW'])
            expected_color.append(tuple(half(c) for c in color));expected_depth.append((z,0,0,1))
            valid+=int(color[3]==1);invalid+=int(color[3]==0)
        optional=['testRadiance','testDepths'] if not config['SCENE_COLOR_MODE'] or config['DEBUG_VIEW'] else []
        pair=runner.pair('composite',config,helper)
        for slot,expected in ((1,expected_color),(2,expected_depth)):
            label='snapshot-helper-{}-{}-{}'.format(config['SCENE_COLOR_MODE'],config['DEBUG_VIEW'],slot)
            actual=runner.render(label,pair,width,height,[('testRadiance',rows(radiance),'RGBA32F'),
                ('testDepths',rows(depths),'RGBA32F')],optional=optional,extra_targets=TARGETS,read_target=slot)
            comparisons.append(compare(actual,rows(expected),label,half_units=1 if slot==1 else 0))
            for ap,ep in zip([p for row in actual for p in row],expected):
                if ap[3]!=ep[3] or (ep[3]==0 and ap!=ep): raise RuntimeError(label+': validity mismatch')
    # Run the ACTUAL deferred pair and the pinned historical fragment with identical
    # inputs. Compare primary output exactly, then independently verify the new pair.
    historical=subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':shaders/deferred.fsh']).decode('utf-8')
    historical=re.sub(r'^#include "([^"]+)"\s*$',lambda match:expand(SHADERS/match[1].lstrip('/')),historical,flags=re.M)
    height=3
    scene=rows([((1+i%4)*.125,(1+i%3)*.25,(1+i%5)*.0625,(1+i%7)/8) for i in range(21)],height)
    surfaces=rows([(.5,1,.5,0 if i==2 else .5 if i==3 else 1) for i in range(21)],height)
    light=rows([(0,1,0,1) for _ in range(21)],height)
    dep1=rows([((1 if i==4 else .25 if i==8 else .9999 if i==14 else .5),0,0,1) for i in range(21)],height)
    dep2=rows([((1 if i==4 else .75 if i==8 else .9999 if i==14 else .5),0,0,1) for i in range(21)],height)
    textures=[('colortex0',scene,'RGBA32F'),('colortex1',surfaces,'RGBA32F'),('colortex2',light,'RGBA32F'),
              ('depthtex1',dep1,'R32F'),('depthtex2',dep2,'R32F')]
    # Upload and reference the same FP32 values, including non-dyadic far depths.
    for _,image,_ in textures:
        for row in image:
            for i,pixel in enumerate(row): row[i]=tuple(map(f32,pixel))
    inverse=tuple(tuple(f32(v) for v in row) for row in inverse_matrix(perspective_matrix(70,width/height,1,192)))
    cases=[dict(label='neutral',fog=0,lighting=0),dict(label='fogged',fog=1,lighting=0),
           dict(label='lit-fogged',fog=1,lighting=1),dict(label='legacy',fog=0,lighting=0,mode=0),
           dict(label='debug',fog=1,lighting=1,debug=5)]
    integrated=[];fog_changed=0;eligible=0
    for case in cases:
        mode=case.get('mode',1);debug=case.get('debug',0);lighting=case['lighting']
        options=dict(SCENE_COLOR_MODE=mode,DEBUG_VIEW=debug,SHADOWS_ENABLED=False,LIGHTING_STRENGTH=float(lighting),
                     LIGHT_PALETTE=lighting,FOG_ENABLED=case['fog'],FOG_START=0.0,FOG_DENSITY=.02)
        def bindings(fog):
            values=[]
            if lighting: values.append(('shadowLightPosition','f3',(0,1,0)))
            if (fog and mode) or lighting:
                values += [('sunPosition','f3',(0,1,0)),('upPosition','f3',(0,1,0)),('rainStrength','f1',(0,)),
                    ('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),('isEyeInWater','i1',(0,)),
                    ('blindness','f1',(0,)),('darknessFactor','f1',(0,))]
            if fog and mode:
                values += [('gbufferProjectionInverse','m4',matrix_uniform(inverse)),('gbufferModelViewInverse','m4',matrix_uniform(IDENTITY4)),
                    ('cameraPositionInt','i3',(0,64,0)),('cameraPositionFract','f3',(0,0,0)),
                    ('eyeBrightnessSmooth','i2',(0,240)),('fogColor','f3',(.2,.3,.4))]
            return values
        optional=['colortex2'] if not lighting else []
        baseline=runner.render('snapshot-old-'+case['label'],runner.pair('deferred',options,historical),width,height,
            textures,bindings(case['fog']),optional=optional+['depthtex2']+(['depthtex1'] if not case['fog'] or not mode else []))
        unfogged=runner.render('snapshot-unfogged-'+case['label'],runner.pair('deferred',dict(options,FOG_ENABLED=0),historical),
            width,height,textures,bindings(0),optional=optional+['depthtex1','depthtex2'])
        pair=runner.pair('deferred',options)
        expected_color=[];expected_depth=[]
        for y in range(height):
            cr=[];dr=[]
            for x in range(width):
                c,z=encode_snapshot(unfogged[y][x][:3],surfaces[y][x][3],dep1[y][x][0],dep2[y][x][0],mode=mode,debug=debug)
                cr.append(tuple(half(v) for v in c));dr.append((z,0,0,1));eligible+=int(c[3]==1)
                if c[3] and baseline[y][x][:3]!=unfogged[y][x][:3]: fog_changed+=1
            expected_color.append(cr);expected_depth.append(dr)
        for slot,expected in ((0,baseline),(1,expected_color),(2,expected_depth)):
            label='snapshot-deferred-{}-{}'.format(case['label'],slot)
            skipped=optional+(['depthtex2'] if not mode or debug else [])
            if (not mode or debug) and not case['fog']: skipped+=['depthtex1']
            actual=runner.render(label,pair,width,height,textures,bindings(case['fog']),optional=skipped,
                                 extra_targets=TARGETS,read_target=slot)
            integrated.append(compare(actual,expected,label,half_units=1 if slot==1 else 0))
            if slot==1 and any(a[3]!=e[3] or (e[3]==0 and a!=e) for ar,er in zip(actual,expected) for a,e in zip(ar,er)):
                raise RuntimeError(label+': snapshot validity mismatch')
    if fog_changed==0: raise RuntimeError('No test distinguished pre-fog radiance from fogged scene')
    return dict(mrt_controls=controls,helper_cases=len(configs),helper_samples=len(configs)*len(specimens),
                helper_valid_samples=valid,helper_invalid_samples=invalid,comparisons=comparisons,
                deferred_cases=len(cases),deferred_pixels=len(cases)*width*height,eligible_deferred_samples=eligible,
                fog_distinguished_samples=fog_changed,deferred_comparisons=integrated,
                input='Actual mixed-format 0/5/6 MRT writes; actual deferred versus pinned M19 output; synthetic inputs, no Iris buffer flipping or world rendering')
