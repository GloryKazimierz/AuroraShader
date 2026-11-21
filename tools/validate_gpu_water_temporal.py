"""K water-only unjittered history: native image/metadata feedback tests."""
import json,math,tempfile
from pathlib import Path

def temporal_scene(width=16,height=12):
    from validate_gpu_water_transport import slab_scene
    from validate_water_depth import inverse_matrix
    from validate_gpu_depth import matrix_uniform
    from validate_water_waves import f32
    data=slab_scene(width,height)
    uniforms={n:(n,k,v) for n,k,v in data['uniforms']}
    uniforms.update(gbufferPreviousProjection=uniforms['gbufferProjection'],gbufferPreviousModelView=('gbufferPreviousModelView','m4',matrix_uniform(inverse_matrix(data['model']))))
    uniforms['gbufferPreviousProjection']=('gbufferPreviousProjection','m4',uniforms['gbufferProjection'][2])
    uniforms.update(previousCameraPositionInt=('previousCameraPositionInt','i3',(0,68,0)),
        previousCameraPositionFract=('previousCameraPositionFract','f3',(0.,0.,0.)),
        frameCounter=('frameCounter','i1',(200,)),frameTime=('frameTime','f1',(f32(1/60),)),
        frameTimeCounter=('frameTimeCounter','f1',(f32(17+1/60),)),
        currentDate=('currentDate','i3',(2026,11,21)),currentTime=('currentTime','i3',(12,0,17)))
    data['uniforms']=list(uniforms.values())
    texture=data['textures']
    texture['colortex3']=[[(2.,1.,.5,1.)]*max(1,width//2) for _ in range(max(1,height//2))]
    texture['colortex12']=[[(f32(.3),f32(.4),f32(.2),texture['colortex7'][y][x][3]) for x in range(width)] for y in range(height)]
    texture['colortex12'][0][0]=(200.,float(width),float(height),1.)
    texture['colortex12'][0][1]=(17.,43217.,float(2026*372+11*31+21),1.)
    for y in range(height):
        for x in range(width):
            noise=.01 if (x+y)%2 else -.01
            texture['colortex0'][y][x]=tuple(f32(v+noise) for v in (.3,.4,.2))+(texture['colortex0'][y][x][3],)
            if x>=width-3:texture['colortex8'][y][x]=(0,0,0,0)
    return data

def draw_temporal(runner,data,options=None,history=False,label='K temporal'):
    from validate_gpu_water_transport import FORMATS
    settings=dict(WATER_OPTICS=1,WATER_TEMPORAL=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True)
    settings.update(options or {})
    names=('colortex0','colortex3','colortex7','colortex8','colortex12','depthtex0')
    formats=dict(FORMATS,colortex3='RGBA16F',colortex12='RGBA32F')
    textures=[(n,data['textures'][n],formats[n]) for n in names]
    pair=runner.pair('composite5',settings)
    return runner.render(label,pair,data['width'],data['height'],textures,data['uniforms'],
        optional=list(names)+[u[0] for u in data['uniforms']],extra_targets=((1,1,'RGBA32F'),),read_target=1 if history else 0)

def smoke_tests(runner):
    from validate_gpu import compare,require
    from validate_water_waves import f32
    data=temporal_scene();image=draw_temporal(runner,data);stored=draw_temporal(runner,data,history=True)
    expected=[];records=[];changed=0;weight=math.exp(-f32(1/60)/.08)
    for y in range(data['height']):
        row=[]
        for x in range(data['width']):
            old=data['textures']['colortex0'][y][x];active=x<data['width']-3 and not(y==0 and x<2)
            filtered=tuple(old[i]*(1-weight)+f32(v)*weight for i,v in enumerate((.3,.4,.2))) if active else old[:3]
            row.append(tuple(filtered[i]+.08*g for i,g in enumerate((2.,1.,.5)))+(old[3],))
            if active:
                require(stored[y][x][3]==data['textures']['colortex7'][y][x][3],'K historical full depth changed')
                for a,b in zip(stored[y][x][:3],filtered):require(abs(a-b)<2e-6,'K stored bloom or wrong filtered color')
                changed+=1
            elif not(y==0 and x<2):require(stored[y][x]==(0,0,0,2),'K nonwater wrote valid history')
        expected.append(row)
    result=compare(image,expected,'Actual recombine: filter water before adding current bloom once',absolute=2e-6,relative=1e-6)
    require(stored[0][0]==(201.,16.,12.,1.),'K frame/viewport header differs')
    require(stored[0][1]==(f32(17+1/60),43217.,float(2026*372+11*31+21),1.),'K clock header differs')
    require(changed>100,'K smoke has insufficient active water')
    return dict(active_pixels=changed,comparison=result,raw_depth_exact=True,history_excludes_bloom=True)


def set_uniform(scene,name,kind,value):
    scene['uniforms']=[u for u in scene['uniforms'] if u[0]!=name]+[(name,kind,value)]

def unbloomed(scene):
    return scene['textures']['colortex0']

def reset_tests(runner):
    """Each reset returns the exact current frame, not a soft comparison."""
    from copy import deepcopy
    from validate_gpu import compare,require
    base=temporal_scene();cases=[]
    def changed(label,edit):
        scene=deepcopy(base);edit(scene);cases.append((label,scene))
    def header(scene,which,channel,value):
        v=list(scene['textures']['colortex12'][0][which]);v[channel]=value
        scene['textures']['colortex12'][0][which]=tuple(v)
    def fill(scene,name,edit):
        scene['textures'][name]=[[edit(v) for v in row] for row in scene['textures'][name]]
    changed('cleared allocation',lambda d:fill(d,'colortex12',lambda v:(0,0,0,0)))
    changed('skipped frame',lambda d:header(d,0,0,199))
    changed('duplicate frame',lambda d:header(d,0,0,201))
    changed('changed dimensions',lambda d:header(d,0,1,15))
    changed('medium changed',lambda d:header(d,0,3,5))
    changed('stale timer',lambda d:header(d,1,0,16.9))
    changed('cached dimension same numeric frame and timer but old wall time',lambda d:header(d,1,1,43214))
    changed('different date',lambda d:header(d,1,2,2026*372+11*31+20))
    changed('clock moved backwards',lambda d:header(d,1,1,43218))
    changed('new dimension timer warmup',lambda d:set_uniform(d,'frameTimeCounter','f1',(1.,)))
    changed('frame time spike',lambda d:set_uniform(d,'frameTime','f1',(.2,)))
    changed('camera teleport',lambda d:set_uniform(d,'cameraPositionInt','i3',(5,68,0)))
    changed('blindness',lambda d:set_uniform(d,'blindness','f1',(.5,)))
    changed('darkness',lambda d:set_uniform(d,'darknessFactor','f1',(.5,)))
    changed('ceiling dimension',lambda d:set_uniform(d,'hasCeiling','i1',(1,)))
    changed('multiple water layers',lambda d:fill(d,'colortex8',lambda v:(2/255,v[1],v[2],v[3])))
    changed('foreground covered interface',lambda d:fill(d,'depthtex0',lambda v:(v[0]-.001,0,0,1)))
    changed('previous foreground occlusion',lambda d:fill(d,'colortex12',lambda v:v if v[3]>=1 else v[:3]+(v[3]-.001,)))
    changed('previous opposite interface side',lambda d:fill(d,'colortex12',lambda v:v if v[3]>=1 else v[:3]+(-v[3],)))
    changed('previous nonfinite radiance',lambda d:fill(d,'colortex12',lambda v:v if v[3]>=1 else (float('nan'),v[1],v[2],v[3])))
    changed('previous invalid current water ownership',lambda d:fill(d,'colortex8',lambda v:(1,0,0,0)))
    def fov(d):
        for name,kind,value in d['uniforms']:
            if name=='gbufferPreviousProjection':
                values=list(value);values[0]*=1.01;set_uniform(d,name,kind,tuple(values));break
    changed('projection changed',fov)
    def turn(d):
        from validate_gpu_depth import matrix_uniform
        from validate_water_depth import inverse_matrix
        m=[list(row) for row in inverse_matrix(d['model'])]
        for row in m:
            row[0]=-row[0];row[2]=-row[2]
        set_uniform(d,'gbufferPreviousModelView','m4',matrix_uniform(m))
    changed('camera rotation cut',turn)
    reports=[]
    for label,data in cases:
        native=draw_temporal(runner,data,{'WATER_TEMPORAL':0},label=label+' off')
        actual=draw_temporal(runner,data,label=label)
        reports.append(compare(actual,native,label))
    # All inactive compile gates must also preserve actual current+bloom behavior.
    for label,option in [('option off',{'WATER_TEMPORAL':0}),('optics off',{'WATER_OPTICS':0}),
                         ('no capability',{'IRIS_FEATURE_PER_BUFFER_BLENDING':False}),
                         ('legacy',{'SCENE_COLOR_MODE':0}),('debug',{'DEBUG_VIEW':8}),('style off',{'WATER_STYLE':0})]:
        actual=draw_temporal(runner,base,option,label=label)
        expected=draw_temporal(runner,base,dict(option,WATER_TEMPORAL=0),label=label+' baseline')
        reports.append(compare(actual,expected,label))
    print('PASS: K exact reset and bypass controls',len(reports),flush=True)
    return reports


def filter_rgb(current,history,neighbors,dt=1/60):
    """Scalar mathematical filter oracle, independent of shader plumbing."""
    clamped=tuple(max(min(p[c] for p in neighbors+[current]),min(max(p[c] for p in neighbors+[current]),history[c])) for c in range(3))
    change=max(abs(a-b)/max(a,b,.05) for a,b in zip(clamped,current))
    t=max(0.,min(1.,(change-.1)/.2));weight=min(.9,math.exp(-dt/.08))*(1-t*t*(3-2*t))
    return tuple(c+(h-c)*weight for c,h in zip(current,clamped))


def reprojection_tests(runner):
    """Positive XY camera translation and yaw sample a world-space field."""
    from copy import deepcopy
    from validate_gpu import compare,require
    from validate_water_depth import inverse_matrix
    from validate_gpu_depth import matrix_uniform
    from validate_water_waves import f32
    reports=[]
    for label,dx,yaw in [('lateral movement',.147,0.),('small yaw',0.,4.),('combined movement and yaw',.147,4.)]:
        data=temporal_scene(32,24);w,h=data['width'],data['height'];tex=data['textures']
        uniforms={n:v for n,k,v in data['uniforms']}
        # Authored field on a horizontal plane. Previous camera yaw changes world
        # x/z, while every ray intersects the SAME physical Y=-4 plane.
        angle=math.radians(yaw);c,s=math.cos(angle),math.sin(angle)
        rotate=((c,0,s,0),(0,1,0,0),(-s,0,c,0),(0,0,0,1))
        old_model=tuple(tuple(sum(rotate[r][k]*data['model'][k][col] for k in range(4)) for col in range(4)) for r in range(4))
        old_view=inverse_matrix(old_model)
        set_uniform(data,'gbufferPreviousModelView','m4',matrix_uniform(old_view))
        set_uniform(data,'cameraPositionFract','f3',(dx,0,0))
        def field(point):return (.30+.005*point[0],.40+.004*point[2],.20+.003*point[0])
        def world(m,p):return tuple(sum(m[r][k]*p[k] for k in range(3))+m[r][3] for r in range(3))
        for y in range(h):
            for x in range(w):
                oldworld=world(old_model,data['front'][y][x])
                currentworld=world(data['model'],data['front'][y][x]);currentworld=(currentworld[0]+dx,currentworld[1],currentworld[2])
                noise=.006 if (x+y)%2 else -.006
                tex['colortex0'][y][x]=tuple(f32(v+noise) for v in field(currentworld))+(tex['colortex0'][y][x][3],)
                if not(y==0 and x<2):tex['colortex12'][y][x]=tuple(f32(v) for v in field(oldworld))+(tex['colortex7'][y][x][3],)
        actual=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},label=label)
        projection=tuple(tuple(uniforms['gbufferProjection'][c*4+r] for c in range(4)) for r in range(4))
        expected=[];accepted=0;shifted=0
        for y in range(h):
            row=[]
            for x in range(w):
                current=tex['colortex0'][y][x];rgb=current[:3]
                if x<w-3 and not(y==0 and x<2):
                    p=world(data['model'],data['front'][y][x]);p=(p[0]+dx,p[1],p[2])
                    view=world(old_view,p);clip=tuple(sum(projection[r][k]*(view+(1,))[k] for k in range(4)) for r in range(4))
                    px=math.floor((clip[0]/clip[3]*.5+.5)*w);py=math.floor((clip[1]/clip[3]*.5+.5)*h)
                    if 0<=px<w and 0<=py<h and not(py==0 and px<2):
                        neighbors=[tex['colortex0'][ny][nx][:3] for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)) if 0<=nx<w-3 and 0<=ny<h and not(ny==0 and nx<2)]
                        rgb=filter_rgb(current[:3],tex['colortex12'][py][px][:3],neighbors,f32(1/60));accepted+=1;shifted+=(px,py)!=(x,y)
                row.append(rgb+(current[3],))
            expected.append(row)
        report=compare(actual,expected,label,absolute=4e-6,relative=2e-6)
        require(accepted>400 and shifted>100,'K reprojection fixture did not move enough samples')
        report.update(accepted=accepted,shifted=shifted);reports.append(report)
    print('PASS: K actual positive camera reprojection',flush=True)
    return reports


def highlight_tests(runner):
    from validate_gpu import compare,require
    data=temporal_scene();t=data['textures'];w,h=data['width'],data['height']
    for y in range(h):
        for x in range(w):
            current=(4.,3.,2.) if (x,y)==(7,6) else (.3,.4,.2)
            prior=(4.,3.,2.) if (x,y)==(6,6) else (.3,.4,.2)
            t['colortex0'][y][x]=current+(t['colortex0'][y][x][3],)
            if not(y==0 and x<2):t['colortex12'][y][x]=prior+(t['colortex7'][y][x][3],)
    actual=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},label='moving bright highlight')
    result=compare(actual,unbloomed(data),'No highlight trail or new-highlight lag',absolute=3e-7)
    # Adjacent highlight means a pure min/max clamp would retain the old bright
    # pixel. Verify this negative control numerically so the test cannot pass by
    # moving the bright feature outside the sampled neighborhood.
    dt=1/60;ghost_without_reactivity=.3+(4.-.3)*math.exp(-dt/.08)
    require(ghost_without_reactivity>3.,'K moving-highlight negative control failed')
    result['unreactive_old_pixel_red']=ghost_without_reactivity
    return result


def noise_tests(runner,panels=None):
    import random,statistics
    from validate_gpu import require
    from validate_water_waves import f32
    data=temporal_scene(24,16);w,h=data['width'],data['height'];rng=random.Random(1361)
    data['textures']['colortex12']=[[(0,0,0,0)]*w for _ in range(h)]
    errors=[];raw=[];alpha_exact=True
    for frame in range(18):
        timer=f32(17+(frame+1)*f32(1/60))
        set_uniform(data,'frameCounter','i1',(200+frame,));set_uniform(data,'frameTimeCounter','f1',(timer,))
        for y in range(h):
            for x in range(w):
                old=data['textures']['colortex0'][y][x];noise=rng.uniform(-.015,.015)
                data['textures']['colortex0'][y][x]=tuple(f32(c+noise) for c in (.3,.4,.2))+(old[3],)
        image=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},label='static feedback '+str(frame))
        stored=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},history=True,label='static stored '+str(frame))
        for y in range(h):
            for x in range(w):
                current=data['textures']['colortex0'][y][x];alpha_exact &= image[y][x][3]==current[3]
                if x<w-3 and not(y==0 and x<2):
                    require(stored[y][x][:3]==image[y][x][:3],'K feedback includes a second operation')
                    require(stored[y][x][3]==data['textures']['colortex7'][y][x][3],'K raw depth changed in feedback')
                    if frame>=6:
                        errors.append(image[y][x][0]-.3);raw.append(current[0]-.3)
                else:require(image[y][x]==current,'K nonwater or reserved color changed')
        data['textures']['colortex12']=stored
    filtered=math.sqrt(statistics.mean(e*e for e in errors));unfiltered=math.sqrt(statistics.mean(e*e for e in raw))
    require(filtered<unfiltered*.75,'K static noise reduction insufficient')
    require(alpha_exact,'K alpha changed')
    if panels is not None:panels.extend([('CURRENT NOISE',unbloomed(data)),('FILTERED',image),('8X DIFFERENCE',[[tuple(min(1.,abs(p[c]-q[c])*8) for c in range(3))+(1.,) for p,q in zip(a,b)] for a,b in zip(unbloomed(data),image)])])
    print('PASS: K static temporal noise RMS',filtered/unfiltered,flush=True)
    return dict(frames=18,measured_pixels=len(errors),current_rms=unfiltered,filtered_rms=filtered,
                rms_ratio=filtered/unfiltered,alpha_exact=alpha_exact,jitter=False)



def underwater_tests(runner):
    """Observed upward exit, sign-tagged history, no inferred invisible boundary."""
    from validate_gpu import compare,require
    from validate_gpu_depth import matrix_uniform
    from validate_water_depth import inverse_matrix
    from validate_water_waves import f32
    data=temporal_scene();t=data['textures'];w,h=data['width'],data['height']
    model=[list(row) for row in data['model']];model[1][2]*=-1;model[2][1]*=-1
    up=(0.,data['up'][1],-data['up'][2])
    set_uniform(data,'gbufferModelViewInverse','m4',matrix_uniform(model))
    set_uniform(data,'gbufferPreviousModelView','m4',matrix_uniform(inverse_matrix(model)))
    set_uniform(data,'upPosition','f3',up);set_uniform(data,'isEyeInWater','i1',(1,))
    depths=[list(row) for row in t['depthtex0']][::-1]
    for y in range(h):
        for x in range(w):
            depth=depths[y][x][0];t['colortex7'][y][x]=up+(depth,);t['depthtex0'][y][x]=(depth,0,0,1)
            v=t['colortex8'][y][x];t['colortex8'][y][x]=v[:3]+(f32(1/255),)
            if not(y==0 and x<2):t['colortex12'][y][x]=tuple(f32(c) for c in (.3,.4,.2))+(-depth,)
    t['colortex12'][0][0]=(200.,float(w),float(h),5.)
    actual=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},label='observed underwater exit')
    history=draw_temporal(runner,data,{'BLOOM_STRENGTH':0.0},history=True,label='signed underwater depth')
    expected=[];count=0;weight=math.exp(-f32(1/60)/.08)
    for y in range(h):
        row=[]
        for x in range(w):
            current=t['colortex0'][y][x];active=x<w-3 and not(y==0 and x<2)
            rgb=tuple(c+(f32(v)-c)*weight for c,v in zip(current[:3],(.3,.4,.2))) if active else current[:3]
            row.append(rgb+(current[3],))
            if active:require(history[y][x][3]==-t['depthtex0'][y][x][0],'Exit history lost exact depth/sign');count+=1
        expected.append(row)
    result=compare(actual,expected,'Observed underwater exit filtering',absolute=2e-6)
    require(count>100,'Insufficient observed underwater samples');result['exact_signed_depth_pixels']=count
    return result


def comparison_plate(panels,path):
    from render_water_bench import draw_text,png
    width,height=192,128
    rows=[[(16,22,28)]*(width*len(panels)) for _ in range(height+40)]
    draw_text(rows,4,5,'SYNTHETIC WATER HISTORY / NO GAME SCREENSHOT')
    for i,(label,image) in enumerate(panels):
        draw_text(rows,i*width+3,22,label)
        ih,iw=len(image),len(image[0])
        for y in range(height):
            rows[y+40][i*width:(i+1)*width]=[tuple(round(max(0.,min(1.,v))**(1/2.2)*255) for v in image[y*ih//height][x*iw//width][:3]) for x in range(width)]
    png(path,rows)

def temporal_tests(runner,plate=None):
    panels=[]
    report=dict(smoke=smoke_tests(runner),resets=reset_tests(runner),camera=reprojection_tests(runner),
                underwater=underwater_tests(runner),highlights=highlight_tests(runner),noise=noise_tests(runner,panels))
    if plate is not None:comparison_plate(panels,plate)
    return report

if __name__=='__main__':
    from compile_glsl import ROOT
    from validate_gpu import Runner,shader_digest,LIMIT
    before=shader_digest()
    with tempfile.TemporaryDirectory(prefix='native-water-K-',dir=ROOT.parent) as directory:
        runner=Runner(Path(directory),r'C:\msys64\ucrt64\bin\g++.exe')
        result=temporal_tests(runner);assert before==shader_digest()
        result.update(shader_digest=before,gl=runner.gl,limit=LIMIT)
        path=ROOT/'docs/validation/K_native.json';path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('PASS: K water-only temporal validation')
