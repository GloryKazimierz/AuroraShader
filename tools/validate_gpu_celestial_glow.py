'''M19 actual sky-glow helpers and synthetic sky-stage dispatch on a native driver.'''
import math

from compile_glsl import SHADERS, expand
from validate_atmosphere import rotate
from validate_foliage import f32, IDENTITY4
from validate_celestial_glow import celestial_glow


def quantized(values):
    return tuple(f32(value) for value in values)


def same_channel(actual,expected):
    if math.isnan(expected): return math.isnan(actual)
    return actual==expected


def checked_compare(compare,actual,expected,label):
    # Invalid input RGB must remain invalid, not be silently repaired. Classify
    # nonfinite channels explicitly; finite comparison is still strict elsewhere.
    clean_actual=[];clean_expected=[]
    for arow,erow in zip(actual,expected):
        ar=[];er=[]
        for ap,ep in zip(arow,erow):
            ac=[];ec=[]
            for a,e in zip(ap,ep):
                if not math.isfinite(e):
                    if not same_channel(a,e): raise RuntimeError(label+': changed invalid source channel')
                    a=e=0.0
                ac.append(a);ec.append(e)
            ar.append(tuple(ac));er.append(tuple(ec))
        clean_actual.append(ar);clean_expected.append(er)
    # The lobe derivative at alignment=1 is 65.625. A one-ULP dot rounding
    # below one changes full-strength light by about 3.91e-6; use 1e-5 for
    # active FP32 normalization/lobe arithmetic. Exact bypass checks stay exact.
    return compare(clean_actual,clean_expected,label,absolute=1e-5,relative=1e-7)


def environment_options(case):
    return dict(sun=quantized(case.get('sun',(0,.5,1))),moon=quantized(case.get('moon',(0,.5,-1))),
                up=quantized(case.get('up',(0,1,0))),phase=case.get('phase',0),
                enabled=case.get('enabled',1),sun_strength=case.get('sun_strength',.4),
                moon_strength=case.get('moon_strength',.15),mode=case.get('mode',1),
                debug=case.get('debug',0),sky_style=case.get('sky_style',1),sky_blend=case.get('sky_blend',1.0),
                rain=f32(case.get('rain',0)),skylight=case.get('skylight',True),ceiling=case.get('ceiling',False),
                eye=case.get('eye',0),blindness=f32(case.get('blindness',0)),darkness=f32(case.get('darkness',0)),
                fp32_result=True)


def settings(options):
    return dict(CELESTIAL_GLOW=options['enabled'],SUN_GLOW_STRENGTH=float(options['sun_strength']),
                MOON_GLOW_STRENGTH=float(options['moon_strength']),SCENE_COLOR_MODE=options['mode'],
                DEBUG_VIEW=options['debug'],SKY_STYLE=options['sky_style'],SKY_BLEND=float(options['sky_blend']))


def uniforms(options):
    return [('sunPosition','f3',options['sun']),('moonPosition','f3',options['moon']),
            ('upPosition','f3',options['up']),('moonPhase','i1',(options['phase'],)),
            ('rainStrength','f1',(options['rain'],)),('hasSkylight','i1',(int(options['skylight']),)),
            ('hasCeiling','i1',(int(options['ceiling']),)),('isEyeInWater','i1',(options['eye'],)),
            ('blindness','f1',(options['blindness'],)),('darknessFactor','f1',(options['darkness'],))]


def static_bypass(options):
    return (not options['enabled'] or not options['mode'] or options['debug'] or not options['sky_style']
            or not options['sky_blend'] or not (options['sun_strength'] or options['moon_strength']))


def celestial_glow_tests(runner,compare):
    wrapper='#version 330 compatibility\n'+expand(SHADERS/'lib/celestial_glow.glsl')+'''
uniform sampler2D testRays;
uniform sampler2D testScene;
layout(location=0) out vec4 color;
void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec4 source=texelFetch(testScene,pixel,0);
    color=vec4(applyCelestialGlow(texelFetch(testRays,pixel,0).xyz,source.rgb),source.a);
}
'''
    width,height=7,3
    sun=(0,.5,1);moon=(0,.5,-1)
    rays=[sun,rotate(sun,.05,0),rotate(sun,.2,0),rotate(sun,.6,0),moon,rotate(moon,.2,0),
          (1,.01,0),(1,-.024,0),(1,.04,0),(0,1,0),(0,-1,0),(0,0,0),
          (math.nan,0,1),(math.inf,0,1),(1e30,5e29,1e30),(1e-8,0,0),sun,moon,sun,sun,(0,.25,1)]
    colors=[(.125,.25,.5,(i%7+1)/8) for i in range(21)]
    colors[16]=(-.125,.25,.5,.25); colors[17]=(math.nan,.25,.5,.5)
    colors[18]=(.125,math.inf,.5,.75); colors[19]=(65505,.25,.5,.875)
    colors[20]=(60000,59999,50000,.625)
    def rows(values): return [values[y*width:(y+1)*width] for y in range(height)]
    cases=[dict(label='default'),dict(label='sun-only',moon_strength=0),dict(label='moon-only',sun_strength=0),
           dict(label='maximum',sun_strength=1,moon_strength=.5),dict(label='half-limit',limit=True),
           dict(label='rotated',rotation=(1.2,-.7)),dict(label='scaled-directions',scale=1e30)]
    cases += [dict(label='moon-phase-'+str(phase),phase=phase,sun_strength=0) for phase in range(1,8)]
    cases += [dict(label='bad-phase-'+str(phase),phase=phase) for phase in (-1,8)]
    cases += [dict(label='zero-sun',sun=(0,0,0)),dict(label='invalid-sun',sun=(math.nan,0,1)),
              dict(label='zero-moon',moon=(0,0,0)),dict(label='invalid-moon',moon=(0,math.inf,1)),
              dict(label='zero-up',up=(0,0,0)),dict(label='invalid-up',up=(0,math.nan,0)),
              dict(label='invalid-rain',rain=math.nan),dict(label='invalid-blindness',blindness=math.nan),
              dict(label='invalid-darkness',darkness=math.inf),dict(label='rain-half',rain=.5),
              dict(label='rain-full',rain=1),dict(label='negative-rain',rain=-1),
              dict(label='no-skylight',skylight=False),dict(label='ceiling',ceiling=True),
              dict(label='underwater',eye=1),dict(label='blind',blindness=1),dict(label='dark',darkness=1),
              dict(label='partial-vision',blindness=.25,darkness=.5),dict(label='off',enabled=0),
              dict(label='zero-strengths',sun_strength=0,moon_strength=0),dict(label='legacy',mode=0),
              dict(label='debug',debug=5),dict(label='native-sky',sky_style=0),dict(label='zero-blend',sky_blend=0)]
    comparisons=[];exact=0;invalid=0
    for case in cases:
        opts=environment_options(case); active_rays=list(rays);scene=list(colors)
        if case.get('rotation'):
            yaw,pitch=case['rotation']
            active_rays=[rotate(ray,yaw,pitch) for ray in active_rays]
            for key in ('sun','moon','up'): opts[key]=quantized(rotate(opts[key],yaw,pitch))
        if case.get('scale'):
            for key in ('sun','moon','up'): opts[key]=quantized(tuple(x*case['scale'] for x in opts[key]))
        if case.get('limit'): scene[0]=(65504,65504,65504,.375)
        active_rays=[quantized(ray)+(1,) for ray in active_rays]
        scene=[quantized(pixel) for pixel in scene]
        tex=[('testRays',rows(active_rays),'RGBA32F'),('testScene',rows(scene),'RGBA32F')]
        bound=uniforms(opts)
        optional=[name for name,_,_ in bound]+['testRays'] if static_bypass(opts) else []
        if opts['sun_strength']==0: optional+=['sunPosition']
        if opts['moon_strength']==0: optional+=['moonPosition','moonPhase']
        label='celestial-helper-'+case['label']
        actual=runner.render(label,runner.pair('composite',settings(opts),wrapper),width,height,tex,bound,optional=optional)
        expected=[]
        for i,(ray,pixel) in enumerate(zip(active_rays,scene)):
            source=pixel[:3]
            result=celestial_glow(ray[:3],source,**opts)
            expected.append(tuple(result)+(pixel[3],))
            ap=actual[i//width][i%width]
            if result is source:
                if not all(same_channel(a,e) for a,e in zip(ap,pixel)):
                    raise RuntimeError(label+': exact helper bypass changed')
                exact+=1
            if not all(math.isfinite(c) for c in source): invalid+=1
            if ap[3]!=pixel[3]: raise RuntimeError(label+': alpha changed')
        comparisons.append(checked_compare(compare,actual,rows(expected),label))
    # Execute the actual sky program to test its branch placement. configure()
    # supplies distinct compile placeholders 4/5/6, not verified Iris enum values.
    matrix=[IDENTITY4[r][c] for c in range(4) for r in range(4)]
    stage_cases=[dict(label='sky',stage=4),dict(label='stars',stage=5),dict(label='void',stage=6),
                 dict(label='other',stage=7),dict(label='rain',stage=4,rain=1),
                 dict(label='underwater',stage=4,eye=1),dict(label='blind',stage=4,blindness=1),
                 dict(label='ceiling',stage=4,ceiling=True),dict(label='no-skylight',stage=4,skylight=False),
                 dict(label='native-sky',stage=4,sky_style=0),dict(label='debug',stage=4,debug=5),
                 dict(label='legacy',stage=4,mode=0),dict(label='zero-strengths',stage=4,sun_strength=0,moon_strength=0)]
    stage_comparisons=[];stage_exact=0;changed=0
    for case in stage_cases:
        opts=environment_options(case);config=settings(opts);config['AURORA_ENABLED']=0
        bound=uniforms(opts)+[('renderStage','i1',(case['stage'],)),('viewWidth','f1',(width,)),
               ('viewHeight','f1',(height,)),('gbufferProjectionInverse','m4',matrix),
               ('gbufferModelView','m4',matrix),('fogColor','f3',(.2,.3,.4)),('skyColor','f3',(.3,.5,.7))]
        label='celestial-sky-stage-'+case['label']
        inactive=['moonPosition','moonPhase']
        if not opts['sky_style']:
            inactive += [name for name,_,_ in uniforms(opts)]
        baseline=runner.render(label+'-off',runner.pair('gbuffers_skybasic',dict(config,CELESTIAL_GLOW=0)),
                               width,height,uniforms=bound,optional=inactive)
        active=runner.render(label+'-on',runner.pair('gbuffers_skybasic',config),width,height,uniforms=bound,
                             optional=inactive if static_bypass(opts) else [])
        expected=[]
        for y in range(height):
            row=[]
            for x in range(width):
                pixel=baseline[y][x];ray=(2*(x+.5)/width-1,2*(y+.5)/height-1,1)
                result=celestial_glow(ray,pixel[:3],**opts) if case['stage']==4 else pixel[:3]
                row.append(tuple(result)+(pixel[3],))
                if tuple(result)==pixel[:3]:
                    if active[y][x]!=pixel: raise RuntimeError(label+': unaffected stage changed')
                    stage_exact+=1
                elif active[y][x]!=pixel: changed+=1
                if active[y][x][3]!=pixel[3]: raise RuntimeError(label+': stage alpha changed')
            expected.append(row)
        stage_comparisons.append(checked_compare(compare,active,expected,label))
    if not changed: raise RuntimeError('Sky branch fixtures did not observe any glow')
    return dict(helper_cases=len(cases),helper_samples=len(cases)*width*height,exact_helper_bypasses=exact,
                nonfinite_source_preservations=invalid,comparisons=comparisons,
                sky_stage_cases=len(stage_cases),sky_stage_samples=len(stage_cases)*width*height,
                exact_stage_bypasses=stage_exact,changed_stage_pixels=changed,stage_comparisons=stage_comparisons,
                input='Actual GLSL helper and actual sky pair with synthetic rays/uniforms; branch placeholders are compile-only, no Iris patcher, celestial textures, sky mesh or frame timing')
