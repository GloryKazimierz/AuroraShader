"""Actual composite1 restricted shallow-bed near-clip transport; synthetic scene, not game."""
import argparse,copy,json,math,shutil,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,expand
from validate_gpu import Runner,require,compare,write_text,shader_digest
from validate_gpu_water_nearclip import World,OPTIONS,capture,camera_uniforms,matrix_shadow,IDENTITY
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix,perspective_matrix,project_view,reconstruct_view
from nearclip_reference import f32,near_point,unit
from render_water_bench import png,draw_text
W,H=96,54
SETTINGS=dict(OPTIONS,WATER_REFRACTION=0,WATER_SCREEN_REFLECTIONS=0,WATER_UNDERWATER=0,
  WATER_FOAM=0,WATER_CELESTIAL_GLINT=0,FOG_ENABLED=0,WATER_CLARITY=1.0)
FORMATS=dict(colortex0="RGBA32F",colortex1="RGBA16",colortex5="RGBA16F",colortex6="R32F",colortex7="RGBA32F",
  colortex8="RGBA8",colortex9="R16F",depthtex0="R32F",depthtex1="R32F")

def scene(world,offset):
    eye,uniforms=camera_uniforms(world,offset,w=W,h=H)
    projection=perspective_matrix(50.,W/H,.05,128.);inverse=inverse_matrix(projection)
    textures={name:[] for name in FORMATS};positions=[]
    for y in range(H):
        rows={name:[] for name in textures};points=[]
        for x in range(W):
            near=near_point(eye,x,y,w=W,h=H);direction=unit(tuple(near[i]-eye[i] for i in range(3)))
            t=(world.bed-eye[1])/direction[1] if direction[1]<-.005 else -1
            valid=t>.05 and t<64
            bottom=tuple(eye[i]+direction[i]*t for i in range(3)) if valid else None
            valid=valid and all(abs(bottom[i])<24 for i in (0,2))
            if valid:
                v=tuple(bottom[i]-eye[i] for i in range(3));_,z=project_view(v,projection);z=f32(z)
                decoded=reconstruct_view(((x+.5)/W,(y+.5)/H),z,inverse)
                bottom=tuple(decoded[i]+eye[i] for i in range(3))
                checker=(math.floor(bottom[0]*6)+math.floor(bottom[2]*6))%2
                rgb=(.75,.5,.25) if checker else (.25,.375,.5)
            else:z=1.;rgb=(.375,.625,.875);bottom=None
            values=dict(colortex0=rgb+(.625,),colortex1=(.5,1.,.5,1.) if valid else (0,0,0,0),
              colortex5=rgb+(1.,) if valid else (0,0,0,0),colortex6=(z,0,0,1),colortex7=(0,0,0,0),
              colortex8=(0,0,0,0),colortex9=(.5 if valid else -1.,0,0,1),depthtex0=(z,0,0,1),depthtex1=(z,0,0,1))
            for name in rows:rows[name].append(values[name])
            points.append(bottom)
        for name in textures:textures[name].append(rows[name])
        positions.append(points)
    uniforms+=matrix_shadow(world)+[("gbufferProjection","m4",matrix_uniform(projection)),("upPosition","f3",(0,1,0)),
      ("shadowLightPosition","f3",world.light),("sunPosition","f3",world.light),("fogColor","f3",(.5,.6,.7)),
      ("hasSkylight","i1",(1,)),("hasCeiling","i1",(0,)),("isEyeInWater","i1",(1,)),
      ("blindness","f1",(0,)),("darknessFactor","f1",(0,)),("rainStrength","f1",(0,)),
      ("eyeBrightnessSmooth","i2",(240,240)),("cameraPositionInt","i3",(0,0,0)),("cameraPositionFract","f3",(0,0,0))]
    return dict(textures=textures,uniforms=uniforms,eye=eye,positions=positions)

def render(runner,data,shadow,options=None):
    textures=[(n,p,FORMATS[n]) for n,p in data['textures'].items()]+shadow
    pair=runner.pair('composite1',dict(SETTINGS,**(options or {})))
    return runner.render('actual composite restricted near-clip',pair,W,H,textures,data['uniforms'],
      optional=[n for n,_,_ in textures]+[n for n,_,_ in data['uniforms']])

def expected(rgb,view,light):
    # Independent analytical two-leg extinction and bounded local-radiance scatter.
    a=(.18,.055,.025);s=(.012,.020,.025);out=[]
    for i in range(3):
        t=math.exp(-(a[i]+s[i])*view);sun=math.exp(-(a[i]+s[i])*light)
        out.append(rgb[i]*(.5+.5*sun)*t+(1-t)*s[i]/(a[i]+s[i])*rgb[i]*.25)
    return tuple(out)

def tests(runner,plate):
    rows=[];panels=[];maximum=0.;total=0;first=None
    for depth,offset in ((.12,-.01),(.30,-.04),(.12,.01)):
        world=World(bed=8/9-depth);shadow,_=capture(runner,world);data=scene(world,offset)
        off=render(runner,data,shadow,dict(WATER_NEARCLIP=0));compare(off,data['textures']['colortex0'],'default off exact')
        on=render(runner,data,shadow);count=0;mask=[]
        for y in range(H):
            line=[]
            for x in range(W):
                p=on[y][x];native=off[y][x];require(p[3]==native[3],'Alpha changed')
                changed=p!=native;line.append((.05,.75,.25,1) if changed else (.08,.08,.08,1))
                if changed:
                    bottom=data['positions'][y][x];require(bottom is not None and offset<0,'Unowned source changed')
                    view=math.dist(bottom,data['eye']);light=(world.top-bottom[1])/math.sqrt(1-(1-world.light[1]**2)/(1.333**2))
                    truth=expected(data['textures']['colortex5'][y][x][:3],view,light)
                    error=max(abs(p[c]-truth[c]) for c in range(3));maximum=max(maximum,error)
                    require(error<2e-5,'Transport oracle mismatch:'+str((x,y,p,truth,error)))
                    require(view<=1.5 and view>.05 and .08<=world.top-bottom[1]<=.5,'Unbounded path accepted')
                    count+=1
            mask.append(line)
        require(count>100 if offset<0 else count==0,'Unexpected color coverage:'+str((depth,offset,count)))
        total+=count;rows.append(dict(depth_m=depth,eye_offset_m=offset,changed_pixels=count,total_pixels=W*H));panels.append((off,on,mask))
        if first is None:first=(data,shadow,on)
        print('scene',depth,offset,count,flush=True)
    data,shadow,baseline=first;negatives=[]
    for name,field,value in (('owner-overlay','colortex8',(1,0,0,0)),('owner-water','colortex8',(1/255,0,1,0)),
      ('existing-interface','colortex7',(0,1,0,.5)),('invalid-share','colortex9',(-1,0,0,1)),
      ('missing-snapshot','colortex5',(0,0,0,0)),('wrong-bottom-normal','colortex1',(1,.5,.5,1)),
      ('front-depth','depthtex0',(.2,0,0,1)),('unpaired-depth','colortex6',(.3,0,0,1))):
        broken=copy.deepcopy(data);broken['textures'][field]=[[value]*W for _ in range(H)]
        image=render(runner,broken,shadow);compare(image,data['textures']['colortex0'],name);negatives.append(name)
    for name,raw in (("zero-light",(0,0,0)),("nonfinite-light",(float("nan"),0,0))):
        broken=dict(data,uniforms=[(key,kind,raw if key=="shadowLightPosition" else value) for key,kind,value in data["uniforms"]]);compare(render(runner,broken,shadow),data["textures"]["colortex0"],name);negatives.append(name)
    missing=list(shadow);missing[0]=(shadow[0][0],[[(0,0,0,0)]*256 for _ in range(256)],shadow[0][2])
    compare(render(runner,data,missing),data['textures']['colortex0'],'missing-shadow');negatives.append('missing-shadow')
    # Compare display only; validation always uses the original linear float output.
    image=[];scale=3
    for row_index,strip in enumerate(panels):
        header=[[(24,27,33)]*(W*3*scale) for _ in range(14)]
        for index,label in enumerate(('NATIVE','FINITE WATER TRANSPORT','CHANGED MASK')):draw_text(header,index*W*scale+4,3,label)
        image.extend(header)
        for y in range(H-1,-1,-1):
            line=[]
            for field in strip:
                for p in field[y]:
                    rgb=tuple(round(max(0,min(1,v))**(1/2.2)*255) for v in p[:3]);line.extend([rgb]*scale)
            image.extend([line]*scale)
    png(plate,image)
    return dict(cases=rows,total_changed_pixels=total,max_linear_rgb_error=maximum,exact_negative_controls=negatives,
      limitations=['Synthetic paired opaque radiance/depth, actual production composite1 and shadow.fsh records.',
       'Only unbroken submerged camera-to-flat-bed paths, depth .08-.5m, path <=1.5m, max32 finite patch intervals.',
       'Crossing-interface and unknown pixels remain native; not a complete split-waterline solution.',
       'No extra unseen sky/lightmap is inferred; uses bounded source-radiance scatter with zero extra sky/block source.',
       'No Minecraft/Iris flip, depth-attachment or performance claim.'])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,default=Path('docs/validation/NEARCLIP_COLOR_GPU_01.json'));parser.add_argument('--plate',type=Path,default=Path('docs/validation/NEARCLIP_COLOR_GPU_01.png'));args=parser.parse_args()
    root=ROOT.resolve();target=(root/args.report).resolve();plate=(root/args.plate).resolve()
    require(root in target.parents and root in plate.parents,'Evidence must remain in D staging')
    require(not target.exists() and not plate.exists(),'New evidence required')
    scratch=Path(tempfile.mkdtemp(prefix='nearclip-color-',dir=root)).resolve();digest=shader_digest()
    try:
        runner=Runner(scratch,r'C:\msys64\ucrt64\bin\g++.exe');result=tests(runner,plate)
        require(shader_digest()==digest,'Source changed');write_text(target,json.dumps(dict(ok=True,shader_sha256=digest,gl=runner.gl,checks=result),indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        require(scratch.parent==root and scratch.name.startswith('nearclip-color-'),'Unsafe cleanup');shutil.rmtree(scratch)
if __name__=='__main__':main()
