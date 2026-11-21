"""M5 staged foam model: independent derivative, lifecycle and non-emission checks."""
import argparse, hashlib, json, math, sys, tempfile
from pathlib import Path

MODES=((11,3,.06,10),(4,-9,.04,-13),(7,13,.03,7),
       (49,19,.006,24),(-83,31,.0035,-31),(151,97,.0015,43))
def displacement(point, seconds, strength, speed, footprint):
    # Independent position-only model; derivatives below are finite differences.
    result=[0.,0.]
    for x,z,a,h in MODES:
        q=[(x*d[0]+z*d[1])/128 for d in (footprint[:2],footprint[2:])]
        freq=max(map(abs,q))
        if freq>=.5:continue
        fade=min(1.,max(0.,(freq-.25)/.25));fade=1-fade*fade*(3-2*fade)
        weight=math.prod(1. if abs(v)<1e-12 else math.sin(math.pi*v)/(math.pi*v) for v in q)*fade
        scale=1.5*strength*a*weight/math.hypot(x,z)
        angle=2*math.pi*((x*point[0]+z*point[1])/128+h*seconds*speed/200)
        for axis,k in enumerate((x,z)):result[axis]+=scale*k*math.cos(angle)
    return tuple(result)
def finite_derivatives(point,seconds,strength,speed,footprint):
    h=.0001
    jac=[]
    for axis in (0,1):
        a=list(point);b=list(point);a[axis]+=h;b[axis]-=h
        da=displacement(a,seconds,strength,speed,footprint)
        db=displacement(b,seconds,strength,speed,footprint)
        jac.extend((da[i]-db[i])/(2*h)+(1. if i==axis else 0.) for i in (0,1))
    a=displacement(point,seconds+h,strength,speed,footprint)
    b=displacement(point,seconds-h,strength,speed,footprint)
    velocity=tuple((a[i]-b[i])/(2*h) for i in (0,1))
    return jac,velocity

def model_tests(runner):
    from compile_glsl import SHADERS,expand
    from validate_gpu import compare,require
    from validate_water_waves import f32
    cases=[]
    for point in ((.001,.007),(17.31,31.7),(63.7,94.2),(127.999,125.3)):
        for seconds in (0.,13.4,199.99,3599.75):
            for strength in (.3,1.):
                for footprint in ((.02,0.,0.,.02),(.3,.1,-.2,.4)):
                    cases.append((tuple(map(f32,point+(seconds,strength))),tuple(map(f32,footprint))))
    source="#version 330 compatibility\n"+expand(SHADERS/'lib/water_foam_model.glsl')+"""
uniform sampler2D query, footprint;
uniform float testSpeed;
uniform int outputKind;
layout(location=0) out vec4 color;
void main(){
 ivec2 p=ivec2(gl_FragCoord.xy);vec4 q=texelFetch(query,p,0),f=texelFetch(footprint,p,0);
 WaterFoamFlow flow=waterFoamFlowAt(q.xy,q.z,q.w,testSpeed,f.xy,f.zw);
 if(outputKind==0)color=vec4(flow.displacement,flow.velocity);
 else if(outputKind==1)color=vec4(flow.jacobian[0],flow.jacobian[1]);
 else{vec2 material;bool ok=waterFoamMaterialPoint(q.xy,q.z,q.w,testSpeed,f.xy,f.zw,material,flow);
 color=vec4(material,flow.areaRatio,ok?1.0:0.0);}
}
"""
    pair=runner.pair('composite1',wrapper=source)
    textures=[('query',[[a for a,b in cases]],'RGBA32F'),('footprint',[[b for a,b in cases]],'RGBA32F')]
    records=[]
    for speed in (0.,1.,2.):
        expected=[[],[],[]]
        for q,f in cases:
            disp=displacement(q[:2],q[2],q[3],speed,f)
            jac,vel=finite_derivatives(q[:2],q[2],q[3],speed,f)
            expected[0].append(disp+vel);expected[1].append(tuple(jac))
            material=q[:2]
            for _ in range(16):
                d=displacement(material,q[2],q[3],speed,f)
                material=tuple(q[i]-d[i] for i in (0,1))
            j,_=finite_derivatives(material,q[2],q[3],speed,f)
            expected[2].append(material+(j[0]*j[3]-j[1]*j[2],1.))
        for kind in (0,1,2):
            image=runner.render('foam-model',pair,len(cases),1,textures,
                                [('testSpeed','f1',[speed]),('outputKind','i1',[kind])])
            records.append(compare(image,[expected[kind]],'flow speed '+str(speed)+' output '+str(kind),
                                   absolute=3e-5,relative=1e-6))
            if kind==2:require(all(px[3]==1. and px[2]>.675 for px in image[0]),'Invalid or folded foam flow')
    # Translation/time periodicity is checked on the model, not on a repeated output.
    point=(9.1,12.4);footprint=(.05,0,0,.05)
    for shift in ((128,0),(0,-128),(128,128)):
        a=displacement(point,13.4,1,1,footprint)
        b=displacement(tuple(point[i]+shift[i] for i in (0,1)),13.4,1,1,footprint)
        require(max(abs(x-y) for x,y in zip(a,b))<1e-13,'Flow tile seam')
    require(max(abs(a-b) for a,b in zip(displacement(point,0,1,2,footprint),
            displacement(point,3600,1,2,footprint)))<1e-13,'Flow timer seam')
    contraction=1.5*sum(a*math.hypot(x,z)*2*math.pi/128 for x,z,a,_ in MODES)
    return dict(samples=len(cases)*3,comparisons=records,derivative_reference='Central differences of independent position-only map',
                contraction_bound=contraction,minimum_area_bound=(1-contraction)**2)

def lifecycle_tests(runner):
    from compile_glsl import SHADERS,expand
    from validate_gpu import compare,require
    cases=[(.5,0.,0.,1/60,1),(.5,.6,.1,1/30,1),(.5,2.49,0.,.02,1),
           (.5,.4,.2,.2,1),(.5,.4,.2,.02,0),(.8,.4,.2,.02,1),
           (.5,-1.,.2,.02,1),(.5,.4,.2,0.,1),(0.,0.,.4,.02,1),
           (float('nan'),.4,.2,.02,1),(.5,.4,float('nan'),.02,1)]
    source="#version 330 compatibility\n"+expand(SHADERS/'lib/water_foam_model.glsl')+"""
uniform sampler2D inputs, flags;
layout(location=0) out vec4 color;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec4 q=texelFetch(inputs,p,0);float age;
float v=waterFoamEvolve(q.x,q.y,q.z,q.w,texelFetch(flags,p,0).r==1.0,age);color=vec4(v,age,0,1);}
"""
    expected=[]
    for old,age,e,dt,valid in cases:
        if not math.isfinite(e):expected.append((0,0,0,1));continue
        if not valid or not all(map(math.isfinite,(old,age,dt))) or not(0<=old<=.6 and 0<=age<=2.5 and 0<dt<=.1 and age+dt<=2.5):
            expected.append((e,0,0,1));continue
        value=old*2**(-dt/.65)
        expected.append((value,age+dt,0,1) if value>e else (e,0,0,1))
    image=runner.render('foam-life',runner.pair('composite1',wrapper=source),len(cases),1,
        [('inputs',[[c[:4] for c in cases]],'RGBA32F'),('flags',[[(c[4],0,0,0) for c in cases]],'RGBA32F')])
    result=compare(image,[expected],'foam decay/reset',absolute=3e-7,relative=1e-6)
    # Independent exponential evolution is frame-rate invariant absent fresh evidence.
    for hz in (30,60,144):
        value=.5
        for _ in range(hz):value*=2**(-1/hz/.65)
        require(abs(value-.5*2**(-1/.65))<2e-15,'Frame rate dependent decay')
    return dict(cases=len(cases),comparison=result)

def lighting_tests(runner):
    from compile_glsl import SHADERS,expand
    from validate_gpu import compare,require
    source="#version 330 compatibility\n"+expand(SHADERS/'lib/water_foam_model.glsl')+"""
uniform sampler2D skyInput,directInput,lampInput,weights;
layout(location=0) out vec4 color;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec4 q=texelFetch(weights,p,0);
color=vec4(waterFoamDiffuse(texelFetch(skyInput,p,0).rgb,texelFetch(directInput,p,0).rgb,
texelFetch(lampInput,p,0).rgb,q.x,q.y,q.z,q.w),1);}
"""
    cases=[((0,0,0),(0,0,0),(0,0,0),(0,0,1,1)),
           ((.2,.3,.5),(3,2.8,2.5),(2,1,.4),(1,0,1,1)),
           ((.2,.3,.5),(3,2.8,2.5),(2,1,.4),(1,0,1,0)),
           ((.2,.3,.5),(3,2.8,2.5),(2,1,.4),(0,1,1,0)),
           ((.2,.3,.5),(3,2.8,2.5),(2,1,.4),(0,0,1,1)),
           ((.2,.3,.5),(3,2.8,2.5),(2,1,.4),(1,.5,0,1))]
    textures=[(name,[[tuple(c[i])+(1,) if i<3 else tuple(c[i]) for c in cases]],'RGBA32F')
              for i,name in enumerate(('skyInput','directInput','lampInput','weights'))]
    expected=[]
    for sky,direct,lamp,(s,b,n,v) in cases:
        expected.append(tuple(albedo/math.pi*(sky[i]*s+direct[i]*s*n*v+lamp[i]*b**3)
                              for i,albedo in enumerate((.88,.91,.92)))+(1,))
    image=runner.render('foam-lighting',runner.pair('composite1',wrapper=source),len(cases),1,textures)
    result=compare(image,[expected],'foam diffuse illumination',absolute=3e-7,relative=1e-6)
    require(image[0][0]==(0,0,0,1) and image[0][4]==(0,0,0,1),'Unlit foam emitted light')
    require(all(a>b for a,b in zip(image[0][1][:3],image[0][2][:3])),'Foam ignored shadow visibility')
    return dict(cases=len(cases),comparison=result)

def local_composite_tests(runner):
    import copy
    from validate_gpu import require,compare
    import validate_gpu_water_transport as m1
    from validate_gpu_depth import matrix_uniform
    from validate_water_waves import f32
    from render_water_bench import png,display_rows,draw_text
    m1.FORMATS['shadowtex1']='R32F'
    identity=tuple(tuple(float(r==c) for c in range(4)) for r in range(4))
    shadow_projection=tuple(tuple((1/128 if r==c and r<3 else float(r==c==3)) for c in range(4)) for r in range(4))
    def scene(sky=1.,block=0.,land=True):
        result=m1.slab_scene(width=192,height=108,depth=2.,pitch=55.,sky=sky,block=block)
        result['textures']['shadowtex1']=[[(1.,0,0,1)]*16 for _ in range(16)]
        result['uniforms'] += [('shadowModelView','m4',matrix_uniform(identity)),
            ('shadowProjection','m4',matrix_uniform(shadow_projection)),('frameTimeCounter','f1',[17.])]
        if land:
            for y in range(result['height']):
                for x in range(result['width']//3):
                    z=result['textures']['colortex7'][y][x][3]
                    for name in ('colortex6','depthtex0','depthtex1'):
                        result['textures'][name][y][x]=(z,0,0,1)
                    result['textures']['colortex7'][y][x]=(0,0,0,0)
                    result['textures']['colortex8'][y][x]=(0,0,0,0)
                    result['textures']['colortex5'][y][x]=(.28,.19,.08,1)
                    result['textures']['colortex0'][y][x]=(.28,.19,.08,.5)
        return result
    def draw(data,enabled,options=None):
        return m1.render_resolve(runner,data,dict(WATER_FOAM=enabled,**(options or {})),label='M5 actual local composite')
    data=scene();off=draw(data,0);on=draw(data,1)
    changed=sum(max(abs(a-b) for a,b in zip(p[:3],q[:3]))>1e-6 for r,t in zip(off,on) for p,q in zip(r,t))
    require(changed>100,'Foam changed too few visible water pixels')
    require(all(p[3]==q[3] for r,t in zip(on,off) for p,q in zip(r,t)),'Foam changed native alpha')
    require(all(on[y][x]==off[y][x] for y in range(data['height']) for x in range(data['width']//3)),
            'Foam altered known land')
    # With waves absent, only supported land proximity is a source. The exact
    # same water-only slab must stay unchanged; a bottom gap is not shoreline.
    no_wave_on=draw(data,1,{'WATER_WAVES':0});no_wave_off=draw(data,0,{'WATER_WAVES':0})
    shore_count=sum(p!=q for r,t in zip(no_wave_on,no_wave_off) for p,q in zip(r,t))
    require(shore_count>30,'Known shoreline did not create visible foam')
    open_data=scene(land=False)
    compare(draw(open_data,1,{'WATER_WAVES':0}),draw(open_data,0,{'WATER_WAVES':0}),'No fabricated shore from bottom depth')
    rejected=[]
    for label,key,fn in [('two-water','colortex8',lambda v:(2/255,v[1],v[2],0)),
                         ('overlay','colortex8',lambda v:(1,v[1],v[2],0)),
                         ('front-mismatch','depthtex0',lambda v:(v[0]-.001,0,0,1)),
                         ('invalid-normal','colortex7',lambda v:(0,0,0,v[3]))]:
        bad=copy.deepcopy(open_data)
        bad['textures'][key]=[[fn(v) for v in row] for row in bad['textures'][key]]
        compare(draw(bad,1),draw(bad,0),label+' unchanged');rejected.append(label)
    for label,key,value in (('underwater','isEyeInWater',[1]),('lava','isEyeInWater',[2]),
                            ('zero-up','upPosition',[0,0,0]),('zero-light','shadowLightPosition',[0,0,0])):
        bad=copy.deepcopy(open_data)
        bad['uniforms']=[(n,k,value if n==key else v) for n,k,v in bad['uniforms']]
        compare(draw(bad,1),draw(bad,0),label+' foam bypass');rejected.append(label)
    black=scene(0.,0.,False)
    black['textures']['colortex0']=[[(0,0,0,p[3]) for p in row] for row in black['textures']['colortex0']]
    black['textures']['colortex5']=[[(0,0,0,1) for p in row] for row in black['textures']['colortex5']]
    black_image=draw(black,1)
    require(all(p[:3]==(0,0,0) for row in black_image for p in row),'Actual foam produced unlit cave glow')
    shadow=copy.deepcopy(data);shadow['textures']['shadowtex1']=[[(0,0,0,1)]*16 for _ in range(16)]
    shadow_image=draw(shadow,1)
    shadow_changes=sum(any(abs(a-b)>1e-6 for a,b in zip(p[:3],q[:3])) for r,t in zip(on,shadow_image) for p,q in zip(r,t))
    require(shadow_changes>30,'Actual foam ignored its surface shadow map')
    images=[]
    for label,linear in [('FOAM OFF',off),('LOCAL FOAM',on),('DIRECT SHADOWED',shadow_image)]:
        display=runner.render('M5 display',runner.pair('final'),data['width'],data['height'],[('colortex0',linear,'RGBA32F')])
        images.append((label,display_rows(display)))
    width,height=data['width'],data['height']
    plate=[[(17,22,30)]*(width*3) for _ in range(height+42)]
    draw_text(plate,6,7,'SYNTHETIC NATIVE FOAM / NOT MINECRAFT')
    for column,(label,rows) in enumerate(images):
        draw_text(plate,column*width+5,25,label)
        for y,row in enumerate(rows):plate[y+42][column*width:(column+1)*width]=row
    image_path=runner.scratch/'M5_local_foam.png';png(image_path,plate)
    return dict(changed_water_pixels=changed,shore_only_changed_pixels=shore_count,
                shadow_response_pixels=shadow_changes,invalid_cases=rejected,alpha_exact=True,
                land_unchanged=True,unlit_cave_black=True,plate=str(image_path))

def history_tests(runner):
    import copy
    from validate_gpu import compare,require,half
    import validate_gpu_water_transport as m1
    from validate_gpu_depth import matrix_uniform
    from validate_water_depth import inverse_matrix
    from validate_water_waves import f32
    w,h=19,13
    source=m1.slab_scene(w,h,depth=2.,pitch=55.)
    zero=[[(0,0,0,0)]*w for _ in range(h)]
    old_state=[[(half(.4),half(.2),0,1)]*w for _ in range(h)]
    old_metadata=[[(v[3],100.,0,1) for v in row] for row in source['textures']['colortex7']]
    projection=next(v for n,k,v in source['uniforms'] if n=='gbufferProjection')
    previous_view=inverse_matrix(source['model'])
    source['uniforms'] += [('frameTimeCounter','f1',[17.]),('frameTime','f1',[f32(1/60)]),
        ('frameCounter','i1',[100]),('previousCameraPositionInt','i3',[0,68,0]),
        ('previousCameraPositionFract','f3',[0,0,0]),
        ('gbufferPreviousModelView','m4',matrix_uniform(previous_view)),
        ('gbufferPreviousProjection','m4',projection)]
    source['textures']['colortex13']=old_state;source['textures']['colortex14']=old_metadata
    formats=dict(m1.FORMATS,colortex13='RGBA16F',colortex14='RG32F')
    options=dict(m1.BASE_OPTIONS,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_FOAM=2,
                 WATER_WAVES=0,SHADOWS_ENABLED=False)
    pair=runner.pair('composite1',options)
    def render(data,target):
        textures=[(name,image,formats[name]) for name,image in data['textures'].items()]
        return runner.render('M5 history target '+str(target),pair,w,h,textures,data['uniforms'],
            extra_targets=((1,1,'RGBA16F'),(2,2,'RG32F')),read_target=target,
            optional=list(data['textures'])+[v[0] for v in data['uniforms']])
    state=render(source,1);metadata=render(source,2);color=render(source,0)
    expected_coverage=half(.4)*2**(-f32(1/60)/.65)
    expected_state=[[(expected_coverage,half(.2)+f32(1/60),0,1)]*w for _ in range(h)]
    state_comparison=compare(state,expected_state,'M5 real RGBA16F history',half_units=2,absolute=1e-6)
    expected_metadata=[[(v[3],101.,0,1) for v in row] for row in source['textures']['colortex7']]
    compare(metadata,expected_metadata,'M5 full precision RG32F depth/frame',absolute=0,relative=0)
    base=copy.deepcopy(source)
    base['textures']={k:v for k,v in base['textures'].items() if k not in ('colortex13','colortex14')}
    baseline=m1.render_resolve(runner,base,dict(WATER_FOAM=0,WATER_WAVES=0,SHADOWS_ENABLED=False))
    foam=tuple(a/math.pi*(sky*.35*math.pi+d) for a,sky,d in zip((.88,.91,.92),(.55,.65,.7),(3.5,3.2,2.7)))
    expected_color=[[tuple(p[c]*(1-expected_coverage)+foam[c]*expected_coverage for c in range(3))+(p[3],)
                     for p in row] for row in baseline]
    color_comparison=compare(color,expected_color,'M5 stored-history actual composite blend',absolute=3e-5,relative=2e-5)
    records=[]
    for label,change in (
        ('cleared-on-allocation',('texture','colortex13',zero)),
        ('clear-stamp-after-resize',('texture','colortex14',zero)),
        ('stale-frame',('texture','colortex14',[[(v[0],99.,0,1) for v in row] for row in old_metadata])),
        ('occluded-old-depth',('texture','colortex14',[[(v[0]-.0001,v[1],0,1) for v in row] for row in old_metadata])),
        ('opposite-normal',('texture','colortex13',[[(.4,.2,0,-1)]*w for _ in range(h)])),
        ('expired-age',('texture','colortex13',[[(.4,2.6,0,1)]*w for _ in range(h)])),
        ('bad-history-size',('texture','colortex13',[[(.4,.2,0,1)]*(w-1) for _ in range(h)])),
        ('long-frame',('uniform','frameTime',[.2])),
        ('camera-teleport',('uniform','previousCameraPositionInt',[32,68,0])),
        ('different-FOV',('uniform','gbufferPreviousProjection',[v*1.1 if i==0 else v for i,v in enumerate(projection)])),
    ):
        data=copy.deepcopy(source)
        kind,key,value=change
        if kind=='texture':data['textures'][key]=value
        else:data['uniforms']=[(n,k,value if n==key else v) for n,k,v in data['uniforms']]
        result=render(data,1)
        require(all(px[0]==0. and px[1]==0. for row in result for px in row),label+' retained foam')
        records.append(label)
    # Nonconstant history patterns make wrong reprojection directions observable.
    # Build the old camera plane independently by ray/plane intersections.
    projection_rows=tuple(tuple(projection[c*4+r] for c in range(4)) for r in range(4))
    def multiply(a,b):return tuple(tuple(sum(a[r][k]*b[k][c] for k in range(4)) for c in range(4)) for r in range(4))
    def transform(a,v):return tuple(sum(x*y for x,y in zip(row,v)) for row in a)
    reprojections=[]
    for label,delta,yaw in (('camera-translation',(.233,0,.117),0.),('camera-yaw',(0,0,0),13.)):
        angle=math.radians(yaw);co,si=math.cos(angle),math.sin(angle)
        rotate=((co,0,si,0),(0,1,0,0),(-si,0,co,0),(0,0,0,1))
        old_view=tuple(tuple(map(f32,row)) for row in multiply(previous_view,rotate))
        old_inverse=inverse_matrix(old_view);inverse_projection=inverse_matrix(projection_rows)
        old_product=multiply(projection_rows,old_view)
        data=copy.deepcopy(source)
        data['uniforms']=[(n,k,matrix_uniform(old_view) if n=='gbufferPreviousModelView' else
                          list(delta) if n=='cameraPositionFract' else v) for n,k,v in data['uniforms']]
        history=[];depths=[]
        for y in range(h):
            hr=[];dr=[]
            for x in range(w):
                a=.12+.30*x/(w-1)+.10*y/(h-1)
                hr.append((half(a),half(.2),0,1))
                ray_h=transform(inverse_projection,(2*(x+.5)/w-1,2*(y+.5)/h-1,0,1))
                view_ray=tuple(v/ray_h[3] for v in ray_h[:3])
                world_ray=transform(old_inverse,view_ray+(0,))[:3]
                origin=transform(old_inverse,(0,0,0,1))[:3]
                distance=(-4+delta[1]-origin[1])/world_ray[1]
                point=tuple(origin[i]+distance*world_ray[i] for i in range(3))
                clip=transform(old_product,point+(1,));raw=f32(clip[2]/clip[3]*.5+.5)
                dr.append((raw,100,0,1))
            history.append(hr);depths.append(dr)
        data['textures']['colortex13']=history;data['textures']['colortex14']=depths
        expected=[];changed_cells=0
        for y in range(h):
            row=[]
            for x in range(w):
                player=transform(source['model'],source['front'][y][x]+(1,))[:3]
                position=tuple(player[i]+delta[i] for i in range(3))
                clip=transform(old_product,position+(1,));uv=(clip[0]/clip[3]*.5+.5,clip[1]/clip[3]*.5+.5)
                if any(v<0 or v>=1 for v in uv):row.append((0,0,0,1));continue
                px,py=int(uv[0]*w),int(uv[1]*h)
                changed_cells+=int((px,py)!=(x,y))
                row.append((history[py][px][0]*2**(-f32(1/60)/.65),half(.2)+f32(1/60),0,1))
            expected.append(row)
        output=render(data,1)
        require(changed_cells>20,label+' did not move enough sampled cells')
        comparison=compare(output,expected,label+' independent world plane reprojection',half_units=2,absolute=1e-6)
        reprojections.append(dict(label=label,changed_history_cells=changed_cells,comparison=comparison))
    cut=copy.deepcopy(source)
    flipped=tuple(tuple(-v if c in (0,2) else v for c,v in enumerate(row)) for row in previous_view)
    cut['uniforms']=[(n,k,matrix_uniform(flipped) if n=='gbufferPreviousModelView' else v) for n,k,v in cut['uniforms']]
    require(all(px[0]==0. and px[1]==0. for row in render(cut,1) for px in row),'Camera rotation cut kept history')
    records.append('camera-rotation-cut')
    # A skipped frame rejects the history; a real counter wrap accepts the previous tag.
    wrapped=copy.deepcopy(source)
    wrapped['uniforms']=[(n,k,[0] if n=='frameCounter' else v) for n,k,v in wrapped['uniforms']]
    wrapped['textures']['colortex14']=[[(v[0],720720.,0,1) for v in row] for row in old_metadata]
    compare(render(wrapped,1),state,'Frame-counter wrap preserves valid foam',absolute=0,relative=0)
    # Keep half-float storage on the actual input/output chain; do not idealize it.
    chained=copy.deepcopy(source);chained['textures']['colortex13']=state;chained['textures']['colortex14']=metadata
    chained['uniforms']=[(n,k,[101] if n=='frameCounter' else [f32(1/30)] if n=='frameTime' else v)
                         for n,k,v in chained['uniforms']]
    next_state=render(chained,1)
    expected_next=[[(p[0]*2**(-f32(1/30)/.65),p[1]+f32(1/30),p[2],p[3]) for p in row] for row in state]
    compare(next_state,expected_next,'Quantized history next frame / changing cadence',half_units=2,absolute=1e-6)
    # Ambiguous current ownership must clear both persistent outputs.
    overlay=copy.deepcopy(source)
    overlay['textures']['colortex8']=[[(1,0,1,0)]*w for _ in range(h)]
    compare(render(overlay,1),zero,'Overlay clears foam history',absolute=0,relative=0)
    compare(render(overlay,2),[[(0,0,0,1)]*w for _ in range(h)],'Overlay clears full-depth stamp',absolute=0,relative=0)
    underwater=copy.deepcopy(source)
    underwater['uniforms']=[(n,k,[1] if n=='isEyeInWater' else v) for n,k,v in underwater['uniforms']]
    compare(render(underwater,1),zero,'Underwater clears foam history',absolute=0,relative=0)
    compare(render(underwater,2),[[(0,0,0,1)]*w for _ in range(h)],'Underwater clears depth stamp',absolute=0,relative=0)
    return dict(pixels=w*h,history_formats=['RGBA16F','RG32F'],state=state_comparison,color=color_comparison,
                exact_depth_frame=True,reset_controls=records,reprojections=reprojections,quantized_frame_chain=True,
                cost_MiB_1080p_double_buffer=1920*1080*(8+8)*2/(1024**2),
                scope='Actual mixed MRT composite and readback-fed next frame; Iris allocation/flipping not executed')

def foam_tests(runner, plate_path=None):
    """Public entry for the existing tools/validate_gpu.py runner."""
    results=dict(scope=__doc__,flow=model_tests(runner),lifecycle=lifecycle_tests(runner),
                 lighting=lighting_tests(runner),local_composite=local_composite_tests(runner),
                 history=history_tests(runner))
    if plate_path is not None:
        image=Path(results['local_composite']['plate']).read_bytes()
        with Path(plate_path).open('xb') as stream:stream.write(image)
        results['local_composite']['plate']=str(plate_path)
    return results

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--support-root',type=Path,required=True)
    parser.add_argument('--history-only',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(args.support_root/'tools'))
    import compile_glsl as c,validate_gpu as g
    c.SHADERS=root/'shaders';c.expand.cache_clear();g.SHADERS=c.SHADERS;g.ROOT=root
    scratch=Path(tempfile.mkdtemp(prefix='native-m5-',dir=str(root)))
    runner=g.Runner(scratch,r'C:/msys64/ucrt64/bin/g++.exe')
    results=dict(scope=__doc__)
    if not args.history_only:
        results.update(flow=model_tests(runner),lifecycle=lifecycle_tests(runner),lighting=lighting_tests(runner),local_composite=local_composite_tests(runner))
    results.update(history=history_tests(runner),driver=runner.gl)
    results['shader_sha256']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((root/'shaders').rglob('*')) if p.is_file()}
    report=scratch/'M5_native.json';report.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print('PASS: '+str(report),flush=True)
if __name__=='__main__':main()
