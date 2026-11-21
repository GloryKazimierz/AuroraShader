"""Native M1 water transport checks. Synthetic inputs, not Minecraft/Iris runtime.

The analytical oracle below is independent of the source validator implementation.
The indexed-blend proof exercises actual driver blending into mixed attachments;
the resolve checks exercise the actual composite program with authored inputs.
"""
import math
from compile_glsl import SHADERS, expand
from validate_gpu import compare, half, require, write_text
from validate_water_waves import f32
from validate_water_depth import inverse_matrix, perspective_matrix, reconstruct_view
from validate_gpu_depth import matrix_uniform
from render_water_bench import display_rows, draw_text, png, make_scene, WIDTH, HEIGHT


def analytical_transport(source, share, view_m, light_m, block, sky, sky_rgb, clarity=1.0, body=0):
    # Radiative-transfer approximation specified by M1: attenuate the separated
    # custom direct share along the incoming leg, then every source component
    # along the outgoing leg. Scatter is bounded by available illumination.
    sigma_a,sigma_s = (
        ((.18,.055,.025),(.012,.020,.025)),
        ((.24,.052,.09),(.032,.105,.083)),
        ((.08,.155,.34),(.066,.044,.022)),
        ((.32,.075,.018),(.008,.018,.035)),
    )[body]
    share, block, sky = [min(1., max(0., x)) for x in (share, block, sky)]
    result = []
    for channel in range(3):
        radiance = max(0., source[channel])
        sky_light = max(0., sky_rgb[channel])
        extinction = (sigma_a[channel] + sigma_s[channel]) / clarity
        scatter = sigma_s[channel] / clarity
        outgoing = math.exp(-min(80., max(0., view_m) * extinction))
        incoming = math.exp(-min(80., max(0., light_m) * extinction))
        incident = radiance * (1. - share + share * incoming)
        available = min(radiance + sky_light,
                        radiance * (.25 + .35 * block) + sky_light * .25 * sky)
        result.append(incident * outgoing + (1. - outgoing) * scatter / extinction * available)
    return tuple(result)


def indexed_blend_tests(runner):
    source = """#version 330 compatibility
uniform vec4 nativeColor, recordValue, countValue;
layout(location=0) out vec4 color;
layout(location=1) out vec4 record;
layout(location=2) out vec4 count;
void main(){color=nativeColor;record=recordValue;count=countValue;}
"""
    result = runner.call("--water-blend-check", *runner.pair("composite1", wrapper=source))
    # Deliberately wrong additive count and metadata outputs must fail. This
    # proves the protocol check observes its attachments instead of just linking.
    rejected = []
    for label, old, new in (
        ("missing count", "count=countValue", "count=vec4(0.0)"),
        ("alpha-scaled record", "record=recordValue", "record=recordValue*nativeColor.a"),
    ):
        # Keep countValue active so the first negative reaches the comparison.
        if label == "missing count":
            new = "count=countValue*0.5"
        pair = runner.pair("composite1", wrapper=source.replace(old, new))
        runner.call("--water-blend-check", *pair, expected_failure="water blend comparison")
        rejected.append(label)
    return dict(**result["water_blend"], negative_controls=rejected)


def helper_tests(runner):
    source = """#version 330 compatibility
""" + expand(SHADERS / "lib/water_optics_settings.glsl") + "\n" + expand(SHADERS / "lib/water_transport.glsl") + """
uniform sampler2D sourceShare, pathsLight, inputSky;
layout(location=0) out vec4 color;
void main(){
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec4 a=texelFetch(sourceShare,pixel,0);
    vec4 b=texelFetch(pathsLight,pixel,0);
    vec3 c=texelFetch(inputSky,pixel,0).rgb;
    color=vec4(waterTransportRadiance(a.rgb,a.a,b.x,b.y,b.z,b.w,c),1.0);
}
"""
    cases=[]
    for radiance, share, block, sky, sky_rgb in (
        ((.6,.4,.2),.65,0.,1.,(.12,.3,.6)),
        ((.6,.4,.2),0.,1.,0.,(0.,0.,0.)),
        ((0.,0.,0.),0.,0.,0.,(0.,0.,0.)),
        ((2.,.3,.05),.8,1.,0.,(0.,0.,0.)),
        ((65504.,100.,.1),1.,.5,.5,(1.,.4,.2)),
        ((.1,.1,.1),1.,0.,0.,(0.,0.,0.)),
    ):
        for view, light in ((0.,0.),(.1,.1),(1.,1.),(4.,6.),(16.,24.),(80.,100.)):
            cases.append((tuple(map(f32,radiance))+(f32(share),),
                          tuple(map(f32,(view,light,block,sky))),
                          tuple(map(f32,sky_rgb))+(1.,)))
    textures=[(name,[[case[index] for case in cases]],"RGBA32F")
              for index,name in enumerate(("sourceShare","pathsLight","inputSky"))]
    comparisons=[]
    for clarity in (.5,1.0,2.0):
        pair=runner.pair("composite1",dict(WATER_OPTICS=1,WATER_CLARITY=clarity,IRIS_FEATURE_PER_BUFFER_BLENDING=True),source)
        image=runner.render("M1-pure-transport",pair,len(cases),1,textures)
        expected=[[analytical_transport(a[:3],a[3],b[0],b[1],b[2],b[3],c[:3],clarity)+(1.,)
                   for a,b,c in cases]]
        comparisons.append(compare(image,expected,"transport clarity "+str(clarity),
                                   absolute=2e-6,relative=2e-5))
        require(all(image[0][index]==(0.,0.,0.,1.) for index in range(12,18)),
                "Unlit cave acquired radiance")
    return dict(configurations=3,samples=len(cases)*3,comparisons=comparisons,
                scope="Actual transport helper versus independently written double-precision formula")


def smooth(a, b, value):
    t=min(1.,max(0.,(value-a)/(b-a)))
    return t*t*(3.-2.*t)


def slab_scene(width=13, height=9, depth=2., pitch=65., sky=1., block=0.,
               source_rgb=(.6,.4,.2), share=.65, sun_cosine=1.):
    """Analytical horizontal interface and bed, with independently projected depths.

    Scene radiance is authored linear RGB; these are synthetic MRT inputs, not
    claimed output of Minecraft's terrain renderer or a solved light transport.
    """
    angle=math.radians(pitch); sine,cosine=math.sin(angle),math.cos(angle)
    rotation=((1.,0.,0.),(0.,cosine,-sine),(0.,sine,cosine))
    inv_rotation=tuple(tuple(rotation[j][i] for j in range(3)) for i in range(3))
    model=tuple(tuple(inv_rotation[r][c] if r<3 and c<3 else float(r==c==3)
                      for c in range(4)) for r in range(4))
    projection=tuple(tuple(map(f32,row)) for row in perspective_matrix(50.,width/height,.05,128.))
    inverse=tuple(tuple(map(f32,row)) for row in inverse_matrix(projection))
    up=tuple(map(f32,(0.,cosine,sine)))
    up_length=math.sqrt(sum(v*v for v in up))
    unit_up=tuple(v/up_length for v in up)
    light=(math.sqrt(max(0.,1.-sun_cosine*sun_cosine)),unit_up[1]*sun_cosine,unit_up[2]*sun_cosine)
    textures={name:[] for name in ("colortex0","colortex5","colortex6","colortex7","colortex8","colortex9","depthtex0","depthtex1")}
    front_positions=[];back_positions=[]
    count_rgb=(f32(1/255),round(block*255)/255,round(sky*255)/255,0.)
    for y in range(height):
        rows={name:[] for name in textures};front_row=[];back_row=[]
        for x in range(width):
            ray=((2*(x+.5)/width-1)/projection[0][0],(2*(y+.5)/height-1)/projection[1][1],-1.)
            length=math.sqrt(sum(v*v for v in ray));ray=tuple(v/length for v in ray)
            world_ray=tuple(sum(a*b for a,b in zip(row,ray)) for row in inv_rotation)
            require(world_ray[1]<-.01,"Slab fixture ray must face the water")
            front_t=-4./world_ray[1];back_t=(-4.-depth)/world_ray[1]
            front=tuple(v*front_t for v in ray);back=tuple(v*back_t for v in ray)
            def window_z(point):
                clip_z=sum(a*b for a,b in zip(projection[2],point+(1.,)))
                clip_w=sum(a*b for a,b in zip(projection[3],point+(1.,)))
                return f32(.5+.5*clip_z/clip_w)
            front_z,back_z=window_z(front),window_z(back)
            world_x=world_ray[0]*back_t;world_z=world_ray[2]*back_t
            checker=.7 if (math.floor(world_x)+math.floor(world_z))%2 else 1.
            rgb=tuple(half(value*checker) for value in source_rgb)
            native=tuple(f32(.55*w+.45*b) for w,b in zip((.045,.11,.13),rgb))+(f32(.375+(x+y)%3*.125),)
            rows["colortex0"].append(native)
            rows["colortex5"].append(rgb+(1.,))
            rows["colortex6"].append((back_z,0.,0.,1.))
            rows["colortex7"].append(up+(front_z,))
            rows["colortex8"].append(count_rgb)
            rows["colortex9"].append((half(share),0.,0.,1.))
            rows["depthtex0"].append((front_z,0.,0.,1.))
            rows["depthtex1"].append((back_z,0.,0.,1.))
            uv=((x+.5)/width,(y+.5)/height)
            front_row.append(reconstruct_view(uv,front_z,inverse))
            back_row.append(reconstruct_view(uv,back_z,inverse))
        for name in textures:textures[name].append(rows[name])
        front_positions.append(front_row);back_positions.append(back_row)
    uniforms=[
        ("gbufferProjection","m4",matrix_uniform(projection)),
        ("gbufferProjectionInverse","m4",matrix_uniform(inverse)),
        ("gbufferModelViewInverse","m4",matrix_uniform(model)),
        ("upPosition","f3",up),("shadowLightPosition","f3",light),
        ("sunPosition","f3",light),("fogColor","f3",(.55,.65,.7)),
        ("hasSkylight","i1",(1,)),("hasCeiling","i1",(0,)),("isEyeInWater","i1",(0,)),
        ("blindness","f1",(0.,)),("darknessFactor","f1",(0.,)),("rainStrength","f1",(0.,)),
        ("eyeBrightnessSmooth","i2",(240,240)),("cameraPositionInt","i3",(0,68,0)),
        ("cameraPositionFract","f3",(0.,0.,0.)),
    ]
    return dict(width=width,height=height,textures=textures,uniforms=uniforms,
                front=front_positions,back=back_positions,model=model,up=unit_up,light=light)


FORMATS={"colortex0":"RGBA32F","colortex5":"RGBA16F","colortex6":"R32F","colortex7":"RGBA32F",
         "colortex8":"RGBA8","colortex9":"R16F","depthtex0":"R32F","depthtex1":"R32F"}
FORMATS.update({"colortex1":"RGBA16","colortex11":"RGBA32F"})
BASE_OPTIONS=dict(WATER_OPTICS=1,FOG_ENABLED=0,WATER_REFLECTION_STRENGTH=0.0,
                  WATER_SCREEN_REFLECTIONS=0,SKY_STYLE=0)


def render_resolve(runner, scene, options=None, capability=True, label="M1-resolve"):
    options=dict(BASE_OPTIONS,**(options or {}))
    options["IRIS_FEATURE_PER_BUFFER_BLENDING"]=capability
    pair=runner.pair("composite1",options)
    inputs=scene["textures"]
    if options.get("WATER_REFRACTION",0)>0:
        from validate_gpu_water_planar import prepare_tiles
        inputs=prepare_tiles(runner,scene,options)
    textures=[(name,image,FORMATS[name]) for name,image in inputs.items()]
    # Optimizer may remove projection/reflection/fog bindings or the entire
    # opt-in branch. A separate changed-output assertion proves active runs.
    optional=list(inputs)+[u[0] for u in scene["uniforms"]]
    return runner.render(label,pair,scene["width"],scene["height"],textures,scene["uniforms"],optional=optional)


def slab_expected(scene, clarity=1., body=0):
    w,h=scene["width"],scene["height"]
    result=[]
    for y in range(h):
        row=[]
        for x in range(w):
            native=scene["textures"]["colortex0"][y][x]
            if x==0 or y==0 or x==w-1 or y==h-1:
                row.append(native);continue
            front,back=scene["front"][y][x],scene["back"][y][x]
            world_delta=tuple(sum(scene["model"][r][c]*(front[c]-back[c]) for c in range(3)) for r in range(3))
            drop=world_delta[1];distance=math.dist(front,back)
            eye_length=math.sqrt(sum(v*v for v in front))
            eye_cosine=sum(-v/eye_length*u for v,u in zip(front,scene["up"]))
            confidence=smooth(0,2,min(x+.5,y+.5,w-x-.5,h-y-.5))*smooth(.03,.12,eye_cosine)
            confidence*=smooth(.001,.03,drop)*(1.-smooth(48,64,distance))
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                gap=abs(scene["back"][ny][nx][2]-back[2])
                confidence*=1.-smooth(max(.25,distance*.05),max(.5,distance*.15),gap)
            sun_cosine=max(0.,min(1.,sum(a*b for a,b in zip(scene["light"],scene["up"]))))
            light_distance=drop/math.sqrt(1.-(1.-sun_cosine*sun_cosine)/(1.333**2))
            tex=scene["textures"]
            rgb=analytical_transport(tex["colortex5"][y][x][:3],tex["colortex9"][y][x][0],
                distance,light_distance,tex["colortex8"][y][x][1],tex["colortex8"][y][x][2],(0.,0.,0.),clarity,body)
            row.append(tuple(a*(1-confidence)+b*confidence for a,b in zip(native[:3],rgb))+(native[3],))
        result.append(row)
    return result


def resolve_tests(runner):
    comparisons=[];samples=0;changed=0
    for label,depth,share,block,sky,source,sun in (
        ("shallow",.25,.65,0.,1.,(.6,.4,.2),1.),
        ("medium",2.,.65,0.,1.,(.6,.4,.2),1.),
        ("deep",12.,.65,0.,1.,(.6,.4,.2),1.),
        ("low-sun",4.,.8,0.,1.,(.6,.4,.2),.05),
        ("moon",4.,.3,0.,1.,(.025,.035,.065),.6),
        ("cave-lamp",8.,0.,1.,0.,(.4,.16,.04),1.),
        ("cave-black",8.,0.,0.,0.,(0.,0.,0.),1.),
        ("no-direct",4.,0.,.5,.25,(.6,.4,.2),1.),
    ):
        scene=slab_scene(depth=depth,share=share,block=block,sky=sky,source_rgb=source,sun_cosine=sun)
        if label=="cave-black":
            scene["textures"]["colortex0"]=[[(0.,0.,0.,p[3]) for p in row] for row in scene["textures"]["colortex0"]]
        image=render_resolve(runner,scene,label=label)
        expected=slab_expected(scene)
        comparisons.append(compare(image,expected,label,absolute=4e-5,relative=4e-4))
        require(all(a[3]==b[3] for ar,br in zip(image,scene["textures"]["colortex0"]) for a,b in zip(ar,br)),
                label+": raw alpha changed")
        active=sum(a[:3]!=b[:3] for ar,br in zip(image,scene["textures"]["colortex0"]) for a,b in zip(ar,br))
        require(active==0 if label=="cave-black" else active>30,
                label+": unexpected active-route change count")
        if label=="cave-black":
            require(all(image[y][x][:3]==(0.,0.,0.) for y in range(2,scene["height"]-2) for x in range(2,scene["width"]-2)),
                    "Actual composite generated unlit cave radiance")
        changed+=active;samples+=scene["width"]*scene["height"]
    # Exact bypass: disabled and unsupported configurations cannot touch scene alpha/RGB.
    scene=slab_scene()
    bypass=[]
    for label,options,capability in (
        ("optics-off",{"WATER_OPTICS":0},True),("no-independent-blend",{},False),
        ("water-style-off",{"WATER_STYLE":0},True),("display-space",{"SCENE_COLOR_MODE":0},True),
        ("debug-view",{"DEBUG_VIEW":7},True)):
        image=render_resolve(runner,scene,options,capability,label)
        compare(image,scene["textures"]["colortex0"],label);bypass.append(label)
    # These fields are independent synthetic inputs, intentionally violating one
    # ownership/depth contract at a time. Actual producer writes are tested separately.
    invalid=[]
    for label,key,fn in (
        ("no-water-count","colortex8",lambda p:(0.,p[1],p[2],0.)),
        ("two-water-layers","colortex8",lambda p:(2/255,p[1],p[2],0.)),
        ("overlay-blocker","colortex8",lambda p:(1.,p[1],p[2],0.)),
        ("count-alpha-invalid","colortex8",lambda p:(p[0],p[1],p[2],1.)),
        ("zero-normal","colortex7",lambda p:(0.,0.,0.,p[3])),
        ("nonunit-normal","colortex7",lambda p:(p[0],p[1]*.5,p[2]*.5,p[3])),
        ("nearer-late-depth","depthtex0",lambda p:(p[0]-.001,0.,0.,1.)),
        ("cleared-late-depth","depthtex0",lambda p:(1.,0.,0.,1.)),
        ("invalid-direct-share","colortex9",lambda p:(-1.,0.,0.,1.)),
        ("missing-snapshot","colortex5",lambda p:(p[0],p[1],p[2],0.)),
        ("unmatched-scene-depth","colortex6",lambda p:(p[0]-.001,0.,0.,1.)),
        ("no-bottom","colortex6",lambda p:(1.,0.,0.,1.)),
    ):
        clone=dict(scene);clone["textures"]=dict(scene["textures"])
        clone["textures"][key]=[[fn(p) for p in row] for row in scene["textures"][key]]
        image=render_resolve(runner,clone,label=label)
        compare(image,scene["textures"]["colortex0"],label);invalid.append(label)
    for label,key,value in (("underwater","isEyeInWater",(1,)),("ceiling-dimension","hasCeiling",(1,)),
                            ("no-skylight-dimension","hasSkylight",(0,)),
                            ("zero-up","upPosition",(0.,0.,0.)),("zero-light","shadowLightPosition",(0.,0.,0.))):
        clone=dict(scene);clone["uniforms"]=[(n,k,value if n==key else v) for n,k,v in scene["uniforms"]]
        image=render_resolve(runner,clone,label=label)
        compare(image,scene["textures"]["colortex0"],label);invalid.append(label)
    return dict(analytical_cases=len(comparisons),pixels=samples,changed_pixels=changed,
                comparisons=comparisons,exact_disabled_cases=bypass,exact_invalid_cases=invalid,
                scope="Actual full-resolution composite with declared mixed-format source textures; independent plane/path oracle")


def comparison_plate(runner,path):
    width,height=128,72
    depths=(.5,2.,8.)
    lighting=(
        ("DAY",(.6,.5,.35),.65,0.,1.,1.),
        ("MOON",(.025,.035,.065),.3,0.,1.,-.65),
        ("CAVE LAMP",(.4,.16,.04),0.,1.,0.,1.),
    )
    panel_height=height+20
    sheet=[[(21,25,32)]*(width*6) for _ in range(panel_height*3+21)]
    draw_text(sheet,5,6,"SYNTHETIC NATIVE COMPOSITE - OFF / ON - NO IRIS OR FPS TEST")
    cases=[]
    for row,(name,rgb,share,block,sky,sun) in enumerate(lighting):
        for column,depth in enumerate(depths):
            scene=slab_scene(width,height,depth,55.,sky,block,rgb,share,abs(sun))
            scene["uniforms"]=[(n,k,tuple(-v for v in values) if n=="sunPosition" and sun<0 else values)
                               for n,k,values in scene["uniforms"]]
            for enabled in (0,1):
                # Actual palette/Fresnel enabled here; numerical oracle cases
                # separately isolate transport with reflection and fog disabled.
                options=dict(WATER_OPTICS=enabled,SKY_STYLE=1,WATER_REFLECTION_STRENGTH=.5)
                result=render_resolve(runner,scene,options,label="plate-"+name)
                display=runner.render("plate-final",runner.pair("final"),width,height,[("colortex0",result,"RGBA32F")])
                x=(column*2+enabled)*width;y=21+row*panel_height
                draw_text(sheet,x+3,y+5,name+" "+str(depth)+" M "+("ON" if enabled else "OFF"))
                for dy,pixels in enumerate(display_rows(display)):sheet[y+20+dy][x:x+width]=pixels
            cases.append(dict(lighting=name,vertical_depth_meters=depth,resolution=[width,height],
                              camera_pitch_degrees=55.,source_radiance=rgb,direct_share=share,
                              local_block_light=block,local_sky_light=sky))
    png(path,sheet)
    return dict(path=str(path),panels=18,cases=cases,
                scope="Actual composite and final programs; analytical flat water/bed and authored checker radiance, synthetic native-alpha fallback; no geometry displacement or game screenshot")



def reflection_tests(runner):
    authored=make_scene(35.)
    uniforms={n:(n,k,v) for n,k,v in authored["uniforms"]}
    projection_data=uniforms["gbufferProjection"][2]
    projection=tuple(tuple(projection_data[c*4+r] for c in range(4)) for r in range(4))
    up=uniforms["upPosition"][2]
    eye_height=authored["eye"][1]
    textures={name:[] for name in FORMATS if name not in ("colortex1","colortex11")}
    for y in range(HEIGHT):
        rows={name:[] for name in textures}
        for x in range(WIDTH):
            mask=bool(authored["mask"][y][x][0])
            ray=((2*(x+.5)/WIDTH-1)/projection[0][0],(2*(y+.5)/HEIGHT-1)/projection[1][1],-1.)
            divisor=sum(a*b for a,b in zip(up,ray))
            front=tuple(v*(-eye_height/divisor) for v in ray)
            raw=f32(.5+.5*(projection[2][2]*front[2]+projection[2][3])/(-front[2]))
            source=authored["color"][y][x];depth=authored["depth"][y][x]
            native=tuple(f32(.55*a+.45*b) for a,b in zip((.045,.11,.13),source[:3]))+(f32(.6),)
            rows["colortex0"].append(native if mask else source)
            rows["colortex5"].append(source)
            rows["colortex6"].append(depth);rows["depthtex1"].append(depth)
            rows["colortex7"].append(tuple(up)+(raw,) if mask else (0.,0.,0.,0.))
            rows["colortex8"].append((1/255,0.,1.,0.) if mask else (0.,0.,0.,0.))
            rows["colortex9"].append((.25,0.,0.,1.))
            rows["depthtex0"].append((raw,0.,0.,1.) if mask else depth)
        for name in textures:textures[name].append(rows[name])
    names=("gbufferProjection","gbufferProjectionInverse","gbufferModelViewInverse",
           "upPosition","sunPosition","fogColor","hasSkylight","hasCeiling","isEyeInWater",
           "blindness","darknessFactor","rainStrength","eyeBrightnessSmooth","cameraPositionInt","cameraPositionFract")
    scene=dict(width=WIDTH,height=HEIGHT,textures=textures,uniforms=[uniforms[n] for n in names]+
               [("shadowLightPosition","f3",uniforms["sunPosition"][2])])
    off=render_resolve(runner,scene,dict(WATER_REFLECTION_STRENGTH=.5),label="SSR-off")
    on=render_resolve(runner,scene,dict(WATER_REFLECTION_STRENGTH=.5,WATER_SCREEN_REFLECTIONS=1),label="SSR-on")
    changed=sum(a!=b for ar,br in zip(off,on) for a,b in zip(ar,br))
    require(changed>100,"Real composite SSR route did not change sufficient pool pixels")
    invalid=[]
    for label,share in (("early-overlay",-1.),("nonfinite-share",float("nan")),("excess-share",1.5)):
        clone=dict(scene);clone["textures"]=dict(textures)
        clone["textures"]["colortex9"]=[
            [(.25 if authored["mask"][y][x][0] else share,0.,0.,1.) for x in range(WIDTH)]
            for y in range(HEIGHT)]
        result=render_resolve(runner,clone,dict(WATER_REFLECTION_STRENGTH=.5,WATER_SCREEN_REFLECTIONS=1),label=label)
        compare(result,off,"SSR invalid hit share: "+label)
        invalid.append(label)
    return dict(changed_scene_reflection_pixels=changed,invalid_hit_share_exact_fallbacks=invalid,
                input="W3 authored plane/AABB snapshot. Actual M1 composite traces visible opaque targets; invalid direct-share at hit rejects contaminated reflections.")


def reflected_fog_tests(runner):
    source="#version 330 compatibility\n"+expand(SHADERS/"lib/water_resolve.glsl")+"""
layout(location=0) out vec4 color;
void main(){
    float distance=gl_FragCoord.x-.5;
    color=vec4(waterReflectedAtmosphere(vec3(.4,.3,.2),vec3(0,0,-4),vec3(0,0,-4-distance)),1);
}
"""
    identity=tuple(tuple(float(r==c) for c in range(4)) for r in range(4))
    uniforms=[
        ("gbufferModelViewInverse","m4",matrix_uniform(identity)),("cameraPositionInt","i3",(0,64,0)),
        ("cameraPositionFract","f3",(0.,0.,0.)),("eyeBrightnessSmooth","i2",(240,240)),
        ("hasSkylight","i1",(1,)),("hasCeiling","i1",(0,)),("isEyeInWater","i1",(0,)),
        ("blindness","f1",(0.,)),("darknessFactor","f1",(0.,)),("rainStrength","f1",(0.,)),
        ("fogColor","f3",(.55,.65,.7)),
    ]
    comparisons=[]
    for enabled in (0,1):
        options=dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,SKY_STYLE=0,
                     FOG_ENABLED=enabled,FOG_DENSITY=.01,FOG_START=64.0,FOG_BASE_HEIGHT=64.0)
        image=runner.render("reflected-segment-fog",runner.pair("composite1",options,source),65,1,
                            uniforms=uniforms,optional=[u[0] for u in uniforms])
        atmosphere=tuple(((v+.055)/1.055)**2.4 for v in (.55,.65,.7))
        expected=[]
        for distance in range(65):
            t=math.exp(-distance*.01) if enabled else 1.
            expected.append(tuple(f32(a)*t+b*(1.-t) for a,b in zip((.4,.3,.2),atmosphere))+(1.,))
        comparisons.append(compare(image,[expected],"reflected air path "+str(enabled),absolute=3e-7,relative=3e-6))
        if enabled:require(image[0][1]!=image[0][0],"Reflected path wrongly inherited camera FOG_START")
    return dict(samples=130,comparisons=comparisons,
                scope="Actual reflected-segment helper, constant-height air path. Independent exponential fog reference; camera exemption deliberately 64 m.")

def transport_tests(runner,plate_path=None):
    result=dict(indexed_blending=indexed_blend_tests(runner),
                helper=helper_tests(runner),resolve=resolve_tests(runner),
                reflections=reflection_tests(runner),reflected_fog=reflected_fog_tests(runner))
    if plate_path:result["comparison_plate"]=comparison_plate(runner,plate_path)
    return result
