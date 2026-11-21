"""Synthetic perspective water bench using actual Aurora GLSL; NOT Minecraft/Iris.
All generated code/builds/artifacts stay on D:. Run only against an explicit frozen digest.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import zlib
from compile_glsl import ROOT, SHADERS, expand
from validate_gpu import Runner, require, write_text, shader_digest, half
from validate_gpu_depth import matrix_uniform
from validate_water_depth import inverse_matrix, perspective_matrix
from validate_water_waves import f32

SCOPE = ("Authored perspective plane/AABB scene with actual Aurora GLSL water/fog/tone "
         "helpers in hidden native OpenGL; not Minecraft, Iris preprocessing, transparent "
         "draw ordering, a physical-water reference or a performance measurement.")
WIDTH, HEIGHT = 256, 144
SENTINEL_ALPHA = -13.0
BOXES = [
    ((-4.,-2.,-6.),(-1.,3.2,-5.35),(.52,.065,.025),"red wall"),
    ((1.,-2.,-4.4),(2.15,3.6,-3.25),(.54,.35,.035),"gold pillar"),
    ((3.1,-2.,-7.5),(6.,2.2,-6.6),(.025,.24,.40),"blue wall"),
    ((-.2,-2.,-3.5),(.03,2.7,-3.25),(.30,.34,.30),"thin pole"),
    ((-10.8,-2.,-13.),(-10.,.4,7.),(.30,.29,.24),"left bank"),
    ((10.,-2.,-13.),(10.8,.4,7.),(.30,.29,.24),"right bank"),
]
CAMERAS = (("OVERHEAD",70.),("OBLIQUE",35.),("GRAZING",10.))

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def unit(a): return mul(a,1/math.sqrt(dot(a,a)))
def mv(m,v): return tuple(dot(row,v) for row in m)
def finite_image(image): return all(math.isfinite(c) for row in image for p in row for c in p)

def box_hit(origin,direction,lower,upper):
    entry,leave=-math.inf,math.inf
    normal=(0.,1.,0.)
    for axis in range(3):
        if abs(direction[axis])<1e-12:
            if origin[axis]<lower[axis] or origin[axis]>upper[axis]: return None
            continue
        a=(lower[axis]-origin[axis])/direction[axis]
        b=(upper[axis]-origin[axis])/direction[axis]
        n=[0.,0.,0.];n[axis]=-1. if direction[axis]>0 else 1.
        if a>b:a,b=b,a
        if a>entry:entry,normal=a,tuple(n)
        leave=min(leave,b)
        if leave<entry:return None
    return (entry,normal) if entry>1e-5 and leave>=entry else None

def scene_hit(origin,direction):
    best=None
    if direction[1]<-1e-10:
        distance=(-2-origin[1])/direction[1]
        if distance>0:
            point=add(origin,mul(direction,distance))
            checker=(math.floor(point[0])+math.floor(point[2]))%2
            color=(.18,.22,.17) if checker else (.105,.14,.11)
            best=(distance,(0.,1.,0.),color,"checker floor")
    for lower,upper,color,label in BOXES:
        hit=box_hit(origin,direction,lower,upper)
        if hit and (best is None or hit[0]<best[0]):
            best=(hit[0],hit[1],color,label)
    return best

SUN=unit((.40,.82,.31))

def radiance(point,normal,albedo):
    # Authored diffuse illumination, independent of Minecraft assets/lighting.
    origin=add(point,mul(normal,.001))
    shadow=any(box_hit(origin,SUN,lo,hi) for lo,hi,_,_ in BOXES)
    lighting=.22+(0 if shadow else .78*max(0,dot(normal,SUN)))
    return tuple(half(c*lighting) for c in albedo)

def make_scene(pitch_degrees):
    pitch=math.radians(pitch_degrees);s,c=math.sin(pitch),math.cos(pitch)
    eye=(0.,16*s,-2+16*c)
    rotation=((1.,0.,0.),(0.,c,-s),(0.,s,c))
    inv_rotation=tuple(tuple(rotation[j][i] for j in range(3)) for i in range(3))
    model_inverse=tuple(tuple(inv_rotation[r][col] if r<3 and col<3 else
                              1. if r==col==3 else 0. for col in range(4)) for r in range(4))
    projection=tuple(tuple(map(f32,row)) for row in perspective_matrix(70.,WIDTH/HEIGHT,.05,128.))
    inverse=tuple(tuple(map(f32,row)) for row in inverse_matrix(projection))
    up=mv(rotation,(0.,1.,0.))
    snapshots,depth,coverage=[],[],[]
    opaque_count=water_count=0
    for y in range(HEIGHT):
        colors,depths,masks=[],[],[]
        for x in range(WIDTH):
            ray_view=unit((((x+.5)/WIDTH*2-1)/projection[0][0],
                           ((y+.5)/HEIGHT*2-1)/projection[1][1],-1.))
            ray_world=mv(inv_rotation,ray_view)
            hit=scene_hit(eye,ray_world)
            color,z,distance=(0.,0.,0.,0.),1.,math.inf
            if hit:
                distance,normal,albedo,_=hit
                point=add(eye,mul(ray_world,distance))
                view=mv(rotation,sub(point,eye))
                clip=mv(projection,view+(1.,))
                d=clip[2]/clip[3]*.5+.5
                if 0<=d<1:
                    z=f32(d);color=radiance(point,normal,albedo)+(1.,);opaque_count+=1
                else:distance=math.inf
            eligible=False
            if ray_world[1]<-1e-9:
                travel=-eye[1]/ray_world[1]
                point=add(eye,mul(ray_world,travel))
                eligible=(travel>0 and travel<distance-1e-4
                          and -10<=point[0]<=10 and -12<=point[2]<=7)
            water_count+=int(eligible)
            colors.append(color);depths.append((z,0.,0.,1.))
            masks.append((float(eligible),0.,0.,1.))
        snapshots.append(colors);depth.append(depths);coverage.append(masks)
    anchor_world=(eye[0],eye[1]+64.,eye[2])
    anchor=tuple(math.floor(v) for v in anchor_world)
    fraction=tuple(v-i for v,i in zip(anchor_world,anchor))
    uniforms=[
        ("gbufferProjection","m4",matrix_uniform(projection)),
        ("gbufferProjectionInverse","m4",matrix_uniform(inverse)),
        ("gbufferModelViewInverse","m4",matrix_uniform(model_inverse)),
        ("cameraPositionInt","i3",anchor),("cameraPositionFract","f3",fraction),
        ("upPosition","f3",up),("sunPosition","f3",mul(mv(rotation,SUN),100.)),
        ("hasSkylight","i1",(1,)),("hasCeiling","i1",(0,)),
        ("isEyeInWater","i1",(0,)),("blindness","f1",(0.,)),
        ("darknessFactor","f1",(0.,)),("rainStrength","f1",(0.,)),
        ("eyeBrightnessSmooth","i2",(240,240)),("fogColor","f3",(.55,.65,.70)),
        ("viewWidth","f1",(WIDTH,)),("viewHeight","f1",(HEIGHT,)),
        ("frameTimeCounter","f1",(17.,)),("blendFunc","i4",(770,771,1,771)),
        ("benchEyeHeight","f1",(eye[1],)),("benchNormal","f3",up),
        ("benchWaterSource","f3",(.045,.11,.13)),("benchAlpha","f1",(.55,)),
    ]
    return dict(color=snapshots,depth=depth,mask=coverage,uniforms=uniforms,
                eye=eye,pitch=pitch_degrees,water_pixels=water_count,opaque_pixels=opaque_count)

WATER_VERTEX="""#version 330 compatibility
uniform mat4 gbufferProjection;
uniform vec3 benchNormal;
uniform float benchEyeHeight;
void main() {
    // Plane depth is affine in NDC, giving real perspective raster depth
    // and correct clipping at its horizon instead of fake fragment depth.
    float plane=benchNormal.x*gl_Vertex.x/gbufferProjection[0][0]
               +benchNormal.y*gl_Vertex.y/gbufferProjection[1][1]-benchNormal.z;
    float depth=-gbufferProjection[2][2]-gbufferProjection[3][2]*plane/benchEyeHeight;
    gl_Position=vec4(gl_Vertex.xy,depth,1.0);
}
"""

def wrappers():
    background="#version 330 compatibility\n"+expand(SHADERS/"lib/fog.glsl")+"""
uniform sampler2D benchScene;
uniform sampler2D benchDepth;
layout(location=0) out vec4 color;
void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec2 uv=gl_FragCoord.xy/vec2(viewWidth,viewHeight);
    float depth=texelFetch(benchDepth,pixel,0).r;
    vec3 value;
    if(depth<1.0) value=applyAtmosphericFog(texelFetch(benchScene,pixel,0).rgb,reconstructViewPosition(uv,depth));
    else value=auroraSkyLinear(reconstructViewPosition(uv,0.5),fogColor);
    color=vec4(value,1.0);
}
"""
    water="#version 330 compatibility\n"+expand(SHADERS/"lib/fog.glsl")+"\n"+expand(SHADERS/"lib/water.glsl")+"""
uniform sampler2D benchMask;
uniform sampler2D benchBackground;
uniform vec3 benchNormal;
uniform vec3 benchWaterSource;
uniform float benchAlpha;
uniform int benchDiagnostic;
layout(location=0) out vec4 color;
void main() {
    vec2 uv=gl_FragCoord.xy/vec2(viewWidth,viewHeight);
    vec3 surface=reconstructViewPosition(uv,gl_FragCoord.z);
    vec2 dx=(mat3(gbufferModelViewInverse)*dFdx(surface)).xz;
    vec2 dy=(mat3(gbufferModelViewInverse)*dFdy(surface)).xz;
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    if(texelFetch(benchMask,pixel,0).r<0.5) discard;
    if(benchDiagnostic!=0) {
        vec3 normal=waterFilteredWaveNormal(benchNormal,surface,1.0,dx,dy);
        vec3 direction=reflect(normalize(surface),normal);
        ivec2 hitPixel; vec3 hitView,hitRGB; float distance,confidence; int steps;
        bool hit=traceWaterScene(surface+benchNormal*0.01,direction,hitPixel,hitView,hitRGB,distance,confidence,steps);
        color=vec4(hit?confidence:0.0,hit?1.0:0.0,hit?distance/64.0:0.0,1.0);
        return;
    }
    vec3 water=applyWaterStyle(benchWaterSource,surface,benchNormal,vec2(0.5/16.0,15.5/16.0),
                              1,blendFunc,fogColor,dx,dy);
    water=applyLateAtmosphericFog(water,surface);
    vec3 background=texelFetch(benchBackground,pixel,0).rgb;
    // Explicit ordinary source-alpha RGB math; not a test of native GL blending.
    color=vec4(water*benchAlpha+background*(1.0-benchAlpha),1.0);
}
"""
    final="#version 330 compatibility\n"+expand(SHADERS/"lib/settings.glsl")+"\n"+expand(SHADERS/"lib/scene_color.glsl")+"\n"+expand(SHADERS/"lib/tone_mapping.glsl")+"\n"+expand(SHADERS/"lib/color.glsl")+"""
uniform sampler2D benchScene;
layout(location=0) out vec4 color;
void main() {
    vec3 value=max(texelFetch(benchScene,ivec2(gl_FragCoord.xy),0).rgb,vec3(0.0))*exp2(EXPOSURE);
    color=vec4(gradeColor(linearToSrgb(toneMapScene(value))),1.0);
}
"""
    return background,water,final


def png(path,rows):
    height,width=len(rows),len(rows[0])
    raw=b"".join(b"\x00"+bytes(c for p in row for c in p) for row in rows)
    def chunk(kind,payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff)
    data=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))
    data+=chunk(b"IDAT",zlib.compress(raw,9))+chunk(b"IEND",b"")
    with path.open("xb") as stream:stream.write(data)

def display_rows(image):
    return [[tuple(int(round(max(0,min(1,v))*255)) for v in p[:3]) for p in row] for row in reversed(image)]

FONT={
"A":"01110|10001|10001|11111|10001|10001|10001","B":"11110|10001|10001|11110|10001|10001|11110",
"C":"01111|10000|10000|10000|10000|10000|01111","D":"11110|10001|10001|10001|10001|10001|11110",
"E":"11111|10000|10000|11110|10000|10000|11111","F":"11111|10000|10000|11110|10000|10000|10000",
"G":"01111|10000|10000|10111|10001|10001|01111","H":"10001|10001|10001|11111|10001|10001|10001",
"I":"11111|00100|00100|00100|00100|00100|11111","J":"00111|00010|00010|00010|10010|10010|01100",
"K":"10001|10010|10100|11000|10100|10010|10001","L":"10000|10000|10000|10000|10000|10000|11111",
"M":"10001|11011|10101|10101|10001|10001|10001","N":"10001|11001|10101|10011|10001|10001|10001",
"O":"01110|10001|10001|10001|10001|10001|01110","P":"11110|10001|10001|11110|10000|10000|10000",
"Q":"01110|10001|10001|10001|10101|10010|01101","R":"11110|10001|10001|11110|10100|10010|10001",
"S":"01111|10000|10000|01110|00001|00001|11110","T":"11111|00100|00100|00100|00100|00100|00100",
"U":"10001|10001|10001|10001|10001|10001|01110","V":"10001|10001|10001|10001|10001|01010|00100",
"W":"10001|10001|10001|10101|10101|10101|01010","X":"10001|10001|01010|00100|01010|10001|10001",
"Y":"10001|10001|01010|00100|00100|00100|00100","Z":"11111|00001|00010|00100|01000|10000|11111",
"0":"01110|10001|10011|10101|11001|10001|01110","1":"00100|01100|00100|00100|00100|00100|01110",
"2":"01110|10001|00001|00010|00100|01000|11111","3":"11110|00001|00001|01110|00001|00001|11110",
"4":"00010|00110|01010|10010|11111|00010|00010","5":"11111|10000|10000|11110|00001|00001|11110",
"6":"01110|10000|10000|11110|10001|10001|01110","7":"11111|00001|00010|00100|01000|01000|01000",
"8":"01110|10001|10001|01110|10001|10001|01110","9":"01110|10001|10001|01111|00001|00001|01110",
"/":"00001|00010|00010|00100|01000|01000|10000","-":"00000|00000|00000|11111|00000|00000|00000",
".":"00000|00000|00000|00000|00000|00110|00110",":":"00000|00110|00110|00000|00110|00110|00000"}

def draw_text(image,x,y,value):
    for char in value.upper():
        for dy,row in enumerate(FONT.get(char,"00000|"*6+"00000").split("|")):
            for dx,bit in enumerate(row):
                if bit=="1" and 0<=y+dy<len(image) and 0<=x+dx<len(image[0]):
                    image[y+dy][x+dx]=(225,230,238)
        x+=6

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-shader-sha256",required=True)
    parser.add_argument("--cxx",default="C:/msys64/ucrt64/bin/g++.exe")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/validation/W3_visual")
    args=parser.parse_args()
    require(ROOT.resolve().drive.upper()=="D:","Project must remain on D:")
    digest=shader_digest()
    require(digest==args.expect_shader_sha256,"Frozen shader digest differs; do not run during edits")
    output=args.output.resolve()
    allowed=(ROOT/"docs/validation").resolve()
    require(output.parent==allowed and output.name.startswith("W3_visual"),
            "Output must be a new W3_visual directory in docs/validation")
    require(not output.exists(),"Refusing to overwrite an existing visual bench")
    output.mkdir()
    bg_wrapper,water_wrapper,final_wrapper=wrappers()
    report=dict(schema=1,ok=False,scope=SCOPE,shader_sha256=digest,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                width=WIDTH,height=HEIGHT,daylight_only=True,budget=64,native_alpha=.55,
                fov_y_degrees=70.,near_plane=.05,far_plane=128.,frame_time_seconds=17.,
                world_water_level=64.,
                options="Pack defaults except SSR off/on; authored source RGB (0.045,0.11,0.13)",
                cases=[],images=[])
    owner=tempfile.TemporaryDirectory(prefix="Aurora-W3-visual-",dir=str(ROOT.parent))
    scratch=Path(owner.name).resolve()
    require(scratch.parent==ROOT.parent.resolve() and scratch.name.startswith("Aurora-W3-visual-"),
            "Unexpected temporary directory")
    panels=[]
    try:
        runner=Runner(scratch,args.cxx)
        plane_vertex=scratch/"water-plane.vert"
        write_text(plane_vertex,WATER_VERTEX)
        for camera_name,pitch in CAMERAS:
            scene=make_scene(pitch);common=scene["uniforms"]
            bg_uniforms=[u for u in common if u[0] not in {
                "gbufferProjection","frameTimeCounter","blendFunc","benchEyeHeight",
                "benchNormal","benchWaterSource","benchAlpha"}]
            background=runner.render(camera_name+"-background",runner.pair("composite",wrapper=bg_wrapper),
                WIDTH,HEIGHT,[("benchScene",scene["color"],"RGBA16F"),("benchDepth",scene["depth"],"R32F")],bg_uniforms)
            require(finite_image(background),"Nonfinite background")
            results={}
            for enabled in (0,1):
                options=dict(WATER_SCREEN_REFLECTIONS=enabled,WATER_REFLECTION_STEPS=64)
                _,fragment=runner.pair("composite",options,water_wrapper)
                textures=[("colortex5",scene["color"],"RGBA16F"),("colortex6",scene["depth"],"R32F"),
                          ("depthtex1",scene["depth"],"R32F"),("depthtex2",scene["depth"],"R32F"),
                          ("benchMask",scene["mask"],"RGBA32F"),("benchBackground",background,"RGBA32F")]
                optional=["colortex5","colortex6","depthtex1"] if not enabled else []
                water=runner.render(camera_name+"-water-"+str(enabled),(plane_vertex,fragment),
                    WIDTH,HEIGHT,textures,common+[("benchDiagnostic","i1",(0,))],optional=optional)
                require(finite_image(water),"Nonfinite water output")
                surviving=sum(p[3]!=SENTINEL_ALPHA for row in water for p in row)
                require(surviving==scene["water_pixels"],"Perspective plane coverage differs from analytic mask")
                require(all((p[3]!=SENTINEL_ALPHA)==bool(scene["mask"][y][x][0])
                            for y,row in enumerate(water) for x,p in enumerate(row)),
                        "Perspective raster coverage differs at an analytic mask pixel")
                merged=[[background[y][x] if p[3]==SENTINEL_ALPHA else p for x,p in enumerate(row)]
                        for y,row in enumerate(water)]
                image=runner.render(camera_name+"-display-"+str(enabled),
                    runner.pair("composite",wrapper=final_wrapper),WIDTH,HEIGHT,[("benchScene",merged,"RGBA32F")])
                require(finite_image(image),"Nonfinite display output")
                results[enabled]=image
                filename=camera_name.lower()+("_SSR_on.png" if enabled else "_SSR_off.png")
                png(output/filename,display_rows(image));report["images"].append(filename)
                if enabled:
                    diagnostic=runner.render(camera_name+"-hits",(plane_vertex,fragment),WIDTH,HEIGHT,
                        textures,common+[("benchDiagnostic","i1",(1,))])
                    require(finite_image(diagnostic),"Nonfinite diagnostics")
            difference=[[tuple(min(1,abs(a-b)*16) for a,b in zip(p[:3],q[:3]))+(1.,)
                         for p,q in zip(r,s)] for r,s in zip(results[0],results[1])]
            diagnostic_image=[[(0.,0.,0.,1.) if p[3]==SENTINEL_ALPHA else p for p in row] for row in diagnostic]
            png(output/(camera_name.lower()+"_delta16.png"),display_rows(difference))
            png(output/(camera_name.lower()+"_trace.png"),display_rows(diagnostic_image))
            report["images"].extend([camera_name.lower()+"_delta16.png",camera_name.lower()+"_trace.png"])
            require(all(p==q for y,(r,t) in enumerate(zip(results[0],results[1]))
                        for x,(p,q) in enumerate(zip(r,t)) if not scene["mask"][y][x][0]),
                    "SSR changed an off-water display pixel")
            changed=sum(max(abs(a-b) for a,b in zip(p[:3],q[:3]))>1e-6
                        for r,s in zip(results[0],results[1]) for p,q in zip(r,s))
            max_delta=max(abs(a-b) for r,s in zip(results[0],results[1])
                          for p,q in zip(r,s) for a,b in zip(p[:3],q[:3]))
            hits=sum(p[3]!=SENTINEL_ALPHA and p[1]>.5 for row in diagnostic for p in row)
            report["cases"].append(dict(camera=camera_name,pitch_down_degrees=pitch,
                angle_from_surface_normal=90-pitch,eye_relative_to_water=scene["eye"],
                water_pixels=scene["water_pixels"],opaque_pixels=scene["opaque_pixels"],
                trace_hits=hits,changed_display_pixels=changed,max_display_delta=max_delta,
                exact_water_coverage=True,off_water_display_unchanged=True))
            panels.append((camera_name,[display_rows(results[0]),display_rows(results[1]),
                                        display_rows(difference),display_rows(diagnostic_image)]))
            print(camera_name,"water",scene["water_pixels"],"hits",hits,"changed",changed,flush=True)
        require(shader_digest()==digest,"Shader source changed during visual run")
        require(any(c["trace_hits"]>0 for c in report["cases"]),"Visual bench produced no scene hits")
        require(any(c["changed_display_pixels"]>0 for c in report["cases"]),"SSR changed no displayed pixels")
        sheet=[[(17,22,30)]*(WIDTH*3) for _ in range(22+(HEIGHT+18)*4)]
        draw_text(sheet,8,7,"SYNTHETIC GLSL WATER BENCH / NOT MINECRAFT")
        row_labels=("SSR OFF","SSR ON","DISPLAY DELTA X16","TRACE R CONF G HIT B RANGE")
        for column,(name,images) in enumerate(panels):
            for row,image in enumerate(images):
                top=22+row*(HEIGHT+18)
                draw_text(sheet,column*WIDTH+5,top+5,name+" / "+row_labels[row])
                for y,pixels in enumerate(image):
                    sheet[top+18+y][column*WIDTH:(column+1)*WIDTH]=pixels
        png(output/"contact_sheet.png",sheet)
        report["images"].append("contact_sheet.png")
        report.update(ok=True,gl=runner.gl,build=runner.build)
        write_text(output/"report.json",json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        write_text(output/"README.md","""# W3 synthetic water visual bench

This is authored analytic geometry rendered with actual Aurora GLSL helpers.
It is **not Minecraft or Iris imagery**, a physical-water reference or a performance measurement.

- Columns: overhead 70, oblique 35, grazing 10 degrees downward pitch (20/55/80 from water normal).
- Rows: SSR off; SSR on; absolute display-space difference magnified 16x; trace diagnostics.
- Diagnostic channels: red = confidence, green = valid hit, blue = hit distance / 64.
- Each panel is 256x144, daylight, default controls, 64 steps, constant source alpha 0.55.
- Vertical FOV is 70 degrees, near/far planes 0.05/128, fixed wave time 17 seconds, world water level 64.
- Every surviving water fragment must match the independent CPU mask; off-water display pixels must remain exactly unchanged.
- An independent CPU scene supplies colored AABBs, a checker floor, paired FP16 color and R32F depth. No Minecraft textures or imported imagery are used.
- Water has true perspective raster depth and real derivatives before the analytic coverage mask.
- Native GLSL runs actual water style, late fog, tone mapping, display encoding and grading.
- Source-alpha RGB arithmetic is explicit over the background; actual OpenGL blending, Minecraft transparent sorting and Iris buffer flipping are not tested.
- Analytic sky fallback does not include actual aurora, glow, discs or clouds. Reflected-segment fog and physical water composition remain absent.
- The JSON report records exact shader/script digests, GPU identity and pixel counts; no frame-time/FPS number is reported.

![Synthetic contact sheet](contact_sheet.png)

Source: [render_water_bench.py](../../../tools/render_water_bench.py).
To reproduce from the repository, run Python with -B tools/render_water_bench.py,
--expect-shader-sha256 set to report.json's shader_sha256, and --output pointing
to a new docs/validation/W3_visual-prefixed directory. Existing output is never overwritten.
The source, native build and temporary files remain on D:.
""")
    finally:
        # Verify the exact owned target again before recursive temporary cleanup.
        require(scratch.parent==ROOT.parent.resolve() and scratch.name.startswith("Aurora-W3-visual-"),
                "Refusing cleanup outside owned D: temporary directory")
        owner.cleanup()

if __name__=="__main__":
    main()
