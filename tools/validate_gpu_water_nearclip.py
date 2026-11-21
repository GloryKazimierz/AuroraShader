"""Native finite near-clip classifier using actual production shadow fragment records.
An isolated diagnostic entry, not a production optical replacement or game run.
"""
import argparse,json,math,shutil,struct,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,expand
from validate_gpu import Runner,require,write_text,shader_digest,compare
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix,perspective_matrix
from nearclip_reference import World,near_point,exact_water_length,f32,dot,unit
OPTIONS=dict(WATER_OPTICS=1,WATER_CAUSTICS=1,WATER_NEARCLIP=1,SHADOWS_ENABLED=True,
             IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_WAVES=0)
IDENTITY=tuple(tuple(float(i==j) for j in range(4)) for i in range(4))
VERTEX="""#version 330 compatibility
uniform vec3 lightRight,lightUp,lightToward,originalNormal;
uniform float shadowHalf,shadowRange,waterHeight;
uniform int material;
out vec2 texcoord;out vec4 glcolor;
out vec3 causticPlayerPosition,causticNormalWorld;
flat out int causticWaterMaterial;
void main(){
 vec3 base=lightRight*gl_Vertex.x*shadowHalf+lightUp*gl_Vertex.y*shadowHalf;
 vec3 p=base+lightToward*((waterHeight-base.y)/lightToward.y);
 float depth=.5-.5*dot(p,lightToward)/shadowRange;
 gl_Position=vec4(gl_Vertex.xy,depth*2.-1.,1.);
 texcoord=gl_Vertex.xy*.5+.5;glcolor=vec4(1);
 causticPlayerPosition=p;causticNormalWorld=originalNormal;causticWaterMaterial=material;
}
"""
DEPTH="""#version 330 compatibility
layout(location=0) out vec4 result;
void main(){result=vec4(gl_FragCoord.z,0,0,1);}
"""
MAIN="""
uniform sampler2D nativeColor,nativeOwner,nativeDepth;
uniform vec3 nearLight;
in vec2 texcoord;layout(location=0) out vec4 result;
void main(){
 ivec2 pixel=ivec2(gl_FragCoord.xy);result=texelFetch(nativeColor,pixel,0);
#ifdef AURORA_WATER_NEARCLIP_ACTIVE
 vec4 q=gbufferProjectionInverse*vec4(texcoord*2.0-1.0,-1.,1.);
 vec4 p=gbufferModelViewInverse*vec4(q.xyz/q.w,1.);
 vec3 eye=(gbufferModelViewInverse*vec4(0,0,0,1)).xyz;
 vec4 d=texelFetch(nativeDepth,pixel,0);
 WaterNearResult r=classifyWaterNearClip(eye,p.xyz/p.w,nearLight,texelFetch(nativeOwner,pixel,0),d.x,d.y,d.z);
 result=vec4(float(r.medium),r.waterLength,r.crossed?1.:0.,float(r.reason));
#endif
}
"""
def source():return "#version 330 compatibility\n"+expand(SHADERS/"lib/water_nearclip.glsl")+MAIN
def matrix_shadow(world):
    view=(world.right,world.vertical,tuple(-v for v in world.light))
    mv=tuple(tuple(view[r][c] if r<3 and c<3 else float(r==c==3) for c in range(4)) for r in range(4))
    proj=((1/world.half,0.,0.,0.),(0.,1/world.half,0.,0.),(0.,0.,1/world.range,0.),(0.,0.,0.,1.))
    return [(n,"m4",matrix_uniform(m)) for n,m in (("shadowModelView",mv),("shadowProjection",proj),
            ("shadowModelViewInverse",inverse_matrix(mv)),("shadowProjectionInverse",inverse_matrix(proj)))]
def capture(runner,world,waves=0,normal=(0,1,0)):
    vp=runner.scratch/("near-capture-"+str(runner.sequence)+".vert");write_text(vp,VERTEX)
    _,fs=runner.pair("shadow",dict(OPTIONS,WATER_WAVES=waves))
    uniforms=[("lightRight","f3",world.right),("lightUp","f3",world.vertical),("lightToward","f3",world.light),
      ("originalNormal","f3",normal),("shadowHalf","f1",[world.half]),("shadowRange","f1",[world.range]),
      ("waterHeight","f1",[world.top]),("material","i1",[1]),
      ("gbufferModelView","m4",matrix_uniform(IDENTITY)),("gbufferModelViewInverse","m4",matrix_uniform(IDENTITY)),
      ("cameraPositionInt","i3",[0,0,0]),("cameraPositionFract","f3",[0,0,0]),("frameTimeCounter","f1",[17.])]
    atlas=[];front=[];bed=[]
    for y in range(world.size):
        a=[];f=[];b=[]
        for x in range(world.size):
            rec,z,back=world.sample(x,y);a.append((1,1,1,1 if any(rec) else 0));f.append((z,0,0,1));b.append((back,0,0,1))
        atlas.append(a);front.append(f);bed.append(b)
    records=runner.render("actual shadow.fsh compact records",(vp,fs),world.size,world.size,
       [("gtexture",atlas,"RGBA32F")],uniforms,storage="RGBA16",optional=[v[0] for v in uniforms])
    _,depthfs=runner.pair("composite1",wrapper=DEPTH)
    raw=runner.render("same raster gl_FragCoord depth",(vp,depthfs),world.size,world.size,
        uniforms=uniforms,storage="R32F",optional=[v[0] for v in uniforms])
    active=0
    for y in range(world.size):
        for x in range(world.size):
            if atlas[y][x][3]:
                # Real fragment depth readback, then explicit normalized D24 quantization.
                z=f32(round(raw[y][x][0]*16777215)/16777215)
                front[y][x]=(z,0,0,1);active+=any(records[y][x])
    require(active>0 or normal[1]<.95,"Actual shadow producer inactive")
    return [("shadowcolor0",records,"RGBA16"),("shadowtex0",front,"R32F"),("shadowtex1",bed,"R32F")],active
def camera_uniforms(world,offset,pitch=0.,yaw=0.,fov=50.,near=.05,w=64,h=36):
    eye=(.017,world.top+offset,.027);a=math.radians(pitch);b=math.radians(yaw)
    right=(math.cos(b),0.,-math.sin(b))
    up=(math.sin(b)*-math.sin(a),math.cos(a),math.cos(b)*-math.sin(a))
    back=(math.sin(b)*math.cos(a),math.sin(a),math.cos(b)*math.cos(a))
    inverse=tuple(tuple((right,up,back)[c][r] if r<3 and c<3 else eye[r] if r<3 and c==3 else float(r==c==3)
                        for c in range(4)) for r in range(4))
    projection=perspective_matrix(fov,w/h,near,128.)
    return eye,[("gbufferModelViewInverse","m4",matrix_uniform(inverse)),
                ("gbufferProjectionInverse","m4",matrix_uniform(inverse_matrix(projection))),
                ("nearLight","f3",world.light)]
def render(runner,pair,world,shadow,offset=0.,owner=(0,0,0,0),depth=(.99,.99,.25,1),**camera):
    w,h=64,36;eye,uniforms=camera_uniforms(world,offset,**camera)
    native=[[(f32(.12),f32(.23),f32(.34),f32(.67))]*w for _ in range(h)]
    textures=shadow+[("nativeColor",native,"RGBA32F"),("nativeOwner",[[owner]*w for _ in range(h)],"RGBA8"),
                     ("nativeDepth",[[depth]*w for _ in range(h)],"RGBA32F")]
    uniforms+=matrix_shadow(world)
    image=runner.render("finite near clip",pair,w,h,textures,uniforms,
       optional=[n for n,_,_ in textures]+[n for n,_,_ in uniforms])
    return image,native,eye
def tests(runner,plate):
    pair=runner.pair("composite1",OPTIONS,source())
    report=[];accepted=0;crossings=0;maximum=0.;integrals=0;unstable=0;panels=[];positive_worlds=[]
    for light in ((.3,.9,.2),(.7,.5,.3),(.9,.2,.1)):
        world=World(light);shadow,active=capture(runner,world);positive_worlds.append((world,shadow))
        row=[]
        for offset in (-.04,-.01,0.,.01,.04):
            pixels,native,eye=render(runner,pair,world,shadow,offset)
            counts={0:0,1:0,2:0}
            for y,r in enumerate(pixels):
                for x,p in enumerate(r):
                    mode=int(p[0]);require(mode in counts and p[0]==mode,"Bad classification");counts[mode]+=1
                    if mode:
                        near=near_point(eye,x,y);truth=2 if near[1]<world.top else 1
                        require(mode==truth,"Wrong medium:"+str((light,offset,x,y,p,near)))
                        accepted+=1
                        if p[3]==0:
                            error=abs(p[1]-exact_water_length(eye,near,world.top));maximum=max(maximum,error)
                            require(error<.00025,"Near water integral exceeded optical error budget:"+str((light,offset,x,y,p,near,exact_water_length(eye,near,world.top),error)))
                            integrals+=1;crossings+=bool(p[2])
                        else:
                            require(p[3]==8 and p[1]==0 and p[2]==0,"Bad uncertain-integral output")
                            unstable+=1
            require(counts[1]+counts[2]>1000,"Insufficient finite coverage")
            if abs(offset)<=.01:require(counts[1] and counts[2],"No per-pixel split")
            report.append(dict(light=light,offset=offset,counts=counts,actual_capture_pixels=active));row.append(pixels)
        panels.append(row)
    world,shadow=positive_worlds[0];bypass=[]
    for name,options in (("default-off",dict(OPTIONS,WATER_NEARCLIP=0)),("no-caustics",dict(OPTIONS,WATER_CAUSTICS=0)),
       ("no-optics",dict(OPTIONS,WATER_OPTICS=0)),("no-capability",dict(OPTIONS,IRIS_FEATURE_PER_BUFFER_BLENDING=False))):
        output,native,_=render(runner,runner.pair("composite1",options,source()),world,shadow)
        compare(output,native,name);bypass.append(name)
    negatives=[]
    for name,owner,depth in (("native-overlay",(1,0,0,0),(.99,.99,.25,1)),
         ("native-water",(1/255,0,1,0),(.99,.99,.25,1)),("native-front",(0,0,0,0),(.98,.99,.25,1)),
         ("unknown-early-color",(0,0,0,0),(.99,.99,-1,1))):
        output,_,_=render(runner,pair,world,shadow,owner=owner,depth=depth)
        require(all(p[0]==0 for row in output for p in row),name+" accepted");negatives.append(name)
    # Actual production capture with filtered normals must not displace medium geometry.
    filtered,active=capture(runner,world,1)
    original,_,_=render(runner,pair,world,shadow)
    waves,_,_=render(runner,pair,world,filtered)
    compare(waves,original,"optical wave normals do not change geometry")
    # Actual bottom/side water records are rejected by the production producer itself.
    side,_=capture(runner,world,0,(1,0,0));output,_,_=render(runner,pair,world,side)
    require(all(p[0]==0 for row in output for p in row),"Side-face water was promoted to a top");negatives.append("actual-side-capture")
    from nearclip_reference import png
    palette={0:(51,54,60),1:(237,195,95),2:(39,127,194)};rows=[]
    for strip in panels:
        for y in range(35,-1,-1):
            row=[]
            for panel in strip:
                for p in panel[y]:row.extend([palette[int(p[0])]]*3)
            rows.extend([row]*3)
    png(plate,rows)
    return dict(cases=report,accepted_pixels=accepted,crossed_pixels=crossings,max_water_length_error_m=maximum,
        valid_integral_pixels=integrals,uncertain_integral_pixels=unstable,exact_bypasses=bypass,negative_controls=negatives,filtered_capture_same_geometry=True,
        depth_scope="Actual gl_FragCoord readback with explicit D24 quantization; no Iris depth attachment or texture-flip claim.",
        geometry_scope="Finite analytic source world; current native ownership/depth inputs are controlled fixture metadata. No optical color replacement implemented.")
def main():
    p=argparse.ArgumentParser();p.add_argument("--cxx",default=r"C:\msys64\ucrt64\bin\g++.exe");p.add_argument("--report",type=Path,required=True);p.add_argument("--plate",type=Path,required=True);args=p.parse_args()
    target=(ROOT/args.report).resolve();plate=(ROOT/args.plate).resolve()
    for path in (target,plate):require(ROOT.resolve() in path.parents and not path.exists(),"New local evidence required")
    scratch=Path(tempfile.mkdtemp(prefix="nearclip-native-",dir=ROOT)).resolve();digest=shader_digest()
    try:
        runner=Runner(scratch,args.cxx);result=tests(runner,plate);require(shader_digest()==digest,"Source changed")
        report=dict(ok=True,shader_sha256=digest,gl=runner.gl,checks=result,scope=__doc__)
        write_text(target,json.dumps(report,indent=2)+"\n")
        print(json.dumps({k:result[k] for k in ("accepted_pixels","crossed_pixels","max_water_length_error_m","exact_bypasses","negative_controls")},indent=2))
    finally:
        require(scratch.parent==ROOT and scratch.name.startswith("nearclip-native-"),"Unsafe cleanup");shutil.rmtree(scratch)
if __name__=="__main__":main()
