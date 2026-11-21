"""Actual post-water planar proof, independent geometry oracle and negative controls."""
import copy,math,struct
from validate_gpu import require
from validate_gpu_water_transport import FORMATS, slab_scene
from render_water_bench import dot

OPTIONS=dict(IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_OPTICS=1,FOG_ENABLED=0,
             WATER_SCREEN_REFLECTIONS=0,WATER_REFLECTION_STRENGTH=0.0,SKY_STYLE=0)

def prepare_tiles(runner,scene,settings):
    options=dict(OPTIONS,**settings)
    w,h=scene["width"],scene["height"]
    textures=dict(scene["textures"])
    if "colortex1" not in textures:
        require("up" in scene,"Authored geometry must provide actual bed normals")
        normal=tuple(.5+.5*v for v in scene["up"])+(1.,)
        textures["colortex1"]=[[normal]*w for _ in range(h)]
    uniforms=scene["uniforms"]
    if options.get("WATER_REFRACTION",0)>0:
        inputs=[(n,textures[n],FORMATS[n]) for n in ("colortex1","colortex5","colortex6","colortex7","colortex8","colortex9","depthtex0","depthtex1")]
        bounds=runner.render("actual-post-water-planar-proof",runner.pair("composite",options),max(1,w//8),max(1,h//8),
            inputs,uniforms,optional=[n for n,_,_ in uniforms]+[n for n,_,_ in inputs])
    else:
        bounds=[[(1e20,-1e20,1e20,-1e20)]*max(1,w//8) for _ in range(max(1,h//8))]
    textures["colortex11"]=bounds
    return textures

def inverse_point(scene,x,y,depth):
    m=next(v for n,k,v in scene["uniforms"] if n=="gbufferProjectionInverse")
    q=(2*(x+.5)/scene["width"]-1,2*(y+.5)/scene["height"]-1,2*depth-1,1.)
    v=[sum(m[c*4+r]*q[c] for c in range(4)) for r in range(4)]
    return tuple(a/v[3] for a in v[:3])
def bounds_oracle(scene,tx,ty):
    w,h=scene["width"],scene["height"];ox,oy=tx*8,ty*8
    if ox<1 or oy<1 or ox+8>=w or oy+8>=h:return None
    heights=[]
    for y in range(oy-1,oy+9):
        for x in range(ox-1,ox+9):
            a=inverse_point(scene,x,y,scene["textures"]["colortex7"][y][x][3])
            b=inverse_point(scene,x,y,scene["textures"]["colortex6"][y][x][0])
            heights.append((dot(a,scene["up"]),dot(b,scene["up"])))
    return min(a for a,b in heights),max(a for a,b in heights),min(b for a,b in heights),max(b for a,b in heights)
def valid(v):return v[0]<=v[1] and v[2]<=v[3]
def planar_tests(runner):
    count=0;maximum=0;cases=[]
    for pitch in (35.,55.,80.):
        for depth in (.05,.5,2.,8.):
            scene=slab_scene(48,32,depth,pitch)
            actual=prepare_tiles(runner,scene,dict(WATER_REFRACTION=1))["colortex11"]
            positives=0
            for ty,row in enumerate(actual):
                for tx,record in enumerate(row):
                    expected=bounds_oracle(scene,tx,ty)
                    require(valid(record)==(expected is not None),"Tile edge validity differs")
                    if expected is not None:
                        error=max(abs(a-b) for a,b in zip(record,expected));maximum=max(maximum,error)
                        require(error<.0005,"Analytical height interval mismatch")
                        positives+=1;count+=1
            require(positives==8,"Expected8 interior+halo tiles")
            cases.append(dict(pitch=pitch,depth=depth,valid_tiles=positives))
    scene=slab_scene(48,32,2.,55.)
    tests=[]
    # Pixel15 is outside tile2's8x8 interior but inside its one-pixel halo.
    for label,key,pixel,change in (
        ("halo-overlay","colortex8",(15,10),lambda p:(1.,p[1],p[2],0.)),
        ("interior-two-water","colortex8",(20,12),lambda p:(2/255,p[1],p[2],0.)),
        ("unresolved-early-color","colortex9",(20,12),lambda p:(-1.,0,0,1)),
        ("unmatched-opaque-depth","colortex6",(20,12),lambda p:(p[0]-.001,0,0,1)),
        ("front-slab","depthtex0",(20,12),lambda p:(p[0]-.001,0,0,1)),
        ("missing-snapshot","colortex5",(20,12),lambda p:(p[0],p[1],p[2],0)),
        ("nonwater-record","colortex7",(20,12),lambda p:(0,0,0,0)),
        ("nonfinite-share","colortex9",(20,12),lambda p:(float("nan"),0,0,1)),
    ):
        modified=copy.deepcopy(scene);x,y=pixel
        modified["textures"][key][y][x]=change(modified["textures"][key][y][x])
        actual=prepare_tiles(runner,modified,dict(WATER_REFRACTION=1))["colortex11"]
        require(not valid(actual[1][2]),label+" left affected tile valid")
        require(valid(actual[2][4]),label+" contaminated distant unaffected tile")
        tests.append(label)
    # Correctly matched but nonhorizontal opaque geometry is not a flat-pool proof.
    for label,normal in (("vertical-bed",(1.,.5,.5,1.)),("missing-bed-normal",(.5,.5,.5,0.))):
        modified=copy.deepcopy(scene)
        n=tuple(.5+.5*v for v in scene["up"])+(1.,)
        modified["textures"]["colortex1"]=[[n]*48 for _ in range(32)]
        modified["textures"]["colortex1"][12][20]=normal
        actual=prepare_tiles(runner,modified,dict(WATER_REFRACTION=1))["colortex11"]
        require(not valid(actual[1][2]),label+" was treated as horizontal")
        tests.append(label)
    # Height discontinuity with a consistent matched raw depth cannot hide behind metadata.
    modified=copy.deepcopy(scene);x,y=20,12
    m=next(v for n,k,v in scene["uniforms"] if n=="gbufferProjection")
    point=scene["back"][y][x];z=point[2]*.99
    shifted=struct.unpack("<f",struct.pack("<f",.5+.5*(m[10]*z+m[14])/-z))[0]
    modified["textures"]["colortex6"][y][x]=(shifted,0,0,1)
    modified["textures"]["depthtex1"][y][x]=(shifted,0,0,1)
    actual=prepare_tiles(runner,modified,dict(WATER_REFRACTION=1))["colortex11"]
    require(not valid(actual[1][2]),"Matched depth stair was accepted")
    tests.append("matched-bed-height-step")
    odd=slab_scene(41,29,2.,55.);actual=prepare_tiles(runner,odd,dict(WATER_REFRACTION=1))["colortex11"]
    require(len(actual)==3 and len(actual[0])==5,"Relative target size mismatch")
    for ty,row in enumerate(actual):
        for tx,pixel in enumerate(row):require(valid(pixel)==(bounds_oracle(odd,tx,ty) is not None),"Odd-size edge semantics")
    return dict(positive_cases=cases,independent_valid_intervals=count,max_interval_error=maximum,negative_controls=tests,odd_resolution=[41,29],actual_normal_storage="RGBA16_UNORM")
def combined_foam_tests(runner):
    """Real planar producer and resolve with the existing independently tested foam."""
    from validate_gpu_water_transport import render_resolve
    scene=slab_scene(96,64,2.,55.)
    scene['uniforms'].append(('frameTimeCounter','f1',[17.]))
    images={}
    for refraction,foam in ((0,0),(1,0),(1,1),(3,0),(3,1)):
        images[refraction,foam]=render_resolve(runner,scene,
            dict(WATER_REFRACTION=refraction,WATER_FOAM=foam,WATER_WAVE_STRENGTH=1.0,SHADOWS_ENABLED=False),
            label='planar and local foam')
    results=[]
    for mode in (1,3):
        base=images[0,0];optics=images[mode,0];foamed=images[mode,1]
        changed=sum(a!=b for ar,br in zip(base,optics) for a,b in zip(ar,br))
        foam_changed=sum(max(abs(a-b) for a,b in zip(p[:3],q[:3]))>1e-6
                         for ar,br in zip(optics,foamed) for p,q in zip(ar,br))
        require(changed>100,'Combined planar optical path inactive')
        require(foam_changed>10,'Existing foam inactive with planar transport')
        require(all(a[3]==b[3]==c[3] for ar,br,cr in zip(base,optics,foamed)
                    for a,b,c in zip(ar,br,cr)),'Combined planar foam changed alpha')
        require(all(math.isfinite(v) for row in foamed for pixel in row for v in pixel),'Combined nonfinite')
        results.append(dict(mode=mode,refraction_changed=changed,foam_changed=foam_changed,alpha_exact=True))
    return results
