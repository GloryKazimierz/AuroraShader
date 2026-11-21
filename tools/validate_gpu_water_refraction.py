"""Native refraction images, target-only invalidation and an independent Snell/transport reference."""
import copy
from functools import lru_cache
from io import BytesIO
import math
import re
import subprocess
from zipfile import ZipFile

from compile_glsl import ROOT
from validate_gpu_water_planar import prepare_tiles
from validate_gpu import compare, half, require, write_text
from validate_gpu_water_transport import FORMATS, analytical_transport, slab_scene, smooth
from render_water_bench import (WIDTH, HEIGHT, make_scene, WATER_VERTEX, png, display_rows,
                               draw_text, dot, mul, add, unit)

def refract(incident,normal_toward_incident,n_incident,n_transmitted):
    incident=unit(incident);normal=unit(normal_toward_incident)
    cosine=-dot(incident,normal)
    if not 0<=cosine<=1+1e-12 or min(n_incident,n_transmitted)<=0:raise ValueError("normal must face the incident medium")
    eta=n_incident/n_transmitted
    sine2=eta*eta*max(0.,1-cosine*cosine)
    if sine2>1:return None
    return unit(add(mul(incident,eta),mul(normal,eta*cosine-math.sqrt(max(0.,1-sine2)))))
def water_index_iapws(wavelength_um,kelvin=293.15,density=998.207):
    """IAPWS R9-97 Eq.1, water refractive index relative to vacuum.
    https://iapws.org/documents/release/Rindex.download
    The density is an explicit model input, not a pressure conversion.
    """
    if not(.2<=wavelength_um<=1.1 and 261.15<=kelvin<=773.15 and 0<=density<=1060):
        raise ValueError("outside selected IAPWS domain")
    wavelength=wavelength_um/.589;temperature=kelvin/273.15;rho=density/1000
    a=(.244257733,.00974634476,-.00373234996,.000268678472,
       .00158920570,.00245934259,.900704920,-.0166626219)
    ll=rho*(a[0]+a[1]*rho+a[2]*temperature+a[3]*wavelength*wavelength*temperature
            +a[4]/(wavelength*wavelength)+a[5]/(wavelength*wavelength-.2292020**2)
            +a[6]/(wavelength*wavelength-5.432937**2)+a[7]*rho*rho)
    return math.sqrt((2*ll+1)/(1-ll))


HEADER="""#version 330 compatibility
#define WATER_REFRACTION 1
uniform mat4 gbufferProjection,gbufferProjectionInverse;
uniform sampler2D colortex5,colortex6,colortex7,colortex8,colortex9,depthtex0,depthtex1;
uniform vec3 fixtureUp;
"""
MAIN="""
layout(location=0) out vec4 result;
layout(location=1) out vec4 metadata;
void main(){
 ivec2 size=textureSize(colortex7,0),pixel=ivec2(gl_FragCoord.xy);
 vec4 record=texelFetch(colortex7,pixel,0);
 vec2 uv=(vec2(pixel)+.5)/vec2(size);
 vec4 p=gbufferProjectionInverse*vec4(uv*2.0-1.0,record.a*2.0-1.0,1.0);
 WaterRefractionHit h;
 bool valid=traceWaterRefraction(p.xyz/p.w,fixtureUp,record.xyz,1.0,1.333,128,h);
 result=vec4(valid?h.pathLength:-float(h.reason)-1.0,vec2(h.pixel),float(h.steps));
 metadata=vec4(h.directShare,h.receiverNormal);
}
"""
OPTIONS=dict(IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_OPTICS=1,FOG_ENABLED=0,
             WATER_SCREEN_REFLECTIONS=0,WATER_REFLECTION_STRENGTH=0.0,SKY_STYLE=0)

def resolve(runner,scene,settings):
    options=dict(OPTIONS,**settings)
    textures=prepare_tiles(runner,scene,settings)
    return runner.render("water refraction",runner.pair("composite1",options),scene["width"],scene["height"],
        [(n,data,FORMATS[n]) for n,data in textures.items()],scene["uniforms"],
        optional=list(textures)+[u[0] for u in scene["uniforms"]])

def integration_tests(runner):
    reports=[];samples=changed=chromatic_changed=0
    for pitch in (35.,55.,80.):
        for depth in (.05,.5,2.,8.):
            scene=slab_scene(48,32,depth,pitch)
            off=resolve(runner,scene,dict(WATER_REFRACTION=0))
            on=resolve(runner,scene,dict(WATER_REFRACTION=2))
            chromatic=resolve(runner,scene,dict(WATER_REFRACTION=3))
            for image in (off,on,chromatic):
                require(all(math.isfinite(c) for row in image for pixel in row for c in pixel),"Nonfinite integrated image")
                require(all(a[3]==b[3] for ar,br in zip(image,scene["textures"]["colortex0"]) for a,b in zip(ar,br)),"Composite alpha changed")
            count=sum(a!=b for ar,br in zip(off,on) for a,b in zip(ar,br))
            split=sum(a!=b for ar,br in zip(on,chromatic) for a,b in zip(ar,br))
            require(count>0,"Actual composite did not consume refraction")
            changed+=count;chromatic_changed+=split;samples+=48*32
            reports.append(dict(pitch=pitch,depth=depth,changed=count,chromatic_changed=split))
    require(chromatic_changed>100,"Dispersion route inactive")
    # Whole-image invalid sources must stay native, even when RGB quality is on.
    scene=slab_scene(48,32,2.,55.)
    invalid=[]
    for label,key,fn in (
        ("source-overlay","colortex8",lambda p:(1.,p[1],p[2],0.)),
        ("source-two-water","colortex8",lambda p:(2/255,p[1],p[2],0.)),
        ("source-front","depthtex0",lambda p:(p[0]-.001,0.,0.,1.)),
        ("missing-bed","colortex5",lambda p:(p[0],p[1],p[2],0.)),
    ):
        modified=dict(scene);modified["textures"]=dict(scene["textures"])
        modified["textures"][key]=[[fn(p) for p in row] for row in modified["textures"][key]]
        result=resolve(runner,modified,dict(WATER_REFRACTION=3))
        compare(result,scene["textures"]["colortex0"],label);invalid.append(label)
    return dict(cases=reports,pixels=samples,refraction_changed=changed,dispersion_changed=chromatic_changed,
                exact_native_fallbacks=invalid,alpha_exact=True)

def scene_capture(runner,pitch):
    authored=make_scene(pitch);mask=authored["mask"]
    common={n:(n,k,v) for n,k,v in authored["uniforms"]}
    vertex=runner.scratch/("captured-water-"+str(pitch)+".vert")
    declarations="""
out vec2 lmcoord, texcoord;
out vec4 glcolor;
out vec3 normalView;
flat out int waterSurface;
"""
    setup="""
texcoord=gl_MultiTexCoord0.xy; lmcoord=vec2(.5/16.0,15.5/16.0);
glcolor=vec4(1);normalView=benchNormal;waterSurface=1;
"""
    write_text(vertex,WATER_VERTEX.replace("void main() {",declarations+"\nvoid main() {"+setup))
    atlas=[[(.18,.32,.38,.55 if pixel[0] else 0.) for pixel in row] for row in mask]
    textures=[("gtexture",atlas,"RGBA32F"),("lightmap",[[(1.,1.,1.,1.)]],"RGBA32F"),
              ("colortex5",authored["color"],"RGBA16F"),("colortex6",authored["depth"],"R32F"),
              ("depthtex1",authored["depth"],"R32F"),("depthtex2",authored["depth"],"R32F")]
    options=dict(IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_OPTICS=1,FOG_ENABLED=0,WATER_SCREEN_REFLECTIONS=0)
    _,fragment=runner.pair("gbuffers_water",options)
    uniforms=list(common.values())
    optional=[n for n,_,_ in uniforms]+[n for n,_,_ in textures]
    captures=[]
    for slot in (0,1,2):
        captures.append(runner.render("actual-water-capture",(vertex,fragment),WIDTH,HEIGHT,textures,uniforms,
            optional=optional,extra_targets=((1,1,"RGBA32F"),(2,2,"RGBA8")),read_target=slot))
    native,record,count=captures
    final_color=[];final_depth=[]
    water_pixels=0
    for y in range(HEIGHT):
        colors=[];depths=[]
        for x in range(WIDTH):
            background=authored["color"][y][x]
            if mask[y][x][0]:
                water_pixels+=1
                require(record[y][x][3]!=-13 and count[y][x][0]>0,"Missing water capture")
                a=native[y][x][3]
                colors.append(tuple(half(max(0.,native[y][x][c]*a+background[c]*(1-a))) for c in range(3))+(1.,))
                depths.append((record[y][x][3],0.,0.,1.))
            else:
                require(native[y][x][3]==-13,"Atlas hole did not discard")
                record[y][x]=(0.,0.,0.,0.);count[y][x]=(0.,0.,0.,0.)
                colors.append(background);depths.append(authored["depth"][y][x])
        final_color.append(colors);final_depth.append(depths)
    uniforms=[common[n] for n in ("gbufferProjection","gbufferProjectionInverse","gbufferModelViewInverse",
        "upPosition","sunPosition","fogColor","hasSkylight","hasCeiling","isEyeInWater","blindness",
        "darknessFactor","rainStrength","eyeBrightnessSmooth","cameraPositionInt","cameraPositionFract")]
    uniforms.append(("shadowLightPosition","f3",common["sunPosition"][2]))
    from render_water_bench import unit as bench_unit, mv, scene_hit
    projection_data=common["gbufferProjection"][2]
    inverse_data=common["gbufferModelViewInverse"][2]
    inverse_rotation=tuple(tuple(inverse_data[c*4+r] for c in range(3)) for r in range(3))
    rotation=tuple(tuple(inverse_rotation[c][r] for c in range(3)) for r in range(3))
    bed_normals=[]
    for y in range(HEIGHT):
        row=[]
        for x in range(WIDTH):
            ray=bench_unit((((x+.5)/WIDTH*2-1)/projection_data[0],
                            ((y+.5)/HEIGHT*2-1)/projection_data[5],-1.))
            h=scene_hit(authored["eye"],mv(inverse_rotation,ray))
            row.append(tuple(.5+.5*v for v in mv(rotation,h[1]))+(1.,) if h else (.5,.5,.5,0.))
        bed_normals.append(row)
    textures={"colortex0":final_color,"colortex5":authored["color"],"colortex6":authored["depth"],
        "colortex1":bed_normals,"colortex7":record,"colortex8":count,"colortex9":[[(.25,0,0,1)]*WIDTH for _ in range(HEIGHT)],
        "depthtex0":final_depth,"depthtex1":authored["depth"]}
    return dict(width=WIDTH,height=HEIGHT,textures=textures,uniforms=uniforms,water_pixels=water_pixels)

def comparison(runner,path):
    cases=[];rows=[]
    qualities=(("M1 SAME RAY",dict(WATER_REFRACTION=0)),
               ("PLANAR VERIFIED",dict(WATER_REFRACTION=1)),
               ("RGB PLANAR",dict(WATER_REFRACTION=3)))
    sheet=[[(21,25,32)]*(WIDTH*3) for _ in range((HEIGHT+21)*3+21)]
    draw_text(sheet,5,6,"ACTUAL STAGED COMPOSITE / SYNTHETIC SCENE / NOT MINECRAFT")
    for row,(label,pitch) in enumerate((("OVERHEAD",70.),("OBLIQUE",35.),("GRAZING",10.))):
        scene=scene_capture(runner,pitch)
        baseline=None
        for column,(quality,options) in enumerate(qualities):
            options=dict(options,SKY_STYLE=1,WATER_REFLECTION_STRENGTH=.5)
            image=resolve(runner,scene,options)
            if baseline is None:baseline=image
            changed=sum(a!=b for ar,br in zip(image,baseline) for a,b in zip(ar,br))
            displayed=runner.render("final",runner.pair("final"),WIDTH,HEIGHT,[("colortex0",image,"RGBA32F")])
            x=column*WIDTH;y=21+row*(HEIGHT+21)
            draw_text(sheet,x+3,y+6,label+" / "+quality)
            for dy,pixels in enumerate(display_rows(displayed)):sheet[y+21+dy][x:x+WIDTH]=pixels
            cases.append(dict(view=label,pitch=pitch,quality=quality,changed_from_same_ray=changed,water_pixels=scene["water_pixels"]))
    png(path,sheet)
    return cases

@lru_cache(maxsize=1)
def reference_source():
    baseline='a19116f'
    with ZipFile(BytesIO(subprocess.check_output(
            ['git','-C',str(ROOT),'archive','--format=zip',baseline,'shaders']))) as tree:
        @lru_cache(maxsize=None)
        def expand_previous(name):
            return re.sub(r'^#include "([^"]+)"\s*$',lambda m:expand_previous(m[1].lstrip('/')),
                          tree.read('shaders/'+name).decode('utf-8'),flags=re.M)
        return expand_previous('composite.fsh')

def outer_confidence(scene,x,y):
    w,h=scene["width"],scene["height"];front,back=scene["front"][y][x],scene["back"][y][x]
    delta=tuple(a-b for a,b in zip(front,back))
    drop=sum(scene["model"][1][c]*delta[c] for c in range(3));distance=math.dist(front,back)
    result=smooth(0,2,min(x+.5,y+.5,w-x-.5,h-y-.5))*smooth(.03,.12,dot(unit(tuple(-v for v in front)),scene["up"]))
    result*=smooth(.001,.03,drop)*(1-smooth(48,64,distance))
    for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
        gap=abs(scene["back"][ny][nx][2]-back[2])
        result*=1-smooth(max(.25,distance*.05),max(.5,distance*.15),gap)
    return result

def analytic_hit(scene,x,y,depth,ior):
    front=scene["front"][y][x];direction=refract(unit(front),scene["up"],1.,ior)
    distance=(-4-depth-dot(front,scene["up"]))/dot(direction,scene["up"])
    point=tuple(a+b*distance for a,b in zip(front,direction))
    matrix=next(v for n,k,v in scene["uniforms"] if n=="gbufferProjection")
    px=(matrix[0]*point[0]/-point[2]*.5+.5)*scene["width"]
    py=(matrix[5]*point[1]/-point[2]*.5+.5)*scene["height"]
    require(min(px,py,scene["width"]-px,scene["height"]-py)>8,"Oracle query edge confidence not one")
    require(min(px%1,py%1,1-px%1,1-py%1)>.012,"Oracle target too near a texel boundary")
    tx,ty=int(px),int(py)
    rgb=scene["textures"]["colortex5"][ty][tx][:3];share=scene["textures"]["colortex9"][ty][tx][0]
    drop=-dot(tuple(b-a for a,b in zip(front,point)),scene["up"])
    cosine=max(0,min(1,dot(scene["light"],scene["up"])))
    light=drop/math.sqrt(1-(1-cosine*cosine)/(ior*ior))
    levels=scene["textures"]["colortex8"][y][x]
    return analytical_transport(rgb,share,distance,light,levels[1],levels[2],(0,0,0)),(tx,ty),distance

def render_baseline(runner,scene):
    pair=runner.pair("composite1",OPTIONS,reference_source())
    return runner.render("baseline-before-refraction",pair,scene["width"],scene["height"],
        [(n,d,FORMATS[n]) for n,d in scene["textures"].items()],scene["uniforms"],
        optional=list(scene["textures"])+[u[0] for u in scene["uniforms"]])

def checks(runner):
    results=[];maximum=0;distinguished=0;positive=0;offpixels=0
    for pitch in (35.,55.,80.):
        for depth in (2.,8.):
            scene=slab_scene(48,32,depth,pitch,block=.5,sun_cosine=.4)
            scene["textures"]["colortex9"]=[[(float((x+2*y)%16)/16,0,0,1) for x in range(48)] for y in range(32)]
            original=render_baseline(runner,scene);off=resolve(runner,scene,dict(WATER_REFRACTION=0))
            compare(off,original,"exact off versus baseline");offpixels+=48*32
            for mode in (1,2,3):
                actual=resolve(runner,scene,dict(WATER_REFRACTION=mode))
                for x,y in ((24,16),(20,14),(28,18)):
                    iors=(1.333,) if mode!=3 else tuple(water_index_iapws(w) for w in (.65,.55,.45))
                    try:hits=[analytic_hit(scene,x,y,depth,ior) for ior in iors]
                    except RuntimeError as error:
                        if str(error).startswith("Oracle "):continue
                        raise
                    expected=hits[0][0] if mode!=3 else tuple(hits[c][0][c] for c in range(3))
                    conf=outer_confidence(scene,x,y);native=scene["textures"]["colortex0"][y][x]
                    expected=tuple(a*(1-conf)+b*conf for a,b in zip(native[:3],expected))+(native[3],)
                    error=max(abs(a-b) for a,b in zip(actual[y][x],expected))
                    maximum=max(maximum,error)
                    require(error<.00035,"Analytic composite mismatch: "+str((pitch,depth,mode,x,y,error,actual[y][x],expected)))
                    for h in hits:
                        tx,ty=h[1];distinguished+=scene["textures"]["colortex9"][ty][tx][0]!=scene["textures"]["colortex9"][y][x][0]
                    positive+=1;results.append(dict(pitch=pitch,depth=depth,mode=mode,source=[x,y],target=[list(h[1]) for h in hits],error=error))
    require(positive>=40 and distinguished>=30,"Insufficient independent oracle coverage")
    # The corrupted target is isolated outside the complete source 3x3 region.
    scene=slab_scene(48,32,8.,35.);x,y=24,16
    _,target,_=analytic_hit(scene,x,y,8.,1.333);tx,ty=target
    require(max(abs(tx-x),abs(ty-y))>2,"Target not isolated from source")
    uniforms=[v for v in scene["uniforms"] if v[0] in ("gbufferProjection","gbufferProjectionInverse")]+[("fixtureUp","f3",scene["up"])]
    pair=runner.pair("composite1",wrapper=HEADER+(ROOT/"shaders/lib/water_refraction.glsl").read_text(encoding="utf-8")+MAIN)
    base_on=resolve(runner,scene,dict(WATER_REFRACTION=1));base_off=resolve(runner,scene,dict(WATER_REFRACTION=0))
    require(base_on[y][x]!=base_off[y][x],"Target-veto query had no optical effect")
    vetoes=[]
    for label,key,change in (
        ("target-only-overlay","colortex8",lambda p:(1.,p[1],p[2],0.)),
        ("target-only-two-water","colortex8",lambda p:(2/255,p[1],p[2],0.)),
        ("target-only-front-slab","depthtex0",lambda p:(p[0]-.001,0,0,1)),
        ("target-only-early-owner","colortex9",lambda p:(-1.,0,0,1)),
        ("target-only-invalid-color","colortex5",lambda p:(p[0],p[1],p[2],0)),
        ("target-only-unmatched-depth","colortex6",lambda p:(p[0]-.001,0,0,1)),
        ("target-only-unobserved-interface","colortex7",lambda p:(0,0,0,0)),
    ):
        modified=copy.deepcopy(scene);modified["textures"][key][ty][tx]=change(modified["textures"][key][ty][tx])
        for sy in range(y-1,y+2):
            for sx in range(x-1,x+2):
                require(modified["textures"][key][sy][sx]==scene["textures"][key][sy][sx],"Source footprint mutated")
        diagnostic=runner.render(label,pair,48,32,[(n,d,FORMATS[n]) for n,d in modified["textures"].items() if n!="colortex0"],
            uniforms,extra_targets=((1,1,"RGBA32F"),))
        require(diagnostic[y][x][0]<0,label+" helper accepted target")
        actual=resolve(runner,modified,dict(WATER_REFRACTION=1))
        require(actual[y][x]==base_off[y][x],label+" failed exact same-ray fallback")
        vetoes.append(dict(label=label,target=list(target),source=[x,y],helper_reason=diagnostic[y][x][0]))
    # Too-shallow depths stay on same-ray/native support without a fabricated hit.
    shallow=[]
    for depth in (.0005,.002):
        tiny=slab_scene(48,32,depth,55.)
        off=resolve(runner,tiny,dict(WATER_REFRACTION=0))
        on=resolve(runner,tiny,dict(WATER_REFRACTION=3))
        compare(on,off,"sub-bias shallow fallback")
        shallow.append(depth)
    return dict(analytic_cases=results,analytic_samples=positive,max_rgb_error=maximum,
                source_target_q_differences=distinguished,exact_off_pixels=offpixels,
                target_only_vetoes=vetoes,exact_shallow_fallback_depths=shallow)

def refraction_tests(runner,plate=None):
    require(abs(water_index_iapws(.589,273.15,999.8426)-1.334344)<5e-7,"IAPWS reference row")
    from validate_gpu_water_planar import planar_tests, combined_foam_tests
    result=dict(planar=planar_tests(runner),transport=integration_tests(runner),analytic=checks(runner),
                combined_foam=combined_foam_tests(runner))
    if plate is not None:
        result['views']=comparison(runner,plate)
    return result
