"""Actual M1 geometry/deferred producer readback; synthetic native GL, not Iris."""
import math
import struct
from render_water_bench import WIDTH, HEIGHT, WATER_VERTEX, make_scene
from validate_gpu import compare, half, half_ulp, require, write_text
from validate_water_waves import f32
from validate_foliage import IDENTITY4
from validate_gpu_depth import matrix_uniform

ENABLED = dict(WATER_OPTICS=1, IRIS_FEATURE_PER_BUFFER_BLENDING=True)
WATER_TARGETS = ((1, 7, 'RGBA32F'), (2, 1, 'RGBA8'))
DEFERRED_TARGETS = ((1, 5, 'RGBA16F'), (2, 6, 'R32F'),
                    (3, 7, 'RGBA32F'), (4, 1, 'RGBA8'), (5, 2, 'R16F'))
OPAQUE_TARGETS = ((1, 1, 'RGBA32F'), (2, 2, 'RGBA32F'), (3, 3, 'RGBA8'))


def constant(pixel, width, height):
    return [[tuple(pixel) for _ in range(width)] for _ in range(height)]


def all_pixels(image):
    return (pixel for row in image for pixel in row)


def compare_fp32_one_ulp(actual, expected, label):
    maximum = 0.0
    max_ulps = 0
    for a, e in zip(all_pixels(actual), all_pixels(expected)):
        require(a[3] == e[3], label + ': alpha changed')
        for x, y in zip(a[:3], e[:3]):
            require(math.isfinite(x) and math.isfinite(y), label + ': nonfinite RGB')
            # Valid radiance is nonnegative; identical negative clear sentinels
            # have distance zero. No cross-sign comparison is accepted.
            require((x >= 0) == (y >= 0), label + ': RGB sign changed')
            distance = abs(struct.unpack('<I',struct.pack('<f',x))[0]
                           - struct.unpack('<I',struct.pack('<f',y))[0])
            require(distance <= 1, label + ': RGB exceeds one FP32 ULP')
            maximum = max(maximum, abs(x-y));max_ulps = max(max_ulps,distance)
    return dict(label=label,max_absolute_error=maximum,max_fp32_ulps=max_ulps,alpha_exact=True)


def water_capture_tests(runner):
    scene = make_scene(35.)
    common = {name: (name, kind, value) for name, kind, value in scene['uniforms']}
    varying = '''
uniform int material;
uniform vec3 testNormal;
uniform vec2 testLightmap;
uniform vec4 testColor;
out vec2 lmcoord, texcoord;
out vec4 glcolor;
out vec3 normalView;
flat out int waterSurface;
'''
    setup = '''
    texcoord=gl_MultiTexCoord0.xy;
    lmcoord=testLightmap;
    glcolor=testColor;
    normalView=testNormal;
    waterSurface=material;
'''
    vertex = runner.scratch/'optics-water-plane.vert'
    write_text(vertex, WATER_VERTEX.replace('void main() {', varying+'\nvoid main() {'+setup))
    plane_uniforms = [common[n] for n in ('gbufferProjection','benchNormal','benchEyeHeight')]
    diagnostic = '#version 330 compatibility\nlayout(location=0) out vec4 result;\nvoid main(){result=vec4(gl_FragCoord.z,0,0,1);}\n'
    _, fs = runner.pair('composite', wrapper=diagnostic)
    depth = runner.render('M1 raster depth', (vertex, fs), WIDTH, HEIGHT, uniforms=plane_uniforms)
    atlas = [[(.25,.5,.75,p[0]) for p in row] for row in scene['mask']]
    textures = [('gtexture',atlas,'RGBA32F'),('lightmap',[[(1,1,1,1)]],'RGBA32F'),
                ('colortex5',scene['color'],'RGBA16F'),('colortex6',scene['depth'],'R32F'),
                ('depthtex1',scene['depth'],'R32F')]
    # All cases share one authored perspective plane; only material, normal,
    # environment, coverage or blend eligibility changes. These are fragment
    # producer tests, not Minecraft vertex-input or draw-order simulation.
    cases = [dict(label='top'), dict(label='filtered',waves=1),
             dict(label='cave',levels=(1.,0.)), dict(label='glass',material=0,valid=False),
             dict(label='side',normal=(1.,0.,0.),valid=False),
             dict(label='underside',normal=tuple(-c for c in common['upPosition'][2]),valid=False),
             dict(label='eye-in-water',changes={'isEyeInWater':(1,)},valid=False),
             dict(label='ceiling',changes={'hasCeiling':(1,)},valid=False),
             dict(label='blind',changes={'blindness':(1.,)},valid=False),
             dict(label='unknown-blend',changes={'blendFunc':(1,1,1,1)},valid=False),
             dict(label='zero-coverage',alpha=0.,threshold=0.,valid=False),
             dict(label='disabled-blend',changes={'blendFunc':(0,0,0,0)}),
             dict(label='opaque-blend',changes={'blendFunc':(1,0,1,0)})]
    stats=[]; preserved=[]; wave_changed=0
    captures={}
    for case in cases:
        label=case['label']; levels=case.get('levels',(.25,.75))
        options=dict(ENABLED, FOG_ENABLED=0, WATER_WAVES=case.get('waves',0), WATER_SCREEN_REFLECTIONS=0)
        _, fs=runner.pair('gbuffers_water',options)
        bindings=dict(common)
        bindings.pop('benchWaterSource');bindings.pop('benchAlpha')
        for name,values in case.get('changes',{}).items():
            bindings[name]=(name,bindings[name][1],values)
        bindings.update(material=('material','i1',(case.get('material',1),)),
                        testNormal=('testNormal','f3',case.get('normal',common['upPosition'][2])),
                        testLightmap=('testLightmap','f2',tuple(.5/16+v*15/16 for v in levels)),
                        testColor=('testColor','f4',(1,1,1,case.get('alpha',.55))),
                        alphaTestRef=('alphaTestRef','f1',(case.get('threshold',.1),)))
        # Optimizers remove wave/sky/fog-only inputs in selected cases. Required
        # producer inputs are deliberately not optional so typos fail the test.
        optional=['gbufferModelViewInverse','cameraPositionInt','cameraPositionFract','frameTimeCounter',
                  'sunPosition','eyeBrightnessSmooth','fogColor','colortex5','colortex6','depthtex1']
        records=runner.render('M1 water record '+label,(vertex,fs),WIDTH,HEIGHT,textures,
                              list(bindings.values()),optional=optional,extra_targets=WATER_TARGETS,read_target=1)
        counts=runner.render('M1 water count '+label,(vertex,fs),WIDTH,HEIGHT,textures,
                             list(bindings.values()),optional=optional,extra_targets=WATER_TARGETS,read_target=2)
        covered=discarded=0
        for y,row in enumerate(records):
            for x,record in enumerate(row):
                raster=depth[y][x][3]!=-13
                survives=raster and (scene['mask'][y][x][0] or case.get('threshold',.1)==0)
                count=counts[y][x]
                if not survives:
                    require(record[3]==-13 and count==(0,0,0,0),label+': discarded pixel wrote metadata')
                    discarded+=1;continue
                covered+=1
                if not case.get('valid',True):
                    require(record==(0,0,0,0) and count==(1,0,0,0),label+': ineligible survivor was not a blocker')
                    continue
                require(record[3]==depth[y][x][0],label+': raw depth differs from independent raster diagnostic')
                require(abs(sum(v*v for v in record[:3])-1)<2e-5,label+': captured normal is not unit')
                require(count[0]==f32(1/255) and count[3]==0,label+': one water layer is not byte 1')
                require(all(abs(a-b)<=.5/255+1e-7 for a,b in zip(count[1:3],levels)),label+': light levels differ')
                if not case.get('waves',0):
                    require(max(abs(a-b) for a,b in zip(record[:3],common['upPosition'][2]))<2e-6,
                            label+': waves-off normal differs')
                else:
                    wave_changed+=max(abs(a-b) for a,b in zip(record[:3],common['upPosition'][2]))>1e-4
        require(covered>100 and discarded>100,label+': fixture did not exercise coverage and holes')
        captures[label]=records
        # Compare actual native RGB/alpha with the same program's option-off
        # branch; metadata must not perturb the existing fallback arithmetic.
        if label in ('top','filtered','cave','glass','unknown-blend'):
            native=runner.render('M1 native on '+label,(vertex,fs),WIDTH,HEIGHT,textures,
                                 list(bindings.values()),optional=optional,extra_targets=WATER_TARGETS)
            _, oldfs=runner.pair('gbuffers_water',dict(options,WATER_OPTICS=0))
            off_optional=optional+['alphaTestRef','material','testNormal','testLightmap','upPosition',
                                   'hasSkylight','hasCeiling','isEyeInWater','blindness','darknessFactor','rainStrength',
                                   'blendFunc','viewWidth','viewHeight','gbufferProjectionInverse']
            baseline=runner.render('M1 native off '+label,(vertex,oldfs),WIDTH,HEIGHT,textures,
                                   list(bindings.values()),optional=off_optional)
            if case.get('waves',0):
                # An additional consumer of the wave normal changes Intel's
                # common-subexpression rounding by one FP32 ULP in this fixture.
                # Keep a strict per-value ULP bound and bit-exact native alpha.
                preserved.append(compare_fp32_one_ulp(native,baseline,'native water '+label))
                half_native=runner.render('M1 native half on',(vertex,fs),WIDTH,HEIGHT,textures,
                                          list(bindings.values()),storage='RGBA16F',optional=optional,
                                          extra_targets=WATER_TARGETS)
                half_baseline=runner.render('M1 native half off',(vertex,oldfs),WIDTH,HEIGHT,textures,
                                            list(bindings.values()),storage='RGBA16F',optional=off_optional)
                preserved.append(compare(half_native,half_baseline,'native water RGBA16F '+label))
            else:
                preserved.append(compare(native,baseline,'native water '+label))
        stats.append(dict(label=label,covered=covered,discarded=discarded))
    require(wave_changed>scene['water_pixels']//2,'filtered normal perturbation was not observed')
    return dict(cases=stats,filtered_perturbed_pixels=wave_changed,native_color_comparisons=preserved,
                resolution=[WIDTH,HEIGHT],normal_depth_format='RGBA32F',count_format='RGBA8')


GEOMETRY_VERTEX = '''#version 330 compatibility
uniform vec2 testLightmap;
uniform vec3 testNormal;
uniform vec4 testColor;
out vec2 lmcoord,texcoord;
out vec4 glcolor;
out vec3 normalView;
void main(){gl_Position=gl_Vertex;texcoord=gl_MultiTexCoord0.xy;
 lmcoord=testLightmap;normalView=testNormal;glcolor=testColor;}
'''


def geometry_ownership_tests(runner):
    width,height=3,2
    vertex=runner.scratch/'optics-geometry.vert';write_text(vertex,GEOMETRY_VERTEX)
    options=dict(ENABLED,FOG_ENABLED=0,CLOUD_STYLE=0,CLOUD_FOG=0,SKY_STYLE=0,AURORA_ENABLED=0)
    base_uniforms=[('testLightmap','f2',(.5,.5)),('testNormal','f3',(0,1,0)),
                   ('testColor','f4',(.3,.5,.7,.8)),('entityColor','f4',(0,0,0,0)),
                   ('viewWidth','f1',(width,)),('viewHeight','f1',(height,)),
                   ('gbufferProjectionInverse','m4',matrix_uniform(IDENTITY4)),
                   ('gbufferModelView','m4',matrix_uniform(IDENTITY4)),
                   ('fogColor','f3',(.2,.3,.4)),('skyColor','f3',(.4,.5,.7))]
    base_textures=[('gtexture',[[(1,1,1,1)]],'RGBA32F'),('lightmap',[[(1,1,1,1)]],'RGBA32F')]
    cases=[];preserved=[]
    for program in ('gbuffers_terrain','gbuffers_block','gbuffers_entities'):
        for label,alpha,blend,expected in [('early',0,(0,0,0,0),0),('overwrite',0,(1,0,1,0),0),
                                         ('late',1,(1,0,1,0),1),('unsupported',0,(770,771,1,771),1)]:
            pair=runner.pair(program,options)
            uniforms=base_uniforms+[('blendFunc','i4',blend)]
            textures=base_textures+[('colortex5',constant((.1,.2,.3,alpha),width,height),'RGBA16F')]
            optional=[n for n,_,_ in base_uniforms]+['gtexture','lightmap']
            actual=runner.render(program+' '+label,(vertex,pair[1]),width,height,textures,uniforms,
                                 optional=optional,extra_targets=OPAQUE_TARGETS,read_target=3)
            compare(actual,constant((expected,0,0,0),width,height),program+' ownership '+label)
            cases.append(program+':'+label)
            if label=='early':
                native=runner.render(program+' native on',(vertex,pair[1]),width,height,textures,uniforms,
                                     optional=optional,extra_targets=OPAQUE_TARGETS)
                _,oldfs=runner.pair(program,dict(options,WATER_OPTICS=0))
                baseline=runner.render(program+' native off',(vertex,oldfs),width,height,textures,uniforms,
                                       optional=optional+['colortex5','blendFunc'],extra_targets=OPAQUE_TARGETS[:2])
                preserved.append(compare(native,baseline,program+' native color'))
    blockers=('gbuffers_armor_glint','gbuffers_basic','gbuffers_beaconbeam','gbuffers_clouds',
              'gbuffers_hand','gbuffers_hand_water','gbuffers_skybasic','gbuffers_skytextured',
              'gbuffers_spidereyes','gbuffers_textured','gbuffers_textured_lit','gbuffers_weather')
    for program in blockers:
        for stage in ((4,5,6) if program=='gbuffers_skybasic' else (4,)):
            # Sky style remains active for the void early-return coverage.
            config=dict(options,SKY_STYLE=1) if program=='gbuffers_skybasic' else options
            _,fs=runner.pair(program,config)
            uniforms=base_uniforms+[('renderStage','i1',(stage,)),('sunPosition','f3',(0,1,0)),
                       ('upPosition','f3',(0,1,0)),('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),
                       ('isEyeInWater','i1',(0,)),('blindness','f1',(0,)),('darknessFactor','f1',(0,)),
                       ('rainStrength','f1',(0,))]
            optional=[n for n,_,_ in uniforms]+['gtexture','lightmap']
            actual=runner.render(program+' blocker '+str(stage),(vertex,fs),width,height,base_textures,uniforms,
                                 optional=optional,extra_targets=((1,1,'RGBA8'),),read_target=1)
            compare(actual,constant((1,0,0,0),width,height),program+' blocker')
            cases.append(program+':'+str(stage))
    return dict(cases=cases,native_color_exact=preserved,
                scope='Actual fragment outputs; blend ordering separately exercised by indexed-blend protocol tests')


def deferred_capture_tests(runner):
    width,height=9,2
    # Independent scene categories include zero sky/block-protected caves,
    # back-facing light, hand mismatch, invalid surface, early contamination.
    samples=[]
    for levels,normal,valid,z,hand,flag in [
        ((0,1),(0,1,0),1,.5,.5,0),((0,0),(0,1,0),1,.5,.5,0),
        ((1,1),(0,1,0),1,.5,.5,0),((.25,.75),(0,1,0),1,.5,.5,0),
        ((0,1),(0,-1,0),1,.5,.5,0),((0,1),(1,0,0),1,.5,.5,0),
        ((0,1),(0,1,0),1,.5,.5,1/255),((0,1),(0,1,0),1,.5,.5,1),
        ((0,1),(0,1,0),1,.5,.4,0),((0,1),(0,1,0),0,.5,.5,0),
        ((0,1),(0,1,0),.5,.5,.5,0),((0,1),(0,1,0),1,1,1,0),
        ((0,1),(0,1,0),1,.5,.5,0),((.5,.5),(0,1,0),1,.5,.5,0),
        ((0,1),(0,1,0),1,0,0,0),((0,1),(0,1,0),1,.5,.5,0),
        ((0,1),(0,1,0),1,.5,.5,0),((0,1),(0,1,0),1,.5,.5,0)]:
        samples.append(dict(levels=levels,normal=normal,valid=valid,z=z,hand=hand,flag=flag))
    def rows(values):return [values[y*width:(y+1)*width] for y in range(height)]
    scene=[(.125,.25,.5,.625)]*len(samples)
    scene[12]=(-.25,.25,.5,.625);scene[15]=(0,0,0,.625);scene[16]=(1,2,3,.625)
    scene[17]=(65504,65504,65504,.625)
    surfaces=[tuple(.5+.5*c for c in s['normal'])+(s['valid'],) for s in samples]
    textures=[('colortex0',rows(scene),'RGBA32F'),('colortex1',rows(surfaces),'RGBA32F'),
              ('colortex2',rows([s['levels']+(0,1) for s in samples]),'RGBA32F'),
              ('depthtex1',rows([(s['z'],0,0,1) for s in samples]),'R32F'),
              ('depthtex2',rows([(s['hand'],0,0,1) for s in samples]),'R32F'),
              ('colortex8',rows([(s['flag'],0,0,0) for s in samples]),'RGBA8')]
    # The shadow fixture projects every valid receiver to shadow depth .5,
    # independently of camera near/far depth, against a constant zero caster.
    identity=matrix_uniform(IDENTITY4)
    uniforms=[('shadowLightPosition','f3',(0,1,0)),('gbufferProjectionInverse','m4',identity),
              ('gbufferModelViewInverse','m4',identity),('shadowModelView','m4',identity),
              ('shadowProjection','m4',matrix_uniform(((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,0.,0.),(0.,0.,0.,1.))))]
    optional=[n for n,_,_ in uniforms]+['colortex2','shadowtex1']
    cases=[dict(label='lit',strength=1.,direct=.55,shadow=False),
           dict(label='strength-zero',strength=0.,direct=.55,shadow=False),
           dict(label='direct-zero',strength=1.,direct=0.,shadow=False),
           dict(label='fully-shadowed',strength=1.,direct=.55,shadow=True)]
    results=[];preserved=[];valid_count=0
    for case in cases:
        options=dict(ENABLED,FOG_ENABLED=0,LIGHT_PALETTE=0,SHADOWS_ENABLED=case['shadow'],
                     SHADOW_FILTER=0,SHADOW_BIAS_MODE=0,LIGHTING_STRENGTH=case['strength'],DIRECT_LIGHT=case['direct'])
        pair=runner.pair('deferred',options)
        inputs=textures+[('shadowtex1',[[(0,0,0,1)]],'R32F')]
        actual=runner.render('M1 deferred q '+case['label'],pair,width,height,inputs,uniforms,
                             optional=optional,extra_targets=DEFERRED_TARGETS,read_target=5)
        full_targets=DEFERRED_TARGETS[:-1]+((5,2,'R32F'),)
        full=runner.render('M1 deferred q full precision '+case['label'],pair,width,height,inputs,uniforms,
                           optional=optional,extra_targets=full_targets,read_target=5)
        # Read the real W1 validity, then independently check the directional
        # energy split. Invalid W1/early ownership may never yield a valid share.
        snapshot=runner.render('M1 deferred snapshot '+case['label'],pair,width,height,inputs,uniforms,
                               optional=optional,extra_targets=DEFERRED_TARGETS,read_target=1)
        maximum=full_maximum=0.
        for i,(pixel,raw,snap,sample) in enumerate(zip(all_pixels(actual),all_pixels(full),all_pixels(snapshot),samples)):
            is_valid=snap[3]==1 and sample['flag']==0
            if not is_valid:
                require(pixel==raw==(-1,0,0,1),'invalid background acquired directional fraction');continue
            sky_weight=sample['levels'][1]*(1-sample['levels'][0])
            w=case['strength']*sky_weight
            ambient=(1-w)+w*.65
            visibility=0. if case['shadow'] else 1.
            directional=w*case['direct']*max(sample['normal'][1],0)*visibility
            expected=directional/(ambient+directional)
            # Check formula accuracy BEFORE half storage. The Intel driver
            # truncates some R16F outputs instead of rounding to nearest, proven
            # by the same output rerouted to R32F and a uniform-only diagnostic.
            full_error=abs(raw[0]-expected);full_maximum=max(full_maximum,full_error)
            require(full_error<=2e-7,case['label']+': full precision ratio differs')
            error=abs(pixel[0]-expected);maximum=max(maximum,error)
            require(error<=half_ulp(expected)+3e-7,
                    case['label']+' q differs at '+str(i)+': '+str((pixel,expected)))
            require(pixel[1:]==(0,0,1) and 0<=pixel[0]<=1,'R16F readback/layout differs')
            valid_count+=1
        for slot in (3,4):
            reset=runner.render('M1 deferred reset '+str(slot),pair,width,height,inputs,uniforms,
                                optional=optional,extra_targets=DEFERRED_TARGETS,read_target=slot)
            compare(reset,constant((0,0,0,0),width,height),'deferred explicit reset '+str(slot))
        _,oldfs=runner.pair('deferred',dict(options,WATER_OPTICS=0))
        for slot in (0,1,2):
            active=runner.render('M1 deferred preserved on '+str(slot),pair,width,height,inputs,uniforms,
                                 optional=optional,extra_targets=DEFERRED_TARGETS,read_target=slot)
            baseline=runner.render('M1 deferred preserved off '+str(slot),(pair[0],oldfs),width,height,inputs,uniforms,
                                   optional=optional+['colortex8'],extra_targets=DEFERRED_TARGETS[:2],read_target=slot)
            preserved.append(compare(active,baseline,'deferred '+case['label']+' slot '+str(slot)))
        results.append(dict(label=case['label'],max_fraction_error=maximum,
                            max_full_precision_error=full_maximum,
                            conversion_probe=dict(index=13,r32f=full[1][4][0],r16f=actual[1][4][0],
                                                  nearest_half_reference=half(full[1][4][0]))))
    return dict(cases=results,samples=len(samples)*len(cases),valid_shares=valid_count,
                native_snapshot_exact=preserved,half_storage_error_bound='one binary16 ULP plus 3e-7 arithmetic slack; no assumed nearest-even mode',formats=['RGBA32F','RGBA16F','R32F','RGBA32F','RGBA8','R16F'],
                scope='Actual six-target deferred output. Independent scalar energy ratio and native option-off equality.')


def capture_tests(runner):
    return dict(water=water_capture_tests(runner),geometry=geometry_ownership_tests(runner),
                deferred=deferred_capture_tests(runner),
                scope='Actual production fragments with synthetic inputs. Native driver MRT readback, not Iris bindings/order or Minecraft runtime.')
