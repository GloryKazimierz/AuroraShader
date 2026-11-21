"""M2 synthetic native reflection stability tests; no Minecraft or Iris execution."""
import json
import math


def footprint_tests(runner):
    from compile_glsl import SHADERS, expand
    from validate_gpu import compare, require
    from validate_gpu_depth import matrix_uniform
    from validate_water_waves import f32
    from validate_water_depth import perspective_matrix, inverse_matrix
    source = "#version 330 compatibility\n" + expand(SHADERS / "lib/water_reflection_filter.glsl") + """
uniform sampler2D queries;
uniform int useFilter;
layout(location=0) out vec4 color;
void main(){
    vec2 screen=texelFetch(queries,ivec2(gl_FragCoord.xy),0).xy;
    ivec2 size=textureSize(colortex6,0);
    ivec2 pixel=ivec2(floor(screen));
    float depth=texelFetch(colortex6,pixel,0).r;
    vec4 h=gbufferProjectionInverse*vec4(screen/vec2(size)*2.0-1.0,depth*2.0-1.0,1.0);
    vec3 nearest=texelFetch(colortex5,pixel,0).rgb;
    vec3 result=useFilter==0?nearest:waterFilteredReflectionRadiance(pixel,h.xyz/h.w,nearest);
    color=vec4(result,1.0);
}
"""
    width,height=64,48
    projection=tuple(tuple(map(f32,row)) for row in perspective_matrix(70,width/height,.05,128))
    inverse=tuple(tuple(map(f32,row)) for row in inverse_matrix(projection))
    pair=runner.pair("composite1",wrapper=source)
    results=[]
    for geometry in ("flat-x","flat-y","flat-corner","flat-slanted","depth-step","crease","constant","invalid-neighbor"):
        color=[];depth=[];share=[]
        for y in range(height):
            cr=[];dr=[];sr=[]
            for x in range(width):
                ray_x=(2*(x+.5)/width-1)/projection[0][0]
                z=-10.
                if geometry=="flat-slanted":
                    ray_y=(2*(y+.5)/height-1)/projection[1][1]
                    z=-10./(1.+.5*ray_x+.3*ray_y)
                if geometry=="depth-step" and x>=32:z=-13.
                if geometry=="crease":z=-10./(1.+(1. if x>=32 else -1.)*ray_x)
                window=f32(.5+.5*(projection[2][2]*z+projection[2][3])/(-z))
                lit=(x>=32) if geometry!="flat-y" else (y>=24)
                if geometry=="flat-corner":lit=x>=32 and y>=24
                rgb=(8.,2.,.5) if lit else (0.,0.,0.)
                if geometry=="constant":rgb=(.25,.5,1.)
                cr.append(rgb+(1.,));dr.append((window,0.,0.,1.));sr.append((0.,0.,0.,1.))
            color.append(cr);depth.append(dr);share.append(sr)
        if geometry=="invalid-neighbor":
            share=[[(-1. if x>=32 else 0.,0.,0.,1.) for x in range(width)] for _ in range(height)]
        query=[];truth=[]
        for frame in range(64):
            offset=.45*math.sin(2*math.pi*(frame+.3)/32.)
            x,y=(32.+offset,20.5)
            if geometry=="flat-y":x,y=20.5,24.+offset
            if geometry=="flat-corner":x,y=32.+offset,24.-offset
            if geometry=="invalid-neighbor":x=31.9
            query.append((f32(x),f32(y),0.,1.))
            fraction=min(1.,max(0.,offset+.5))
            if geometry=="flat-corner":fraction*=min(1.,max(0.,.5-offset))
            if geometry in ("depth-step","crease","invalid-neighbor"):
                fraction=float(x>=32)
            truth.append((.25,.5,1.,1.) if geometry=="constant" else tuple(c*fraction for c in (8.,2.,.5))+(1.,))
        textures=[("colortex5",color,"RGBA16F"),("colortex6",depth,"R32F"),
                  ("depthtex1",depth,"R32F"),("colortex9",share,"R16F"),("queries",[query],"RGBA32F")]
        common=[("gbufferProjection","m4",matrix_uniform(projection)),
                ("gbufferProjectionInverse","m4",matrix_uniform(inverse))]
        images=[]
        for enabled in (0,1):
            images.append(runner.render("M2-footprint-"+geometry,pair,len(query),1,textures,
                                       common+[("useFilter","i1",(enabled,))]))
        comparison=compare(images[1],[truth],"M2 footprint "+geometry,absolute=7e-5,relative=2e-5)
        metrics={}
        if geometry.startswith("flat"):
            for name,image in zip(("nearest","filtered"),images):
                values=[p[0] for p in image[0]]
                metrics[name+"_rms_error"]=math.sqrt(sum((a-b[0])**2 for a,b in zip(values,truth))/len(values))
                metrics[name+"_max_frame_step"]=max(abs(a-b) for a,b in zip(values,values[1:]))
            require(metrics["filtered_rms_error"]<metrics["nearest_rms_error"]*.01,"No measured footprint error reduction")
            if metrics["nearest_max_frame_step"] > 0.0:
                require(metrics["filtered_max_frame_step"]<metrics["nearest_max_frame_step"]*.25,"Bright-edge spikes did not decrease")
            else:
                # Along this corner sweep nearest loses ALL subpixel coverage.
                # Correct filtering recovers variation, so zero spikes is not quality.
                require(geometry=="flat-corner" and metrics["filtered_max_frame_step"]>0.0,
                        "Corner coverage detail was not recovered")
                metrics["nearest_lost_subpixel_detail"]=True
        results.append(dict(scene=geometry,comparison=comparison,**metrics))
        print("PASS: M2 footprint "+geometry+" "+json.dumps(metrics),flush=True)
    return dict(cases=results,frames_per_case=64,reference="Independent unit-pixel box integral of a moving step/corner; depth steps and normal creases remain unfiltered")



def classification_tests(runner):
    from compile_glsl import SHADERS, expand
    from validate_gpu import require
    from validate_gpu_depth import matrix_uniform
    from validate_water_screen_reflection import trace_fixtures
    source="#version 330 compatibility\n#define IRIS_FEATURE_PER_BUFFER_BLENDING\n"+expand(SHADERS/"lib/water_optics_settings.glsl")+"\n"+expand(SHADERS/"lib/water_screen_reflection.glsl")+"""
uniform sampler2D origins, directions;
layout(location=0) out vec4 color;
void main(){
    ivec2 p=ivec2(gl_FragCoord.xy), hitPixel;
    vec3 point,radiance;float distance,confidence;int steps,outcome;
    bool hit=traceWaterSceneClassified(texelFetch(origins,p,0).xyz,texelFetch(directions,p,0).xyz,
                                      hitPixel,point,radiance,distance,confidence,steps,outcome);
    color=vec4(float(outcome),hit?1.0:0.0,confidence,float(steps));
}
"""
    by_name={f['name']:f for f in trace_fixtures()}
    cases=[]
    for name,expected in (("unknown-occluder",2),("diagonal-unknown-pixel",2),
                          ("unknown-sky-gap",1),("diagonal-sky-pixel",1),
                          ("invalid-alpha",3),("invalid-depth",3),("valid-black",1)):
        cases.append((name,by_name[name],expected))
    sky=dict(by_name['unknown-occluder']);w=len(sky['depth'][0]);h=len(sky['depth'])
    sky['color']=[[(0.,0.,0.,0.)]*w for _ in range(h)]
    sky['depth']=sky['opaque_depth']=[[1.]*w for _ in range(h)]
    cases.append(('observed-sky-still-unresolved',sky,0))
    results=[]
    pair=runner.pair('composite1',dict(WATER_OPTICS=1,WATER_REFLECTION_STEPS=128),source)
    for name,fixture,want in cases:
        textures=[('colortex5',fixture['color'],'RGBA16F'),
                  ('colortex6',[[(v,0.,0.,1.) for v in row] for row in fixture['depth']],'R32F'),
                  ('depthtex1',[[(v,0.,0.,1.) for v in row] for row in fixture['opaque_depth']],'R32F'),
                  ('origins',[[tuple(q['origin'])+(1.,) for q in fixture['queries']]],'RGBA32F'),
                  ('directions',[[tuple(q['direction'])+(1.,) for q in fixture['queries']]],'RGBA32F')]
        uniforms=[('gbufferProjection','m4',matrix_uniform(fixture['projection'])),
                  ('gbufferProjectionInverse','m4',matrix_uniform(fixture['inverse_projection']))]
        image=runner.render('M2-classification-'+name,pair,len(fixture['queries']),1,textures,uniforms)
        require(all(pixel[0]==want for pixel in image[0]),name+': wrong classified outcome '+str(image))
        require(all(pixel[1]==float(want==1) for pixel in image[0]),name+': hit classification differs')
        results.append(dict(scene=name,outcome=want,queries=len(image[0])))
    print('PASS: M2 eight classified ray/known-occluder/invalid/unresolved fixtures',flush=True)
    return results


def roof_scene(kind):
    from validate_gpu import half
    from validate_water_waves import f32
    import render_water_bench as bench
    old_size=bench.WIDTH,bench.HEIGHT
    width,height=128,72
    try:
        bench.WIDTH,bench.HEIGHT=width,height
        authored=bench.make_scene(20.)
    finally:
        bench.WIDTH,bench.HEIGHT=old_size
    uniforms={n:(n,k,v) for n,k,v in authored['uniforms']}
    def matrix(name):
        values=uniforms[name][2]
        return tuple(tuple(values[c*4+r] for c in range(4)) for r in range(4))
    projection=matrix('gbufferProjection');model=matrix('gbufferModelViewInverse')
    up=uniforms['upPosition'][2];eye=authored['eye'];roof_y=eye[1]+2.5
    names=('colortex0','colortex5','colortex6','colortex7','colortex8','colortex9','depthtex0','depthtex1')
    textures={name:[] for name in names}
    roof_count=0
    for y in range(height):
        rows={name:[] for name in names}
        for x in range(width):
            ray=((2*(x+.5)/width-1)/projection[0][0],(2*(y+.5)/height-1)/projection[1][1],-1.)
            world_ray=tuple(sum(model[r][c]*ray[c] for c in range(3)) for r in range(3))
            color=authored['color'][y][x];depth=authored['depth'][y][x]
            raw_depth=depth;share=0.25
            if world_ray[1]>0:
                roof_count+=1
                distance=(roof_y-eye[1])/world_ray[1]
                point=tuple(v*distance for v in ray)
                roof_z=f32(.5+.5*(projection[2][2]*point[2]+projection[2][3])/(-point[2]))
                color=(0.,0.,0.,0.);depth=(1.,0.,0.,1.);raw_depth=depth
                if kind=='unknown' and 0.0<=roof_z<1.0:raw_depth=(roof_z,0.,0.,1.)
                if kind=='contaminated' and 0.0<=roof_z<1.0:
                    color=(half(.02),half(.03),half(.04),1.)
                    depth=raw_depth=(roof_z,0.,0.,1.);share=-1.
            mask=bool(authored['mask'][y][x][0])
            divisor=sum(a*b for a,b in zip(up,ray))
            front=tuple(v*(-eye[1]/divisor) for v in ray)
            front_z=f32(.5+.5*(projection[2][2]*front[2]+projection[2][3])/(-front[2]))
            native=tuple(f32(.55*a+.45*b) for a,b in zip((.045,.11,.13),color[:3]))+(f32(.6),)
            rows['colortex0'].append(native if mask else color)
            rows['colortex5'].append(color);rows['colortex6'].append(depth);rows['depthtex1'].append(raw_depth)
            rows['colortex7'].append(tuple(up)+(front_z,) if mask else (0.,0.,0.,0.))
            rows['colortex8'].append((1/255,0.,64/255,0.) if mask else (0.,0.,0.,0.))
            rows['colortex9'].append((share,0.,0.,1.))
            rows['depthtex0'].append((front_z,0.,0.,1.) if mask else raw_depth)
        for name in names:textures[name].append(rows[name])
    used=('gbufferProjection','gbufferProjectionInverse','gbufferModelViewInverse','upPosition','sunPosition',
          'fogColor','hasSkylight','hasCeiling','isEyeInWater','blindness','darknessFactor','rainStrength',
          'eyeBrightnessSmooth','cameraPositionInt','cameraPositionFract')
    return dict(width=width,height=height,textures=textures,roof_pixels=roof_count,
                uniforms=[uniforms[n] for n in used]+[('shadowLightPosition','f3',uniforms['sunPosition'][2])])


def cave_fallback_tests(runner):
    from compile_glsl import SHADERS, expand
    from validate_gpu import require
    import validate_gpu_water_transport as m1
    classifier="#version 330 compatibility\n#define IRIS_FEATURE_PER_BUFFER_BLENDING\n"+expand(SHADERS/'lib/water_resolve.glsl')+"""
layout(location=0) out vec4 color;
void main(){
    ivec2 pixel=ivec2(gl_FragCoord.xy),size=textureSize(colortex7,0);
    vec4 surface=texelFetch(colortex7,pixel,0);
    color=vec4(-1,0,0,0);
    if(dot(surface.xyz,surface.xyz)<.9)return;
    vec3 start;
    if(!waterTraceUnproject(pixel,surface.a,size,start))return;
    vec3 up=celestialUnit(upPosition);
    vec3 reflected=reflect(celestialUnit(start),normalize(surface.xyz));
    ivec2 hitPixel;vec3 point,radiance;float distance,confidence;int steps,outcome;
    bool hit=traceWaterSceneClassified(start+up*.01,reflected,hitPixel,point,radiance,distance,confidence,steps,outcome);
    color=vec4(float(outcome),hit?1:0,hit?texelFetch(colortex9,hitPixel,0).r:0.0,float(steps));
}
"""
    options=dict(WATER_OPTICS=1,SKY_STYLE=1,FOG_ENABLED=0,WATER_SCREEN_REFLECTIONS=1,WATER_REFLECTION_STRENGTH=.5)
    pair=runner.pair('composite1',options,classifier)
    all_images={};records=[]
    for kind in ('unknown','contaminated','open'):
        scene=roof_scene(kind)
        classifications=runner.render('M2-roof-classification-'+kind,pair,scene['width'],scene['height'],
            [(n,img,m1.FORMATS[n]) for n,img in scene['textures'].items()],scene['uniforms'],
            optional=list(scene['textures'])+[u[0] for u in scene['uniforms']])
        transmitted=m1.render_resolve(runner,scene,dict(options,WATER_REFLECTION_STRENGTH=0.),label='M2-transmission-'+kind)
        reflected=m1.render_resolve(runner,scene,options,label='M2-reflection-'+kind)
        known=2 if kind=='unknown' else 1
        checked=0;worst=0.
        if kind!='open':
            for y in range(scene['height']):
                for x in range(scene['width']):
                    if classifications[y][x][0]!=known:continue
                    if kind=='contaminated' and classifications[y][x][2]>=0.0:continue
                    # Count only pixels actually owned by the compositor.
                    if transmitted[y][x][:3]==scene['textures']['colortex0'][y][x][:3]:continue
                    error=max(abs(a-b) for a,b in zip(reflected[y][x],transmitted[y][x]))
                    require(error<=2e-6,kind+': known roof leaked analytic sky at '+str((x,y,error)))
                    worst=max(worst,error);checked+=1
            require(checked>30,kind+': fixture did not exercise enough owned roof reflections')
        records.append(dict(kind=kind,known_opaque_pixels=checked,max_sky_leak_error=worst,visible_roof_pixels=scene['roof_pixels']))
        all_images[kind]=(classifications,transmitted,reflected)
        print('PASS: M2 actual composite roof '+kind+' known owned pixels '+str(checked),flush=True)
    blocked=all_images['unknown'];open_scene=all_images['open']
    paired=0;difference=0.
    for y in range(len(blocked[0])):
        for x in range(len(blocked[0][y])):
            if blocked[0][y][x][0]==2 and open_scene[0][y][x][0]==0:
                change=max(abs(a-b) for a,b in zip(open_scene[2][y][x][:3],open_scene[1][y][x][:3]))
                if change>1e-5:paired+=1;difference=max(difference,change)
    require(paired>30,'Roof/open pair did not discriminate known blockage from unresolved sky fallback')
    return dict(cases=records,paired_opaque_vs_unresolved_pixels=paired,max_removed_false_sky_change=difference,
                scope='Actual composite, analytical horizontal roof above the camera. Local sky access64/255 in both cases; unresolved exits are not proof of open sky.')


def slope_variance_audit():
    """Phase/tile mean only: independent resolved-energy quadrature, not a BRDF."""
    modes=[(11,3,.06,10),(4,-9,.04,-13),(7,13,.03,7),
           (49,19,.006,24),(-83,31,.0035,-31),(151,97,.0015,43)]
    signed={(sign*x%37,sign*z%41) for x,z,_,_ in modes for sign in (-1,1)}
    assert len(signed)==12 and (0,0) not in signed
    def weight(x,z,dx,dy):
        q=[(x*d[0]+z*d[1])/128 for d in (dx,dy)]
        f=max(map(abs,q))
        if f>=.5:return 0.
        a=max(0.,min(1.,(f-.25)/.25))
        return math.prod(1. if abs(v)<1e-14 else math.sin(math.pi*v)/(math.pi*v) for v in q)*(1-a*a*(3-2*a))
    records=[]
    for dx,dy in [((.25,0),(0,.25)),((1,.3),(-.2,.5)),((8,0),(0,8))]:
        weights=[weight(x,z,dx,dy) for x,z,_,_ in modes]
        for strength in (.3,1.):
            analytic=.5*strength**2*sum(a*a*(2*math.pi/128)**2*(x*x+z*z)*(1-f*f)
                                      for (x,z,a,_),f in zip(modes,weights))
            measured=0.
            for iz in range(41):
                for ix in range(37):
                    raw=[0.,0.];resolved=[0.,0.]
                    for (x,z,a,h),f in zip(modes,weights):
                        c=strength*a*(2*math.pi/128)*math.cos(2*math.pi*(x*ix/37+z*iz/41+h*13.4/200))
                        for axis,k in enumerate((x,z)):
                            raw[axis]+=c*k;resolved[axis]+=c*k*f
                    measured+=sum(v*v for v in raw)-sum(v*v for v in resolved)
            measured/=37*41
            assert abs(measured-analytic)<1e-15
            records.append(dict(dx=dx,dy=dy,strength=strength,analytic=analytic,
                                quadrature=measured,error=abs(measured-analytic)))
    full=.5*sum(a*a*(2*math.pi/128)**2*(x*x+z*z) for x,z,a,_ in modes)
    return dict(scope='Exact fixed-affine-footprint tile/phase mean; not instantaneous local variance or implemented roughness.',
                modes=len(modes),quadrature_grid=[37,41],cases=records,
                full_unresolved_variance_at_strength1=full,
                max_absolute_error=max(r['error'] for r in records))


def roof_plate(runner,path):
    """Compare the real, pinned M1 and current M2 resolve on identical roof inputs."""
    from functools import lru_cache
    from io import BytesIO
    import re
    import subprocess
    from zipfile import ZipFile
    from compile_glsl import ROOT
    from validate_gpu_water_transport import FORMATS
    from render_water_bench import png,display_rows,draw_text
    base='7c32ba602a104efcfb9a6067b03fe207ffe3e3f8'
    with ZipFile(BytesIO(subprocess.check_output(['git','-C',str(ROOT),'archive','--format=zip',base,'shaders']))) as tree:
        @lru_cache(maxsize=None)
        def previous(name):
            return re.sub(r'^#include "([^"]+)"\s*$',lambda m:previous(m[1].lstrip('/')),
                          tree.read('shaders/'+name).decode('utf-8'),flags=re.M)
        previous_source=previous('composite.fsh')
    options=dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,
                 FOG_ENABLED=0,WATER_SCREEN_REFLECTIONS=1,WATER_REFLECTION_STRENGTH=.5)
    pairs=[runner.pair('composite1',options,previous_source),runner.pair('composite1',options)]
    width,height=128,72
    sheet=[[(18,24,30)]*(width*3) for _ in range((height+18)*3+20)]
    draw_text(sheet,4,6,'M1 / M2 / DISPLAY DELTA X12    SYNTHETIC ROOF')
    changes={}
    for r,kind in enumerate(('unknown','contaminated','open')):
        scene=roof_scene(kind)
        inputs=[(name,tex,FORMATS[name]) for name,tex in scene['textures'].items()]
        outputs=[]
        for pair in pairs:
            pixels=runner.render('roof comparison',pair,width,height,inputs,scene['uniforms'],
                                 optional=list(scene['textures'])+[u[0] for u in scene['uniforms']])
            display=runner.render('roof final',runner.pair('final'),width,height,[('colortex0',pixels,'RGBA32F')])
            outputs.append(display_rows(display))
        a,b=outputs
        delta=[[tuple(min(255,abs(u-v)*12) for u,v in zip(pa,pb)) for pa,pb in zip(ra,rb)] for ra,rb in zip(a,b)]
        changes[kind]=sum(any(pix) for row in delta for pix in row)
        y=20+r*(height+18)
        for col,img in enumerate([a,b,delta]):
            x=col*width
            draw_text(sheet,x+3,y+4,kind.upper()+' '+('M1','M2','X12')[col])
            for dy,row in enumerate(img):
                sheet[y+18+dy][x:x+width]=row
    png(path,sheet)
    return dict(pixel_changes=changes,previous_commit=base)

def stability_tests(runner,plate=None):
    result=dict(footprint=footprint_tests(runner),classifications=classification_tests(runner),
                cave_fallback=cave_fallback_tests(runner),slope_variance=slope_variance_audit())
    if plate is not None:
        result['plate']=roof_plate(runner,plate)
    return result
