"""Finite-exit M3B: independent angle-space optics and native source tests."""
import json,math,tempfile
from pathlib import Path

def scattering_tests(runner):
    from compile_glsl import SHADERS,expand
    from validate_gpu import compare,require
    from validate_water_waves import f32
    cases=[]
    critical=math.degrees(math.asin(1/1.333))
    for ni,nt in ((1.,1.333),(1.333,1.),(1.333,1.333)):
        for degree in (0.,15.,30.,45.,critical-.01,critical+.01,60.,89.):
            for azimuth in (0.,73.,180.):
                a=math.radians(degree);phi=math.radians(azimuth)
                direction=tuple(map(f32,(math.sin(a)*math.cos(phi),math.sin(a)*math.sin(phi),-math.cos(a))))
                cases.append((direction+(f32(ni),),(0.,0.,1.,f32(nt))))
    invalid=[((0,0,0,1.333),(0,0,1,1)),((0,0,1,1.333),(0,0,1,1)),
             ((0,0,-1,.8),(0,0,1,1)),((0,0,-1,1.333),(0,0,0,1)),
             ((float('nan'),0,-1,1.333),(0,0,1,1)),((0,0,-1,1.333),(0,0,1,float('inf')))]
    source="#version 330 compatibility\n"+expand(SHADERS/'lib/water_interface_scatter.glsl')+"""
uniform sampler2D query,normalIndex;uniform int outputKind;layout(location=0)out vec4 color;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec4 a=texelFetch(query,p,0),b=texelFetch(normalIndex,p,0);
WaterInterfaceScatter s=scatterWaterInterface(a.xyz,b.xyz,a.w,b.w);
if(outputKind==0)color=vec4(s.transmitted,s.valid?1:0);
else if(outputKind==1)color=vec4(s.reflected,s.totalInternalReflection?1:0);
else color=vec4(s.fresnel,s.radianceScale,s.valid?1:0,s.totalInternalReflection?1:0);}
"""
    expected=[[],[],[]]
    for a,b in cases:
        length=math.sqrt(sum(x*x for x in a[:3]));d=[x/length for x in a[:3]]
        incident_angle=math.acos(min(1.,max(0.,-d[2])));phi=math.atan2(d[1],d[0])
        ni,nt=a[3],b[3];critical_angle=math.asin(nt/ni) if ni>nt else math.pi/2
        tir=incident_angle>=critical_angle and ni>nt
        reflected=(d[0],d[1],-d[2]);transmitted=(0.,0.,0.)
        fresnel=1.
        if not tir:
            theta=math.asin(min(1.,ni/nt*math.sin(incident_angle)))
            transmitted=(math.sin(theta)*math.cos(phi),math.sin(theta)*math.sin(phi),-math.cos(theta))
            ci,ct=math.cos(incident_angle),math.cos(theta)
            rs=(ni*ci-nt*ct)/(ni*ci+nt*ct);rp=(nt*ci-ni*ct)/(nt*ci+ni*ct)
            fresnel=(rs*rs+rp*rp)/2
            require(abs(ni*math.sin(incident_angle)-nt*math.sin(theta))<1e-12,'Snell invariant')
        expected[0].append(transmitted+(1.,));expected[1].append(reflected+(float(tir),))
        expected[2].append((fresnel,(ni/nt)**2,1.,float(tir)))
    for _ in invalid:
        expected[0].append((0,0,0,0));expected[1].append((0,0,0,0));expected[2].append((1,1,0,0))
    allcases=cases+invalid
    pair=runner.pair('composite',wrapper=source);results=[]
    for kind in range(3):
        image=runner.render('M3B interface',pair,len(allcases),1,
            [('query',[[a for a,b in allcases]],'RGBA32F'),('normalIndex',[[b for a,b in allcases]],'RGBA32F')],
            [('outputKind','i1',[kind])])
        if kind != 2:
            results.append(compare(image,[expected[kind]],'Independent angle-space interface '+str(kind),absolute=1e-5,relative=1e-6))
        else:
            # Fresnel's condition number diverges at the critical angle. Bound only
            # that scalar by an independent interval for eight FP32 unit roundoffs
            # in the normalized cosine; directions, TIR and index scale stay strict.
            maximum=0.;maximum_bound=0.
            for i,(actual,wanted) in enumerate(zip(image[0],expected[kind])):
                bound=2e-6
                if i<len(cases):
                    a,b=cases[i];length=math.sqrt(sum(v*v for v in a[:3]));ci=-a[2]/length
                    def reflectance(c):
                        c=min(1.,max(0.,c));theta=math.acos(c);s=a[3]/b[3]*math.sin(theta)
                        if s>=1:return 1.
                        ct=math.cos(math.asin(s));rs=(a[3]*c-b[3]*ct)/(a[3]*c+b[3]*ct)
                        rp=(b[3]*c-a[3]*ct)/(b[3]*c+a[3]*ct);return (rs*rs+rp*rp)/2
                    bound+=max(abs(reflectance(ci+sign*8*2**-24)-wanted[0]) for sign in (-1,1))
                error=abs(actual[0]-wanted[0]);require(error<=bound,'Fresnel exceeded FP32 cosine condition bound')
                require(abs(actual[1]-wanted[1])<1e-6 and actual[2:]==wanted[2:],'Index scale/TIR/valid mismatch')
                maximum=max(maximum,error);maximum_bound=max(maximum_bound,bound)
            results.append(dict(label='Critical-angle conditioned Fresnel',max_absolute_error=maximum,
                maximum_bound=maximum_bound,normalized_cosine_uncertainty=8*2**-24))
        if kind==0:
            for i,e in enumerate(expected[2]):
                if e[3]:require(image[0][i][:3]==(0,0,0),'TIR fabricated a transmitted direction')
    return dict(valid_cases=len(cases),invalid_cases=len(invalid),critical_degrees=critical,comparisons=results,
        reference='Angle-space Snell invariant, independent exact polarization Fresnel and radiance index ratio')

def finite_pool_scene(width=96,height=64,pitch=-20.,eye_height=-1.,dark=False):
    from validate_gpu import half
    from validate_water_waves import f32
    from validate_water_depth import perspective_matrix,inverse_matrix
    from validate_gpu_depth import matrix_uniform
    from render_water_bench import box_hit
    angle=math.radians(pitch);c,s=math.cos(angle),math.sin(angle)
    rotation=((1,0,0),(0,c,-s),(0,s,c));inverse_rotation=tuple(zip(*rotation))
    def mv(m,v):return tuple(sum(a*b for a,b in zip(row,v)) for row in m)
    projection=tuple(tuple(map(f32,row)) for row in perspective_matrix(90.,width/height,.05,128.))
    inverse=tuple(tuple(map(f32,row)) for row in inverse_matrix(projection))
    model=tuple(tuple(inverse_rotation[r][k] if r<3 and k<3 else float(r==k==3) for k in range(4)) for r in range(4))
    up=tuple(map(f32,mv(rotation,(0,1,0))));eye=(0.,eye_height,4.)
    textures={key:[] for key in ('colortex0','colortex5','colortex6','colortex7','colortex8','colortex9','depthtex0','depthtex1')}
    surfaces=[];rays=[];classes=[]
    def z_of(view):
        clip=mv(projection,view+(1.,));return f32(.5+.5*clip[2]/clip[3])
    for y in range(height):
        row={k:[] for k in textures};surface_row=[];ray_row=[];class_row=[]
        for x in range(width):
            ray=((2*(x+.5)/width-1)/projection[0][0],(2*(y+.5)/height-1)/projection[1][1],-1.)
            mag=math.sqrt(sum(v*v for v in ray));ray=tuple(v/mag for v in ray);world=mv(inverse_rotation,ray)
            hits=[]
            for plane,color,label in ((-3.,(.16,.26,.11),'floor'),(4.,(.65,.22,.08),'ceiling')):
                if abs(world[1])>1e-9:
                    t=(plane-eye[1])/world[1]
                    if t>0:hits.append((t,color,label))
            # Finite opaque end/side walls bound the authored test room.
            for axis,coordinate in ((0,-9.),(0,9.),(2,-14.)):
                if abs(world[axis])>1e-9:
                    t=(coordinate-eye[axis])/world[axis]
                    if t>0:hits.append((t,(.12,.18,.25),'wall'))
            distance,rgb,label=min(hits);back=tuple(v*distance for v in ray);back_z=z_of(back)
            rgb=tuple(half(v) for v in rgb) if not dark else (0.,0.,0.)
            front=None;front_z=back_z
            if world[1]>1e-9:
                travel=-eye[1]/world[1];point=tuple(eye[i]+world[i]*travel for i in range(3))
                if travel>.05 and travel<distance and -6<=point[0]<=6 and -10<=point[2]<=5:
                    front=tuple(v*travel for v in ray);front_z=z_of(front)
                    if not 0<=front_z<1:front=None;front_z=back_z
            native=tuple(f32(v) for v in ((0.,0.,0.) if dark else ((.04,.13,.17) if front else rgb)))+(f32(.375+(x+y)%3*.125),)
            row['colortex0'].append(native);row['colortex5'].append(rgb+(1.,));row['colortex6'].append((back_z,0,0,1))
            row['colortex7'].append(up+(front_z,) if front else (0,0,0,0))
            row['colortex8'].append((f32(1/255),0,1,f32(1/255)) if front else (0,0,0,0))
            row['colortex9'].append((0,0,0,1));row['depthtex0'].append((front_z,0,0,1));row['depthtex1'].append((back_z,0,0,1))
            surface_row.append(front);ray_row.append(ray);class_row.append(label)
        for k in textures:textures[k].append(row[k])
        surfaces.append(surface_row);rays.append(ray_row);classes.append(class_row)
    uniforms=[('gbufferProjection','m4',matrix_uniform(projection)),('gbufferProjectionInverse','m4',matrix_uniform(inverse)),
        ('gbufferModelViewInverse','m4',matrix_uniform(model)),('upPosition','f3',up),('shadowLightPosition','f3',up),
        ('sunPosition','f3',up),('fogColor','f3',(.04,.15,.2)),('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),
        ('isEyeInWater','i1',(1,)),('blindness','f1',(0.,)),('darknessFactor','f1',(0.,)),('rainStrength','f1',(0.,)),
        ('eyeBrightnessSmooth','i2',(240,240)),('cameraPositionInt','i3',(0,63,4)),('cameraPositionFract','f3',(0.,0.,0.))]
    return dict(width=width,height=height,textures=textures,uniforms=uniforms,front=surfaces,rays=rays,classes=classes,up=up)

def composite_tests(runner,plate_path=None):
    import copy
    from validate_gpu import require,compare
    from validate_gpu_water_transport import render_resolve
    from render_water_bench import png,display_rows,draw_text
    from compile_glsl import ROOT
    options=dict(WATER_UNDERWATER=1,WATER_SCREEN_REFLECTIONS=1,WATER_REFLECTION_STRENGTH=1.0,
                 WATER_TRACE_TILES=0,WATER_REFLECTION_STEPS=128,WATER_REFRACTION=0,WATER_FOAM=0)
    scene=finite_pool_scene();off=render_resolve(runner,scene,dict(options,WATER_UNDERWATER=0));on=render_resolve(runner,scene,options)
    changed=tir_changed=transmitted_changed=0
    for y in range(scene['height']):
        for x in range(scene['width']):
            a,b=off[y][x],on[y][x];require(a[3]==b[3],'M3B changed native alpha')
            differs=max(abs(u-v) for u,v in zip(a[:3],b[:3]))>1e-6
            if scene['front'][y][x] is None:require(a==b,'M3B changed pixel without finite exit')
            if differs:
                changed+=1;cosine=sum(v*u for v,u in zip(scene['rays'][y][x],scene['up']))
                if 1.333**2*(1-cosine*cosine)>=1:tir_changed+=1
                else:transmitted_changed+=1
    require(changed>100 and tir_changed>10 and transmitted_changed>10,'No meaningful actual finite-exit optical response')
    controls=[]
    for label in ('missing-exit','double-water','overlay','wrong-front','invalid-normal','above-water','lava','blindness','ceiling','no-screen-rays'):
        data=copy.deepcopy(scene);cfg=dict(options)
        if label in ('above-water','lava','blindness','ceiling'):
            key,value={'above-water':('isEyeInWater',0),'lava':('isEyeInWater',2),'blindness':('blindness',1.),'ceiling':('hasCeiling',1)}[label]
            data['uniforms']=[(n,k,(value,) if n==key else v) for n,k,v in data['uniforms']]
        elif label=='no-screen-rays':cfg['WATER_SCREEN_REFLECTIONS']=0
        else:
            for y in range(data['height']):
                for x in range(data['width']):
                    if data['front'][y][x] is None:continue
                    if label=='missing-exit':data['textures']['colortex8'][y][x]=(0,0,0,0)
                    elif label=='double-water':data['textures']['colortex8'][y][x]=(2/255,0,1,2/255)
                    elif label=='overlay':data['textures']['colortex8'][y][x]=(1,0,1,1/255)
                    elif label=='wrong-front':data['textures']['depthtex0'][y][x]=(.25,0,0,1)
                    elif label=='invalid-normal':data['textures']['colortex7'][y][x]=(0,0,0,data['textures']['colortex7'][y][x][3])
        enabled=render_resolve(runner,data,cfg);baseline=render_resolve(runner,data,dict(cfg,WATER_UNDERWATER=0))
        controls.append(compare(enabled,baseline,'M3B fallback '+label))
    dark=finite_pool_scene(dark=True);dark_on=render_resolve(runner,dark,options)
    require(all(pixel[:3]==(0.,0.,0.) for row in dark_on for pixel in row),'Black cave acquired luminous energy')
    strength_checks=[]
    for strength in (.35,.2,.75,0.):
        image=render_resolve(runner,scene,dict(options,WATER_REFLECTION_STRENGTH=strength))
        checked=0
        for y in range(scene['height']):
            for x in range(scene['width']):
                if scene['front'][y][x] is None:continue
                cosine=sum(v*u for v,u in zip(scene['rays'][y][x],scene['up']))
                if 1.333**2*(1-cosine*cosine)<=1.00001:continue
                expected=off[y][x] if strength==0. else on[y][x]
                require(image[y][x]==expected,'TIR must be full F=1 at nonzero strength, native at zero')
                checked+=1
        require(checked>100,'TIR strength fixture has insufficient admitted rays')
        strength_checks.append(dict(strength=strength,exact_tir_pixels=checked))
    # A genuine above-water M1/M3A record must remain byte-identical with M3B on.
    from validate_gpu_water_transport import slab_scene
    above=slab_scene();above_options=dict(options,WATER_REFRACTION=1)
    compare(render_resolve(runner,above,above_options),render_resolve(runner,above,dict(above_options,WATER_UNDERWATER=0)),
            'Genuine above-water transport preserved')
    # Display is a generated test-room image, not a Minecraft screenshot.
    a,b=display_rows(off),display_rows(on);w,h=scene['width'],scene['height']
    plate=[[(20,24,31)]*(w*2) for _ in range(h+20)]
    for y in range(h):plate[y+20]=a[y]+b[y]
    draw_text(plate,3,5,'NATIVE');draw_text(plate,w+3,5,'FINITE EXIT')
    if plate_path is not None:png(plate_path,plate)
    return dict(changed_pixels=changed,tir_pixels=tir_changed,transmission_pixels=transmitted_changed,
                controls=controls,alpha_exact=True,no_exit_exact=True,tir_strength_checks=strength_checks)

def producer_tests(runner):
    from validate_gpu import write_text,require,compare
    from render_water_bench import WATER_VERTEX
    from validate_gpu_water_capture import WATER_TARGETS
    from validate_water_waves import f32
    data=finite_pool_scene(64,48);width,height=data['width'],data['height']
    varying='uniform int material;uniform float testHeight;out float waterInterfaceHeight;uniform vec3 testNormal;out vec2 lmcoord,texcoord;out vec4 glcolor;out vec3 normalView;flat out int waterSurface;'
    setup='waterInterfaceHeight=testHeight;texcoord=gl_MultiTexCoord0.xy;lmcoord=vec2(.5);glcolor=vec4(1);normalView=testNormal;waterSurface=material;'
    vertex=runner.scratch/'underwater-producer.vert'
    write_text(vertex,WATER_VERTEX.replace('void main() {',varying+'\nvoid main(){'+setup))
    common={n:(n,k,v) for n,k,v in data['uniforms']};common.update(
        material=('material','i1',(1,)),testHeight=('testHeight','f1',(.875,)),testNormal=('testNormal','f3',tuple(-v for v in data['up'])),
        viewWidth=('viewWidth','f1',(width,)),viewHeight=('viewHeight','f1',(height,)),
        frameTimeCounter=('frameTimeCounter','f1',(17.,)),blendFunc=('blendFunc','i4',(770,771,1,771)),
        benchEyeHeight=('benchEyeHeight','f1',(-1.,)),benchNormal=('benchNormal','f3',data['up']))
    textures=[('gtexture',[[ (.25,.5,.75,.5) ]],'RGBA32F'),('lightmap',[[ (1,1,1,1) ]],'RGBA32F')]
    diagnostic='#version 330 compatibility\nlayout(location=0)out vec4 color;void main(){color=vec4(gl_FragCoord.z,0,0,1);}'
    _,fs=runner.pair('composite',wrapper=diagnostic)
    depth=runner.render('Actual exit raster depth',(vertex,fs),width,height,uniforms=[common[n] for n in ('gbufferProjection','benchEyeHeight','benchNormal')])
    cases=[('exit-reversed',{},True),('exit-up',{'testNormal':data['up']},True),('real-bottom',{'testHeight':(.015625,)},False),('glass',{'material':(0,)},False),('side',{'testNormal':(1.,0.,0.)},False),
        ('above',{'isEyeInWater':(0,)},False),('lava',{'isEyeInWater':(2,)},False),
        ('blind',{'blindness':(1.,)},False),('unknown-blend',{'blendFunc':(1,1,1,1)},False)]
    results=[]
    for label,changes,valid in cases:
        bindings={n:(n,k,changes.get(n,v)) for n,k,v in common.values()}
        options=dict(WATER_OPTICS=1,WATER_UNDERWATER=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,
                     WATER_WAVES=0,WATER_SCREEN_REFLECTIONS=0,FOG_ENABLED=0)
        _,fs=runner.pair('gbuffers_water',options)
        optional=list(bindings)
        record=runner.render('Actual exit producer '+label,(vertex,fs),width,height,textures,list(bindings.values()),
                             optional=optional,extra_targets=WATER_TARGETS,read_target=1)
        count=runner.render('Actual exit ownership '+label,(vertex,fs),width,height,textures,list(bindings.values()),
                             optional=optional,extra_targets=WATER_TARGETS,read_target=2)
        covered=0
        for y in range(height):
            for x in range(width):
                if depth[y][x][3]==-13:continue
                covered+=1
                # The actual raster contains a near-horizon band intentionally
                # excluded by the .03 camera-side guard; derive it geometrically.
                eligible=valid and sum(v*u for v,u in zip(data['rays'][y][x],data['up']))>.03
                if eligible:
                    require(record[y][x][3]==depth[y][x][0],'Exit producer changed raw depth')
                    require(max(abs(a-b) for a,b in zip(record[y][x][:3],data['up']))<2e-6,'Exit producer changed base normal')
                    require(count[y][x][0]==f32(1/255) and count[y][x][3]==f32(1/255),'Exit counter/marker not byte1')
                else:
                    require(record[y][x]==(0,0,0,0) and count[y][x]==(1,0,0,0),'Invalid exit not an opaque ownership blocker')
        require(covered>100,'Producer fixture has no rasterized exit')
        # Native scene color must not depend on writing extra exit metadata.
        on=runner.render('Exit producer color',(vertex,fs),width,height,textures,list(bindings.values()),optional=optional,extra_targets=WATER_TARGETS)
        _,fs0=runner.pair('gbuffers_water',dict(options,WATER_UNDERWATER=0))
        off=runner.render('Exit producer baseline',(vertex,fs0),width,height,textures,list(bindings.values()),optional=optional,extra_targets=WATER_TARGETS)
        results.append(dict(case=label,covered=covered,color=compare(on,off,'Exit metadata color0 '+label)))
    return dict(cases=results)

def boundary_tests(runner):
    from validate_gpu import require
    from validate_gpu_water_transport import render_resolve
    records=[]
    for eye_height in (-.2,-.05,-.01,-.001,0.,.001,.05,.2):
        data=finite_pool_scene(64,48,pitch=-5.,eye_height=eye_height)
        if eye_height>=0:data['uniforms']=[(n,k,(0,) if n=='isEyeInWater' else v) for n,k,v in data['uniforms']]
        options=dict(WATER_UNDERWATER=1,WATER_SCREEN_REFLECTIONS=1,WATER_REFLECTION_STRENGTH=1.0,
                     WATER_TRACE_TILES=0,WATER_REFLECTION_STEPS=64,WATER_REFRACTION=0,WATER_FOAM=0)
        on=render_resolve(runner,data,options);off=render_resolve(runner,data,dict(options,WATER_UNDERWATER=0))
        exits=changed=0
        for y in range(data['height']):
            for x in range(data['width']):
                if data['front'][y][x] is None:require(on[y][x]==off[y][x],'Waterline leaked past finite raster interface')
                else:exits+=1
                require(on[y][x][3]==off[y][x][3],'Waterline changed coverage')
                changed+=on[y][x]!=off[y][x]
        if eye_height>=0:require(changed==0,'Above-water boundary did not preserve old path')
        records.append(dict(eye_y=eye_height,visible_exit_pixels=exits,changed_pixels=changed))
    require(records[0]['visible_exit_pixels']>records[3]['visible_exit_pixels'],'Near-plane clipping control ineffective')
    return dict(samples=records,scope='Actual finite raster exits only. Near-clipped pixels deliberately retain native rendering; no inferred closure.')

def underwater_tests(runner,plate_path=None):
    result={}
    result['scattering']=scattering_tests(runner);print('PASS: M3B independent Snell/Fresnel/TIR core',flush=True)
    result['producer']=producer_tests(runner);print('PASS: M3B actual exit producer and native color preservation',flush=True)
    result['composite']=composite_tests(runner,plate_path);print('PASS: M3B actual finite-exit composite and exact fallbacks',flush=True)
    result['boundary']=boundary_tests(runner);print('PASS: M3B eight actual camera-height boundary cases',flush=True)
    return result
