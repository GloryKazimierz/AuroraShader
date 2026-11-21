"""GPU checks for shadow caustics and their interaction with water transport."""
import copy
import math
import struct
from compile_glsl import ROOT,SHADERS,expand
from validate_gpu import require,compare,write_text
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix,perspective_matrix
from validate_foliage import IDENTITY4
from validate_water_waves import f32
from validate_gpu_water_transport import slab_scene,FORMATS,BASE_OPTIONS,analytical_transport,smooth

OPTIONS=dict(WATER_OPTICS=1,WATER_CAUSTICS=1,WATER_CAUSTICS_STRENGTH=1.0,
             IRIS_FEATURE_PER_BUFFER_BLENDING=True)
LIGHT_VIEW=((1.,0.,0.,0.),(0.,0.,-1.,0.),(0.,1.,0.,0.),(0.,0.,0.,1.))
LIGHT_PROJ=((.125,0.,0.,0.),(0.,.125,0.,0.),(0.,0.,-.03125,0.),(0.,0.,0.,1.))
SIZE=256
K=2*math.pi/4
PHASE=0.


def normal_at(x,amplitude):
    slope=amplitude*math.cos(K*x+PHASE)
    length=math.sqrt(1+slope*slope)
    return (-slope/length,1/length,0.)


def map_analytic(x,depth,amplitude,ior=1.333):
    nx,ny,_=normal_at(x,amplitude);eta=1/ior
    factor=eta*ny-math.sqrt(1-eta*eta*(1-ny*ny))
    tx,ty=factor*nx,-eta+factor*ny
    return x+depth*tx/(-ty)


def finite_area_truth(entry,depth,amplitude,radius=None,ior=1.333):
    radius=.04+.03*depth if radius is None else radius
    area=(map_analytic(entry+radius,depth,amplitude,ior)-map_analytic(entry-radius,depth,amplitude,ior))/(2*radius)
    raw=min(4.,1/area) if area>.05 else 1.
    return 1+(raw-1)*(1-smooth(8,24,depth)),area


def encode_cpu(normal,depth,storage):
    maximum=255 if storage==0 else 65535
    center=128 if storage==0 else 32768
    multiplier=254 if storage==0 else 65534
    sx,sz=normal[0]/normal[1],normal[2]/normal[1]
    qx,qz=math.floor(sx*multiplier+center+.5),math.floor(sz*multiplier+center+.5)
    word=(math.floor(f32(depth)*65534+.5)+1 if storage==0 else
          struct.unpack('<I',struct.pack('<f',depth))[0]+1)
    bits=8 if storage==0 else 16
    return tuple(v/maximum for v in (qx,qz,word>>bits,word&maximum))


def decode_cpu(record,depth,storage):
    maximum=255 if storage==0 else 65535
    center=128 if storage==0 else 32768
    multiplier=254 if storage==0 else 65534
    codes=[math.floor(v*maximum+.5) for v in record]
    word=(codes[2]<<(8 if storage==0 else 16))|codes[3]
    expected=(math.floor(f32(depth)*65534+.5)+1 if storage==0 else
              struct.unpack('<I',struct.pack('<f',depth))[0]+1)
    if not codes[0] or not codes[1] or not word or word!=expected:return None
    x,z=(codes[0]-center)/multiplier,(codes[1]-center)/multiplier
    length=math.sqrt(1+x*x+z*z)
    return (x/length,1/length,z/length)


def shadow_scene(depth=2.,amplitude=.08,water_y=0.,kind='valid',storage=1):
    record=[];front=[];opaque=[]
    water_depth=f32(.5-water_y/64)
    bed_depth=f32(.5-(water_y-depth)/64)
    for y in range(SIZE):
        rr=[];fr=[];op=[]
        for x in range(SIZE):
            world_x=16*((x+.5)/SIZE-.5)
            n=normal_at(world_x,amplitude)
            record_depth=f32(water_depth+.01) if kind=='mismatched-depth' else water_depth
            rec=tuple(map(f32,n))+(record_depth,) if storage<0 else encode_cpu(n,record_depth,storage)
            if kind=='unknown':rec=(0,0,0,0)
            rr.append(rec);fr.append((water_depth,0,0,1))
            opaque_value=.25 if kind=='opaque-before-water' else bed_depth
            if kind=='source-obstacle' and x==138 and y==127:opaque_value=f32(bed_depth-.5/64)
            op.append((opaque_value,0,0,1))
        record.append(rr);front.append(fr);opaque.append(op)
    return [('shadowcolor0',record,'RGBA32F' if storage<0 else 'RGBA8' if storage==0 else 'RGBA16'),('shadowtex0',front,'R32F'),('shadowtex1',opaque,'R32F')]


def shadow_uniforms():
    return [(name,'m4',matrix_uniform(matrix)) for name,matrix in (
        ('shadowModelView',LIGHT_VIEW),('shadowProjection',LIGHT_PROJ),
        ('shadowModelViewInverse',inverse_matrix(LIGHT_VIEW)),
        ('shadowProjectionInverse',inverse_matrix(LIGHT_PROJ)))]


def core_tests(runner):
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics.glsl')+'''
uniform sampler2D testWaterShare,testBed,testNormal;
uniform vec3 towardLight;
layout(location=0) out vec4 result;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec4 a=texelFetch(testWaterShare,p,0);
 result=vec4(waterShadowCausticGain(a.xyz,texelFetch(testBed,p,0).xyz,
 texelFetch(testNormal,p,0).xyz,towardLight,a.w),0,0,1);}
'''
    pair=runner.pair('composite',OPTIONS,source)
    cases=[];all_error=0
    for label,depth,amplitude in (('flat',2.,0.),('curved',2.,.08),('deep-filtered',16.,.02),('deep-disabled',24.,.08)):
        entries=[-5.8+i*11.6/63 for i in range(64)]
        receivers=[map_analytic(x,depth,amplitude) for x in entries]
        query=[('testWaterShare',[[(x,0,0,.65) for x in receivers]],'RGBA32F'),
               ('testBed',[[(x,-depth,0,1) for x in receivers]],'RGBA32F'),
               ('testNormal',[[(0,1,0,1)]*len(entries)],'RGBA32F')]
        result=runner.render(label,pair,len(entries),1,shadow_scene(depth,amplitude)+query,
                             shadow_uniforms()+[('towardLight','f3',(0,1,0))])
        maximum=0;active=0;flux=[]
        for entry,pixel in zip(entries,result[0]):
            expected,area=finite_area_truth(entry,depth,amplitude)
            error=abs(pixel[0]-expected);maximum=max(maximum,error)
            require(math.isfinite(pixel[0]) and 0<=pixel[0]<=4,label+': nonfinite/unbounded gain')
            require(error<(1e-5 if label=='flat' else .004),label+': finite-area oracle differs '+str((entry,pixel[0],expected,error)))
            active+=abs(pixel[0]-1)>1e-4
            if depth<8:flux.append(pixel[0]*area)
        if label=='curved':require(active>50,'curved field is inactive')
        if label=='deep-disabled':require(all(p==(1,0,0,1) for p in result[0]),'deep cutoff not exact')
        cases.append(dict(label=label,samples=len(entries),active=active,max_gain_error=maximum,
                          mean_area_weighted_flux=sum(flux)/len(flux) if flux else None))
        all_error=max(all_error,maximum)
    negatives=[]
    for label,kind,q,bed_normal,water_y,bed_y,receiver_x,light in (
        ('torch-only','valid',0.,(0,1,0),0.,-2.,1.,(0,1,0)),
        ('shadowed','opaque-before-water',.65,(0,1,0),0.,-2.,1.,(0,1,0)),
        ('unknown-overlay','unknown',.65,(0,1,0),0.,-2.,1.,(0,1,0)),
        ('wrong-shadow-depth','mismatched-depth',.65,(0,1,0),0.,-2.,1.,(0,1,0)),
        ('different-interface','valid',.65,(0,1,0),.1,-2.,1.,(0,1,0)),
        ('source-obstacle','source-obstacle',.65,(0,1,0),0.,-2.,.7,(0,1,0)),
        ('different-bed','valid',.65,(0,1,0),0.,-2.1,1.,(0,1,0)),
        ('vertical-wall','valid',.65,(1,0,0),0.,-2.,1.,(0,1,0)),
        ('map-edge','valid',.65,(0,1,0),0.,-2.,7.99,(0,1,0)),
        ('no-sun','valid',.65,(0,1,0),0.,-2.,1.,(1,0,0)),
        ('no-medium','valid',.65,(0,1,0),0.,.1,1.,(0,1,0)),
    ):
        query=[('testWaterShare',[[(receiver_x,water_y,0,q)]],'RGBA32F'),
               ('testBed',[[(receiver_x,bed_y,0,1)]],'RGBA32F'),
               ('testNormal',[[bed_normal+(1,)]],'RGBA32F')]
        image=runner.render(label,pair,1,1,shadow_scene(kind=kind)+query,
                            shadow_uniforms()+[('towardLight','f3',light)])
        compare(image,[[(1,0,0,1)]],label);negatives.append(label)
    return dict(cases=cases,negative_cases=negatives,max_gain_error=all_error,
                bound='Local flat-plane normalization; no multi-path/global photon conservation claim')


def capture_tests(runner):
    vertex='''#version 330 compatibility
uniform vec3 originalNormal;
uniform int material;
out vec2 texcoord;
out vec4 glcolor;
out vec3 causticPlayerPosition,causticNormalWorld;
flat out int causticWaterMaterial;
void main(){gl_Position=gl_Vertex;texcoord=gl_MultiTexCoord0.xy;glcolor=vec4(1);
 causticPlayerPosition=vec3(gl_Vertex.x*8,0,-gl_Vertex.y*8);
 causticNormalWorld=originalNormal;causticWaterMaterial=material;}
'''
    vp=runner.scratch/'caustic-capture.vert';write_text(vp,vertex)
    uniforms=[('originalNormal','f3',(0,1,0)),('material','i1',(1,)),
              ('gbufferModelView','m4',matrix_uniform(IDENTITY4)),
              ('gbufferModelViewInverse','m4',matrix_uniform(IDENTITY4)),
              ('cameraPositionInt','i3',(16777217,64,-16777217)),
              ('cameraPositionFract','f3',(.25,.5,.75)),('frameTimeCounter','f1',(17.,))]
    optional=[u[0] for u in uniforms]
    atlas=[[(1,1,1,0 if (x+y)%5==0 else 1) for x in range(32)] for y in range(16)]
    results=[]
    for label,waves,normal,material in (('flat',0,(0,1,0),1),('filtered',1,(0,1,0),1),
                                        ('opaque',1,(0,1,0),0),('side',1,(1,0,0),1)):
        options=dict(OPTIONS,WATER_WAVES=waves)
        _,fs=runner.pair('shadow',options)
        values=[(n,k,(normal if n=='originalNormal' else (material,) if n=='material' else v)) for n,k,v in uniforms]
        image=runner.render(label,(vp,fs),32,16,[('gtexture',atlas,'RGBA32F')],values,storage='RGBA16',optional=optional)
        diagnostic=runner.render(label+' alpha diagnostic',(vp,fs),32,16,[('gtexture',atlas,'RGBA32F')],values,optional=optional)
        active=0;perturbed=0
        for y,row in enumerate(image):
            for x,p in enumerate(row):
                if not atlas[y][x][3]:require(p==(0,0,0,0) and diagnostic[y][x][3]==-13,label+': alpha hole wrote metadata');continue
                if material==0 or normal[1]<.95:require(p==(0,0,0,0),label+': non-top-water recorded');continue
                decoded=decode_cpu(p,.5,1)
                require(decoded is not None and decoded[1]>.95,label+': normal/matched-depth record differs')
                active+=1;perturbed+=abs(decoded[0])+abs(decoded[2])>1e-5
        if label=='filtered':require(perturbed>active//2,'world-anchored filtered waves absent')
        results.append(dict(label=label,water_pixels=active,perturbed=perturbed))
    return results


def transport_tests(runner):
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_transport.glsl')+'''
uniform sampler2D testInput;
layout(location=0) out vec4 result;
void main(){vec4 v=texelFetch(testInput,ivec2(gl_FragCoord.xy),0);
 result=vec4(waterTransportRadiance(vec3(.6,.4,.2),v.x,v.y,v.z,.3,.7,vec3(.1,.2,.3),v.w),1);}
'''
    pair=runner.pair('composite',OPTIONS,source)
    cases=[(q,view,light,gain) for q in (0.,.65,1.) for view,light in ((0.,0.),(2.,3.),(12.,16.)) for gain in (.25,1.,3.)]
    rows=[[tuple(map(f32,v)) for v in cases]]
    image=runner.render('direct-only-transport',pair,len(cases),1,[('testInput',rows,'RGBA32F')])
    expected=[]
    for q,view,light,gain in rows[0]:
        base=analytical_transport((.6,.4,.2),q,view,light,.3,.7,(.1,.2,.3))
        delta=[c*q*(gain-1)*math.exp(-(view+light)*ext) for c,ext in zip((.6,.4,.2),(.192,.075,.05))]
        expected.append(tuple(a+b for a,b in zip(base,delta))+(1.,))
    comparison=compare(image,[expected],'gain applies only to qL',absolute=2e-6,relative=2e-5)
    require(all(image[0][i]==image[0][i+1]==image[0][i+2] for i in (0,3,6)),
            'caustics changed torch/ambient-only radiance')
    return dict(samples=len(cases),comparison=comparison,torch_exact=True)


def receiver_pixel_span(point,scene):
    p=next(values for name,kind,values in scene['uniforms'] if name=='gbufferProjection')
    pxx,pyy=p[0],p[5]
    nx,ny=point[0]/(-point[2])*pxx,point[1]/(-point[2])*pyy
    bed_y=sum(scene['model'][1][c]*point[c] for c in range(3))
    corners=[]
    for ox,oy in ((-1/scene['width'],0),(1/scene['width'],0),(0,-1/scene['height']),(0,1/scene['height'])):
        ray=((nx+ox)/pxx,(ny+oy)/pyy,-1.)
        world=tuple(sum(scene['model'][r][c]*ray[c] for c in range(3)) for r in range(3))
        scale=bed_y/world[1]
        corners.append((world[0]*scale,world[2]*scale))
    return max(math.hypot(*(a-b for a,b in zip(corners[i+1],corners[i]))) for i in (0,2))


def footprint_tests(runner):
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics.glsl')+'''
uniform sampler2D points;
uniform ivec2 footprintSize;
uniform mat4 projection,inverseProjection,inverseView;
layout(location=0) out vec4 result;
void main(){vec2 dx,dy;bool valid=waterCausticPixelFootprint(texelFetch(points,ivec2(gl_FragCoord.xy),0).xyz,
 footprintSize,projection,inverseProjection,inverseView,dx,dy);result=valid?vec4(dx,dy):vec4(-1);}
'''
    pair=runner.pair('composite',OPTIONS,source);results=[]
    for pitch in (10.,35.,70.):
        angle=math.radians(pitch);sine,cosine=math.sin(angle),math.cos(angle)
        inv=((1.,0.,0.,0.),(0.,cosine,sine,0.),(0.,-sine,cosine,0.),(0.,0.,0.,1.))
        for width,height in ((64,36),(256,144),(1920,1080)):
            projection=perspective_matrix(70.,width/height,.05,512.)
            heights=(2.,8.,32.,128.)
            points=[(0,0,-h/sine,1) for h in heights]
            uniforms=[('footprintSize','i2',(width,height)),('projection','m4',matrix_uniform(projection)),
                      ('inverseProjection','m4',matrix_uniform(inverse_matrix(projection))),('inverseView','m4',matrix_uniform(inv))]
            image=runner.render('analytic footprint',pair,len(points),1,[('points',[points],'RGBA32F')],uniforms)
            expected=[]
            for h in heights:
                dx=2*h/(sine*projection[0][0]*width)
                ry=1/(projection[1][1]*height)
                upper=-h*(sine*ry+cosine)/(sine-cosine*ry)
                lower=-h*(-sine*ry+cosine)/(sine+cosine*ry)
                expected.append((dx,0,0,upper-lower))
            results.append(compare(image,[expected],'perspective plane footprint '+str((pitch,width,height)),absolute=.0002,relative=.00002))
    # Real caustic field: unresolved isotropic or grazing anisotropic pixels,
    # and invalid footprints, are neutral before any shadow-map lookup.
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics.glsl')+'''
uniform sampler2D footprints;
layout(location=0) out vec4 result;
void main(){vec4 f=texelFetch(footprints,ivec2(gl_FragCoord.xy),0);
 float weight=causticResolutionWeight(f.xy,f.zw);
 result=vec4(waterShadowCausticGain(vec3(.7,0,0),vec3(.7,-2,0),vec3(0,1,0),vec3(0,1,0),.65,f.xy,f.zw),weight,0,1);}
'''
    values=[(.01,0,0,.01),(.18,0,0,.18),(.2,0,0,.2),(1,0,0,1),(.01,0,0,1),(math.nan,0,0,.01)]
    image=runner.render('footprint suppression',runner.pair('composite',OPTIONS,source),len(values),1,
                        shadow_scene()+[('footprints',[values],'RGBA32F')],shadow_uniforms())[0]
    require(abs(image[0][0]-1)>.01,'resolved control is not focusing light')
    for i,(value,pixel) in enumerate(zip(values,image)):
        span=max(math.hypot(*value[:2]),math.hypot(*value[2:]))
        weight=0 if not math.isfinite(span) else 1-smooth(.25,.5,span/(128/math.hypot(151,97)))
        require(abs(pixel[1]-weight)<2e-6,'Nyquist fade differs')
        if i<3:require(abs(pixel[0]-(1+(image[0][0]-1)*weight))<2e-5,'filtered gain energy blend differs')
        else:require(pixel==(1,0,0,1),'unresolved/invalid footprint was not exact neutral')
    return dict(plane_comparisons=results,plane_samples=len(results)*4,filter_cases=len(values),
                scope='Analytic perspective horizontal-plane footprint; no divergent hardware derivatives; camera ray footprint, not complete refracted-ray-bundle Jacobian')


def integrated_tests(runner,plate=None):
    scene=slab_scene(width=128,height=72,depth=2.,pitch=65.,share=.65)
    scene['textures']['colortex1']=[[(.5+.5*scene['up'][0],.5+.5*scene['up'][1],
                                    .5+.5*scene['up'][2],1.)]*scene['width'] for _ in range(scene['height'])]
    shadow=shadow_scene(depth=2.,amplitude=.08,water_y=-4.)
    textures=[(n,image,FORMATS.get(n,'RGBA32F')) for n,image in scene['textures'].items()]+shadow
    uniforms=scene['uniforms']+shadow_uniforms()
    optional=[n for n,_,_ in textures]+[n for n,_,_ in uniforms]
    options=dict(BASE_OPTIONS,**OPTIONS)
    pair=runner.pair('composite',dict(options,WATER_CAUSTICS=0))
    off=runner.render('M4 production off',pair,scene['width'],scene['height'],textures,uniforms,optional=optional)
    _,fs=runner.pair('composite',options)
    on=runner.render('M4 production on',(pair[0],fs),scene['width'],scene['height'],textures,uniforms,optional=optional)
    changed=0;max_error=0.
    for y,row in enumerate(on):
        for x,pixel in enumerate(row):
            require(pixel[3]==off[y][x][3],'M4 changed native alpha')
            if x==0 or y==0 or x==scene['width']-1 or y==scene['height']-1:
                require(pixel==off[y][x],'M4 changed border fallback');continue
            front,back=scene['front'][y][x],scene['back'][y][x]
            world_front=tuple(sum(scene['model'][r][c]*front[c] for c in range(3)) for r in range(3))
            world_back=tuple(sum(scene['model'][r][c]*back[c] for c in range(3)) for r in range(3))
            depth=world_front[1]-world_back[1]
            distance=math.sqrt(sum((a-b)**2 for a,b in zip(front,back)))
            # Independent converged scalar inversion of the analytic sinusoidal
            # normal field (not the production four-step texture procedure).
            entry=world_back[0]
            for iteration in range(30):
                error=map_analytic(entry,depth,.08)-world_back[0]
                h=1e-5
                derivative=(map_analytic(entry+h,depth,.08)-map_analytic(entry-h,depth,.08))/(2*h)
                entry-=error/derivative
            span=receiver_pixel_span(back,scene)
            weight=1-smooth(.25,.5,span/(128/math.hypot(151,97)))
            gain,_=finite_area_truth(entry,depth,.08,max(.04+.03*depth,.5*span))
            gain=1+(gain-1)*weight
            eye_length=math.sqrt(sum(v*v for v in front))
            eye_cosine=sum(-v/eye_length*u for v,u in zip(front,scene['up']))
            confidence=smooth(0,2,min(x+.5,y+.5,scene['width']-x-.5,scene['height']-y-.5))*smooth(.03,.12,eye_cosine)
            confidence*=smooth(.001,.03,depth)*(1-smooth(48,64,distance))
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                gap=abs(scene['back'][ny][nx][2]-back[2])
                confidence*=1-smooth(max(.25,distance*.05),max(.5,distance*.15),gap)
            source=scene['textures']['colortex5'][y][x]
            share=scene['textures']['colortex9'][y][x][0]
            delta=[c*share*(gain-1)*math.exp(-(distance+depth)*ext)*confidence
                   for c,ext in zip(source[:3],(.192,.075,.05))]
            expected=tuple(a+b for a,b in zip(off[y][x][:3],delta))
            error=max(abs(a-b) for a,b in zip(pixel[:3],expected));max_error=max(max_error,error)
            require(error<.0003,'production direct-light delta differs: '+str((x,y,error)))
            changed+=pixel[:3]!=off[y][x][:3]
    require(changed>200,'actual composite did not apply caustics')
    if plate:
        from render_water_bench import png,display_rows,draw_text
        w,h=scene['width'],scene['height']
        panels=[]
        for frame in (off,on):
            display=runner.render('caustic final',runner.pair('final'),w,h,[('colortex0',frame,'RGBA32F')])
            panels.append(display_rows(display))
        panels.append([[tuple(min(255,abs(a-b)*12) for a,b in zip(p,q)) for p,q in zip(ar,br)]
                       for ar,br in zip(*panels)])
        sheet=[[(14,19,24)]*w*3 for _ in range(h+20)]
        for col,(label,img) in enumerate(zip(('OFF','CAUSTICS','DELTA X12'),panels)):
            draw_text(sheet,col*w+3,5,label)
            for j,row in enumerate(img):
                sheet[j+20][col*w:(col+1)*w]=row
        png(plate,sheet)
    negatives=[];max_zero_ulps=0
    half_off=runner.render('native half off',runner.pair('composite',dict(options,WATER_CAUSTICS=0)),
        scene['width'],scene['height'],textures,uniforms,storage='RGBA16F',optional=optional)
    for label,overrides in [('strength-zero',{'WATER_CAUSTICS_STRENGTH':0.0}),('waves-off',{'WATER_WAVES':0}),
                            ('wave-strength-zero',{'WATER_WAVE_STRENGTH':0.0})]:
        _,fragment=runner.pair('composite',dict(options,**overrides))
        value=runner.render(label,(pair[0],fragment),scene['width'],scene['height'],textures,uniforms,optional=optional)
        # Zero controls bypass the entire caustic path at its callers. Both
        # FP32 diagnostic and native Iris RGBA16F must now remain exact.
        for actual_row,expected_row in zip(value,off):
            for actual_pixel,expected_pixel in zip(actual_row,expected_row):
                require(actual_pixel[3]==expected_pixel[3],label+': zero-control alpha changed')
                for actual,expected in zip(actual_pixel[:3],expected_pixel[:3]):
                    ulps=abs(struct.unpack('<I',struct.pack('<f',actual))[0]-struct.unpack('<I',struct.pack('<f',expected))[0])
                    require(ulps==0,label+': diagnostic changed despite the neutral caller bypass')
                    max_zero_ulps=max(max_zero_ulps,ulps)
        half_value=runner.render(label+' native half',(pair[0],fragment),scene['width'],scene['height'],
            textures,uniforms,storage='RGBA16F',optional=optional)
        compare(half_value,half_off,label+' actual RGBA16F');negatives.append(label)
    return dict(pixels=scene['width']*scene['height'],changed=changed,max_analytic_delta_error=max_error,
                exact_RGBA16F_zero_controls=negatives,max_RGBA32F_zero_diagnostic_ulps=max_zero_ulps,alpha_exact=True)


def caustic_test_source(source,storage):
    if storage!=0:return source
    production=expand(SHADERS/'lib/water_caustics_packing.glsl')
    counterexample=(ROOT/'tools/fixtures/water_caustics_rgba8_counterexample.glsl').read_text(encoding='utf-8')
    counterexample=counterexample.replace('#include "/lib/water_caustics_settings.glsl"',
                                         expand(SHADERS/'lib/water_caustics_settings.glsl'))
    require(source.count(production)==1,'Test-only storage replacement must be unique')
    return source.replace(production,counterexample,1)


def packing_tests(runner):
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics_packing.glsl')+'''
uniform sampler2D inputs;
layout(location=0) out vec4 result;
void main(){vec4 v=texelFetch(inputs,ivec2(gl_FragCoord.xy),0);result=encodeWaterCaustic(v.xyz,v.w);}
'''
    decoder='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics_packing.glsl')+'''
uniform sampler2D records,depths;
layout(location=0) out vec4 result;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec3 n;
 bool valid=decodeWaterCaustic(texelFetch(records,p,0),texelFetch(depths,p,0).r,n);result=vec4(n,valid?1.:0.);}
'''
    cases=[]
    for slope in (-.5,-.31,-.08,-.02,0.,.02,.08,.31,.5):
        for z in (-.4,0.,.4):
            length=math.sqrt(1+slope*slope+z*z)
            for depth in (0.,2**-24,.125,.5,f32(1-2**-24)):
                cases.append(tuple(map(f32,(slope/length,1/length,z/length,depth))))
    reports=[]
    for storage in (0,1):
        options=dict(OPTIONS)
        fmt='RGBA8' if storage==0 else 'RGBA16'
        pair=runner.pair('composite',options,caustic_test_source(source,storage))
        packed=runner.render('actual '+fmt+' packing',pair,len(cases),1,[('inputs',[cases],'RGBA32F')],storage=fmt)
        unpacked=runner.render('actual '+fmt+' unpacking',runner.pair('composite',options,caustic_test_source(decoder,storage)),len(cases),1,
                               [('records',packed,fmt),('depths',[[ (v[3],0,0,1) for v in cases]],'R32F')])
        maximum=0.
        for original,pixel in zip(cases,unpacked[0]):
            require(pixel[3]==1,fmt+': valid quantized record rejected')
            error=max(abs(a-b) for a,b in zip(pixel[:3],original[:3]));maximum=max(maximum,error)
            require(error<(.003 if storage==0 else .000015),fmt+': normal quantization exceeded bound')
        bad=[[(0,0,0,0)]*len(cases)]
        rejected=runner.render('invalid '+fmt,runner.pair('composite',options,caustic_test_source(decoder,storage)),len(cases),1,
                               [('records',bad,fmt),('depths',[[ (v[3],0,0,1) for v in cases]],'R32F')])
        require(all(p==(0,0,0,0) for p in rejected[0]),'clear code did not reject')
        length=math.sqrt(1+.51*.51)
        invalid=[(.51/length,1/length,0.,.5),(0.,0.,0.,.5),(0.,-1.,0.,.5),
                 (math.nan,1.,0.,.5),(0.,1.,0.,math.inf),(0.,1.,0.,1.)]
        rejected=runner.render('overflow and invalid '+fmt,pair,len(invalid),1,[('inputs',[invalid],'RGBA32F')],storage=fmt)
        require(all(p==(0,0,0,0) for p in rejected[0]),'invalid normal/depth was packed')
        reports.append(dict(format=fmt,samples=len(cases),invalid_samples=len(invalid),max_normal_component_error=maximum,
                            nominal_double_buffer_mib_2048=32 if storage==0 else 64))
    return reports


def depth_storage_tests(runner):
    probe='#version 330 compatibility\nuniform float testDepth;layout(location=0) out vec4 result;\nvoid main(){gl_FragDepth=testDepth;result=vec4(testDepth,0,0,1); }\n'
    result=runner.call('--depth-storage-check',*runner.pair('composite',wrapper=probe))
    values=result['depth_storage']
    bad=probe.replace('gl_FragDepth=testDepth','gl_FragDepth=0.0')
    runner.call('--depth-storage-check',*runner.pair('composite',wrapper=bad),expected_failure='depth storage comparison')
    prefix='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics_packing.glsl')
    encode=prefix+'''
uniform sampler2D sourceDepth;
layout(location=0) out vec4 result;
void main(){result=encodeWaterCaustic(vec3(0,1,0),texelFetch(sourceDepth,ivec2(gl_FragCoord.xy),0).r);}
'''
    decode=prefix+'''
uniform sampler2D records,actualDepth;
layout(location=0) out vec4 result;
void main(){ivec2 p=ivec2(gl_FragCoord.xy);vec3 n;
 bool valid=decodeWaterCaustic(texelFetch(records,p,0),texelFetch(actualDepth,p,0).r,n);result=vec4(n,valid?1.:0.);}
'''
    assessment=[]
    for storage in (0,1):
        fmt='RGBA8' if storage==0 else 'RGBA16';options=dict(OPTIONS)
        records=runner.render('depth source '+fmt,runner.pair('composite',options,caustic_test_source(encode,storage)),len(values),1,
            [('sourceDepth',[[(v['source'],0,0,1) for v in values]],'R32F')],storage=fmt)
        pairs=runner.pair('composite',options,caustic_test_source(decode,storage))
        image=runner.render('depth actual '+fmt,pairs,len(values),1,
            [('records',records,fmt),('actualDepth',[[(v['stored'],0,0,1) for v in values]],'R32F')])
        accepted=sum(p[3]==1 for p in image[0])
        if storage==1:require(accepted==len(values),'RGBA16 ownership rejected a real D24/D32F write')
        for v,pixel in zip(values,image[0]):
            require(pixel in ((0,1,0,1),(0,0,0,0)),'depth acceptance has invalid normal/code')
            if v['format']=='D32F':require(pixel[3]==1,'exact D32F source did not match')
        wrong=runner.render('depth mismatch '+fmt,pairs,len(values),1,
            [('records',records,fmt),('actualDepth',[[(v['stored']+4/65534,0,0,1) for v in values]],'R32F')])
        require(all(p==(0,0,0,0) for p in wrong[0]),'unrelated depth was accepted')
        assessment.append(dict(format=fmt,accepted=accepted,rejected_boundary_bins=len(values)-accepted,
                               unrelated_depth_rejections=len(values)))
    return dict(native_values=values,packed_ownership=assessment,negative_harness_control=True,
                scope='Actual depth-attachment D24/D32F writes/readback followed by real packed shader decoding')


def timed_repeat(runner):
    manifest=runner.last_manifest
    output=runner.last_output
    timed_output=output.with_name(output.stem+'-timed.raw')
    timed_manifest=manifest.with_name(manifest.stem+'-timed.txt')
    text=manifest.read_text(encoding='utf-8').replace(str(output).replace('\\','/'),str(timed_output).replace('\\','/'))
    require(text!=manifest.read_text(encoding='utf-8'),'Timing output path substitution failed')
    write_text(timed_manifest,text)
    result=runner.call('--time-render',timed_manifest)
    samples=result.get('gpu_nanoseconds',[])
    require(len(samples)==25 and all(x>0 for x in samples),'Invalid native timing samples')
    require(timed_output.read_bytes()==output.read_bytes(),'Timed draw changed deterministic output')
    return samples


def benchmark_tests(runner):
    width,height,shadow_size=512,288,2048
    scene=slab_scene(width=width,height=height,depth=2.,pitch=65.,share=.65)
    scene['textures']['colortex1']=[[(.5+.5*scene['up'][0],.5+.5*scene['up'][1],
                                    .5+.5*scene['up'][2],1.)]*width for _ in range(height)]
    # This authored normal field is constant along Z: repeated immutable rows
    # avoid constructing millions of duplicate Python tuples. The driver still
    # allocates/uploads all three actual2048x2048 texture images.
    row=[encode_cpu(normal_at(16*((x+.5)/shadow_size-.5),.08),.5625,1) for x in range(shadow_size)]
    shadow=[('shadowcolor0',[row]*shadow_size,'RGBA16'),
            ('shadowtex0',[[(.5625,0,0,1)]*shadow_size]*shadow_size,'R32F'),
            ('shadowtex1',[[(.59375,0,0,1)]*shadow_size]*shadow_size,'R32F')]
    formats=dict(FORMATS,colortex0='RGBA16F',colortex1='RGBA16')
    textures=[(name,image,formats[name]) for name,image in scene['textures'].items()]+shadow
    uniforms=scene['uniforms']+shadow_uniforms()
    optional=[n for n,_,_ in textures]+[n for n,_,_ in uniforms]
    results=[];images=[]
    for enabled in (0,1):
        pair=runner.pair('composite',dict(BASE_OPTIONS,**dict(OPTIONS,WATER_CAUSTICS=enabled)))
        image=runner.render('M4 GPU cost '+str(enabled),pair,width,height,textures,uniforms,
                            storage='RGBA16F',optional=optional)
        samples=timed_repeat(runner);values=sorted(samples)
        median=values[len(values)//2]/1e6
        results.append(dict(caustics=enabled,samples_ms=[v/1e6 for v in samples],
                            minimum_ms=values[0]/1e6,median_ms=median,p95_ms=values[23]/1e6))
        images.append(image)
    changed=sum(a[:3]!=b[:3] for ar,br in zip(images[0],images[1]) for a,b in zip(ar,br))
    require(changed>width*height//2,'timed caustics draw did not exercise active optics')
    require(all(a[3]==b[3] for ar,br in zip(images[0],images[1]) for a,b in zip(ar,br)),
            'timed caustics draw changed alpha')
    return dict(output_size=[width,height],shadow_size=[shadow_size,shadow_size],warmups=6,samples=25,
                passes=results,incremental_median_ms=results[1]['median_ms']-results[0]['median_ms'],
                changed_pixels=changed,max_caustic_texture_fetches=109,
                scope='GL_TIME_ELAPSED around the actual full composite draw after warmup; authored water-only fixture, fog/SSR disabled; texture upload/readback excluded. Not Minecraft FPS or an1080p extrapolation.')



def combined_scene():
    scene=slab_scene(128,72,2.,65.,block=.5)
    w,h=scene['width'],scene['height']
    scene['textures']['colortex1']=[[(.5+.5*scene['up'][0],.5+.5*scene['up'][1],
                                      .5+.5*scene['up'][2],1.)]*w for _ in range(h)]
    # Binary fractions stay exact in R16F and distinguish the receiver from the
    # screen source. Never compare an oracle to a source-pixel substituted q.
    scene['textures']['colortex9']=[[(float((3*x+5*y)%15+1)/16,0,0,1) for x in range(w)] for y in range(h)]
    return scene


def combined_render(runner,scene,mode,enabled,wrapper=None):
    options=dict(BASE_OPTIONS,**dict(OPTIONS,WATER_CAUSTICS=enabled,WATER_REFRACTION=mode))
    textures=[(n,image,FORMATS.get(n,'RGBA32F')) for n,image in scene['textures'].items()]+shadow_scene(2.,.08,-4.)
    uniforms=scene['uniforms']+shadow_uniforms()
    optional=[n for n,_,_ in textures]+[n for n,_,_ in uniforms]
    return runner.render('M3 x M4 mode {} caustics {}'.format(mode,enabled),
        runner.pair('composite',options,wrapper),scene['width'],scene['height'],textures,uniforms,optional=optional)


def analytic_refracted_sample(scene,x,y,ior):
    from validate_gpu_water_refraction import refract
    front=scene['front'][y][x];length=math.sqrt(sum(v*v for v in front))
    direction=refract(tuple(v/length for v in front),scene['up'],1.,ior)
    distance=(-6.-sum(a*b for a,b in zip(front,scene['up'])))/sum(a*b for a,b in zip(direction,scene['up']))
    point=tuple(a+b*distance for a,b in zip(front,direction))
    projection=next(v for n,k,v in scene['uniforms'] if n=='gbufferProjection')
    px=(projection[0]*point[0]/-point[2]*.5+.5)*scene['width']
    py=(projection[5]*point[1]/-point[2]*.5+.5)*scene['height']
    if min(px,py,scene['width']-px,scene['height']-py)<=9:return None
    if min(px%1,py%1,1-px%1,1-py%1)<.035:return None
    tx,ty=int(px),int(py)
    world=tuple(sum(scene['model'][r][c]*point[c] for c in range(3)) for r in range(3))
    entry=world[0]
    # Independent analytic Newton inversion, not the four-step sampled GPU map.
    for _ in range(30):
        e=map_analytic(entry,2.,.08,ior)-world[0];h=1e-5
        derivative=(map_analytic(entry+h,2.,.08,ior)-map_analytic(entry-h,2.,.08,ior))/(2*h)
        entry-=e/derivative
    span=receiver_pixel_span(point,scene)
    gain,_=finite_area_truth(entry,2.,.08,max(.10,.5*span),ior)
    gain=1+(gain-1)*(1-smooth(.25,.5,span/(128/math.hypot(151,97))))
    source=scene['textures']['colortex5'][ty][tx][:3];share=scene['textures']['colortex9'][ty][tx][0]
    levels=scene['textures']['colortex8'][y][x]
    radiance=analytical_transport(source,share,distance,2.,levels[1],levels[2],(0,0,0))
    delta=tuple(c*share*(gain-1)*math.exp(-(distance+2.)*ext) for c,ext in zip(source,(.192,.075,.05)))
    return dict(target=(tx,ty),point=point,distance=distance,share=share,gain=gain,
                radiance=radiance,with_caustics=tuple(a+b for a,b in zip(radiance,delta)))


def combined_tests(runner):
    scene=combined_scene();images={};combos=[]
    for mode in (0,2):
        for enabled in (0,1):
            image=combined_render(runner,scene,mode,enabled);images[mode,enabled]=image
            require(all(math.isfinite(c) for row in image for p in row for c in p),'nonfinite combined output')
            require(all(p[3]==q[3] for row,orig in zip(image,scene['textures']['colortex0']) for p,q in zip(row,orig)),
                    'combined native alpha changed')
            combos.append(dict(refraction=mode,caustics=enabled,pixels=scene['width']*scene['height']))
        require(any(a[:3]!=b[:3] for row,old in zip(images[mode,1],images[mode,0]) for a,b in zip(row,old)),
                'combination caustics was visually inactive')
    # Independent plane intersections and analytic normal field. Interior queries
    # have unit trace confidence; this is checked indirectly against full RGB truth.
    queries=[];max_error=0;different=0
    for x,y in ((x,y) for y in (28,32,36,40,44) for x in (48,56,64,72,80)):
        truth=analytic_refracted_sample(scene,x,y,1.333)
        if truth is None:continue
        tx,ty=truth['target']
        if max(abs(tx-x),abs(ty-y))<=1:continue
        # This fixture is well inside the outer coverage/range/neighbor fades.
        for enabled,key in ((0,'radiance'),(1,'with_caustics')):
            expected=truth[key];actual=images[2,enabled][y][x][:3]
            error=max(abs(a-b) for a,b in zip(actual,expected));max_error=max(error,max_error)
            require(error<.0004,'M3/M4 true receiver mismatch '+str((x,y,enabled,truth,error,actual)))
        different+=truth['share']!=scene['textures']['colortex9'][y][x][0]
        queries.append(dict(source=[x,y],target=[tx,ty],gain=truth['gain'],target_q=truth['share']))
    require(len(queries)>=12 and different>=10,'Insufficient displaced target coverage')
    selected=next(q for q in queries if q['target_q']!=scene['textures']['colortex9'][q['source'][1]][q['source'][0]][0])
    x,y=selected['source'];tx,ty=selected['target']
    source_change=copy.deepcopy(scene)
    source_change['textures']['colortex9'][y][x]=(0.,0.,0.,1.)
    source_change['textures']['colortex1'][y][x]=(1.,.5,.5,1.)
    source_result=combined_render(runner,source_change,2,1)
    source_error=max(abs(a-b) for a,b in zip(source_result[y][x],images[2,1][y][x]))
    require(source_error<=2e-7,'Traced receiver borrowed source q or normal')
    target_zero=copy.deepcopy(scene);target_zero['textures']['colortex9'][ty][tx]=(0.,0.,0.,1.)
    a=combined_render(runner,target_zero,2,0);b=combined_render(runner,target_zero,2,1)
    require(a[y][x]==b[y][x],'Target-only q zero failed exact caustic neutrality')
    # Three independent channel endpoints / IORs, each tested against its own
    # sampled receiver q and caustic analytic mapping rather than the green ray.
    dispersed=combined_render(runner,scene,3,1);spectral=0;max_spectral=0
    for q in queries:
        x,y=q['source'];truths=[analytic_refracted_sample(scene,x,y,ior) for ior in (1.331667825,1.334682548,1.339607890)]
        if any(t is None for t in truths):continue
        expected=tuple(t['with_caustics'][c] for c,t in enumerate(truths))
        error=max(abs(a-b) for a,b in zip(dispersed[y][x][:3],expected));max_spectral=max(max_spectral,error)
        require(error<.00045,'Dispersive caustic receiver mismatch '+str((x,y,error)))
        spectral+=1
    require(spectral>=8,'Insufficient spectral receiver checks')
    return dict(combinations=combos,analytic_queries=queries,
        max_receiver_rgb_error=max_error,source_target_q_differences=different,
        source_only_change_error=source_error,target_q_zero_exact=True,
        spectral_queries=spectral,max_spectral_rgb_error=max_spectral)


def caustics_tests(runner,plate=None):
    result={}
    for name,fn in (('depth_storage',depth_storage_tests),('packing',packing_tests),('capture',capture_tests),
                    ('core',core_tests),('transport',transport_tests),('footprint',footprint_tests),
                    ('composite',lambda r: integrated_tests(r,plate)),('combined_refraction',combined_tests)):
        result[name]=fn(runner);print('PASS caustics '+name,flush=True)
    result['memory_mib_at_2048_double_side']={'RGBA8':32,'RGBA16_UNORM_selected':64,'RGBA32F_reference_only':128}
    result['scope']='Native synthetic inputs; no Minecraft/Iris runtime or full path-traced volume claim'
    return result


def wave_capture_views(runner,plate):
    from render_water_bench import display_rows,draw_text,png
    w,h,side=192,104,256
    depth=3.
    scene=slab_scene(w,h,depth=depth,pitch=75.,share=.90,source_rgb=(.83,.74,.53))
    # A continuous sandy floor makes light redistribution visible without edges
    # from the checker pattern used by the numerical regression.
    for row in scene['textures']['colortex5']:
        row[:]=[(.83,.74,.53,1.)]*w
    normal=tuple(.5+.5*v for v in scene['up'])+(1.,)
    scene['textures']['colortex1']=[[normal]*w for _ in range(h)]
    v=runner.scratch/'caustic-surface-plane.vert'
    write_text(v,'''#version 330 compatibility
out vec2 texcoord;
out vec4 glcolor;
out vec3 causticPlayerPosition,causticNormalWorld;
flat out int causticWaterMaterial;
void main(){
    gl_Position=vec4(gl_Vertex.xy,0.125,1);
    causticPlayerPosition=vec3(8.0*gl_Vertex.x,-4.0,-8.0*gl_Vertex.y);
    causticNormalWorld=vec3(0,1,0);
    causticWaterMaterial=1;texcoord=gl_MultiTexCoord0.xy;glcolor=vec4(1);
}''')
    opt=dict(BASE_OPTIONS,**OPTIONS)
    capture_uniforms=[('cameraPositionInt','i3',(0,68,0)),('cameraPositionFract','f3',(0.,0.,0.)),
                      ('gbufferModelView','m4',matrix_uniform(IDENTITY4)),
                      ('gbufferModelViewInverse','m4',matrix_uniform(IDENTITY4))]
    textures=[(n,image,FORMATS.get(n,'RGBA16')) for n,image in scene['textures'].items()]
    uniforms=scene['uniforms']+shadow_uniforms()
    rows=[]
    for seconds in (17.,19.):
        capture=runner.render('wave normal + depth capture',(v,runner.pair('shadow',opt)[1]),side,side,
            [('gtexture',[[(1.,1.,1.,1.)]],'RGBA8')],capture_uniforms+[('frameTimeCounter','f1',(seconds,))],
            storage='RGBA16',optional=[u[0] for u in capture_uniforms])
        shadow=[('shadowcolor0',capture,'RGBA16'),
                ('shadowtex0',[[((.5625),0.,0.,1.)]*side]*side,'R32F'),
                ('shadowtex1',[[((.5+(4.+depth)/64.),0.,0.,1.)]*side]*side,'R32F')]
        for active in ((0,1) if not rows else (1,)):
            options=dict(opt,WATER_CAUSTICS=active)
            rgb=runner.render('caustics on actual W2 waves',runner.pair('composite',options),w,h,textures+shadow,uniforms,
                              optional=[t[0] for t in textures+shadow+uniforms])
            display=runner.render('wave caustics final',runner.pair('final'),w,h,[('colortex0',rgb,'RGBA32F')])
            rows.append(display_rows(display))
    changes=[]
    for a,b in ((0,1),(1,2)):
        differences=[max(abs(p-q) for p,q in zip(left,right)) for ar,br in zip(rows[a],rows[b]) for left,right in zip(ar,br)]
        require(sum(v>=2 for v in differences)>w*h*.05,'Missing visible 2D time-dependent caustics')
        changes.append(dict(visible=sum(v>=2 for v in differences),maximum=max(differences)))
    if plate:
        sheet=[[(14,19,24)]*(w*3) for _ in range(h+22)]
        for n,title in enumerate(('OFF / SAME SAND','SUNLIT BED / T=17 S','SAME VIEW / T=19 S')):
            draw_text(sheet,n*w+3,6,title)
            for y,row in enumerate(rows[n]):sheet[y+22][n*w:(n+1)*w]=row
        png(plate,sheet)
    return dict(size=[w,h],depth_metres=depth,display_differences=changes,shadow_capture='production shadow fragment with classified top-face fixture')
