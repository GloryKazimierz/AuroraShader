"""W3 screen-space reflection reference and independent analytic scene truth."""
import math
import re
import subprocess
from functools import lru_cache
from itertools import product
from pathlib import Path

W2_BASELINE = 'db67a74a9244b81c809ce776a9c8567f17587039'
REFLECTION_OPTIONS = {'WATER_SCREEN_REFLECTIONS','WATER_REFLECTION_STEPS'}
REFLECTION_LABELS = {'option.WATER_SCREEN_REFLECTIONS','value.WATER_SCREEN_REFLECTIONS.0',
    'value.WATER_SCREEN_REFLECTIONS.1','option.WATER_SCREEN_REFLECTIONS.comment',
    'option.WATER_REFLECTION_STEPS','value.WATER_REFLECTION_STEPS.64',
    'value.WATER_REFLECTION_STEPS.128','option.WATER_REFLECTION_STEPS.comment'}


def finite(values):
    return all(math.isfinite(x) for x in values)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def vector(matrix,value):
    return tuple(dot(row,value) for row in matrix)


def unit(value):
    if not finite(value):
        return None
    scale=max(map(abs,value))
    if scale<=1e-8:
        return None
    scaled=tuple(x/scale for x in value)
    length=math.sqrt(dot(scaled,scaled))
    return tuple(x/length for x in scaled)


def perspective(fov=70,aspect=1.5,near=.05,far=128):
    focal=1/math.tan(math.radians(fov)/2)
    return ((focal/aspect,0,0,0),(0,focal,0,0),
            (0,0,(far+near)/(near-far),2*far*near/(near-far)),(0,0,-1,0))


def inverse(matrix):
    rows=[list(row)+[float(i==j) for j in range(4)] for i,row in enumerate(matrix)]
    for column in range(4):
        pivot=max(range(column,4),key=lambda index:abs(rows[index][column]))
        if not math.isfinite(rows[pivot][column]) or abs(rows[pivot][column])<1e-15:
            return None
        rows[column],rows[pivot]=rows[pivot],rows[column]
        divisor=rows[column][column]
        rows[column]=[x/divisor for x in rows[column]]
        for index in range(4):
            if index!=column:
                factor=rows[index][column]
                rows[index]=[x-factor*y for x,y in zip(rows[index],rows[column])]
    return tuple(tuple(row[4:]) for row in rows)


def project(point,projection):
    clip=vector(projection,tuple(point)+(1,))
    if not finite(clip) or clip[3]<=0:
        return None
    return ((clip[0]/clip[3]*.5+.5,clip[1]/clip[3]*.5+.5),clip[2]/clip[3]*.5+.5)


def reconstruct(uv,depth,inverse_projection):
    h=vector(inverse_projection,(2*uv[0]-1,2*uv[1]-1,2*depth-1,1))
    if not finite(h) or abs(h[3])<=1e-12:
        return None
    point=tuple(x/h[3] for x in h[:3])
    return point if finite(point) else None


def smooth(a,b,value):
    t=min(1,max(0,(value-a)/(b-a)))
    return t*t*(3-2*t)



def pixel_span_tolerance(width,height):
    """Explicit subpixel corner convention: four binary32 ULP-scale viewport units."""
    return max(.0001,4.76837158203125e-7*max(width,height))


def trace_scene(origin,direction,projection,inverse_projection,color,depth,opaque_depth,steps=64):
    """Discrete DDA oracle; independent continuous geometry truth is tested below."""
    result=dict(valid=False,pixel=(-1,-1),position=(0,0,0),radiance=(0,0,0),distance=0.,confidence=0.,steps=0)
    height=len(color);width=len(color[0]) if height else 0
    if width<=0 or height<=0 or any(len(row)!=width for row in color):
        return result
    if any(len(image)!=height or any(len(row)!=width for row in image) for image in (depth,opaque_depth)):
        return result
    if not finite(origin) or not finite(direction) or max(map(abs,direction))<=1e-6:
        return result
    if not all(finite(row) for matrix in (projection,inverse_projection) for row in matrix):
        return result
    ray=unit(direction)
    near_h=vector(inverse_projection,(0,0,-1,1))
    if not finite(near_h) or near_h[3]<=1e-6:
        return result
    near_z=near_h[2]/near_h[3]
    if not math.isfinite(near_z) or near_z>=0:
        return result
    clip_z=near_z-max(.0001,abs(near_z)*.0001)
    if origin[2]>=clip_z:
        return result
    maximum=64.
    if ray[2]>0:
        maximum=min(maximum,(clip_z-origin[2])/ray[2])
    if maximum<=.05 or not math.isfinite(maximum):
        return result
    original=project(origin,projection)
    if original is None or any(x<0 or x>=1 for x in original[0]):
        return result
    origin_pixel=tuple(math.floor(original[0][i]*(width,height)[i]) for i in range(2))
    starts=tuple(o+.05*d for o,d in zip(origin,ray))
    ends=tuple(o+maximum*d for o,d in zip(origin,ray))
    c0=vector(projection,starts+(1,));c1=vector(projection,ends+(1,))
    if not finite(c0+c1) or c0[3]<=1e-6 or c1[3]<=1e-6:
        return result
    k0,k1=1/c0[3],1/c1[3]
    q0=tuple(x*k0 for x in starts);q1=tuple(x*k1 for x in ends)
    p0=tuple((c0[i]*k0*.5+.5)*(width,height)[i] for i in range(2))
    p1=tuple((c1[i]*k1*.5+.5)*(width,height)[i] for i in range(2))
    if not finite(p0+p1) or any(p0[i]<0 or p0[i]>=(width,height)[i] for i in range(2)):
        return result
    delta=tuple(b-a for a,b in zip(p0,p1))
    end_fraction=1.
    for axis,extent in enumerate((width,height)):
        if delta[axis]>0:
            end_fraction=min(end_fraction,(extent-p0[axis])/delta[axis])
        elif delta[axis]<0:
            end_fraction=min(end_fraction,-p0[axis]/delta[axis])
    if end_fraction<=0 or not math.isfinite(end_fraction):
        return result
    p1=tuple(a+end_fraction*d for a,d in zip(p0,delta))
    q1=tuple(a+end_fraction*(b-a) for a,b in zip(q0,q1))
    k1=k0+end_fraction*(k1-k0)
    delta=tuple(b-a for a,b in zip(p0,p1))
    if max(map(abs,delta))<1e-5:
        return result
    signs=tuple(1 if d>0 else -1 if d<0 else 0 for d in delta)
    cells=[math.floor(value) for value in p0]
    for coordinate in range(2):
        if signs[coordinate]<0 and p0[coordinate]==cells[coordinate]:
            cells[coordinate]-=1
    def point_at(fraction):
        k=k0+(k1-k0)*fraction
        if not math.isfinite(k) or k<=1e-8:
            return None
        point=tuple((a+(b-a)*fraction)/k for a,b in zip(q0,q1))
        return point if finite(point) and point[2]<0 else None
    def depth_position(pixel,raw):
        h=vector(inverse_projection,(2*(pixel[0]+.5)/width-1,2*(pixel[1]+.5)/height-1,2*raw-1,1))
        if not finite(h) or h[3]<=1e-6:
            return None
        view=tuple(x/h[3] for x in h[:3])
        return view if finite(view) and view[2]<0 else None
    steps=max(1,min(128,int(steps)))
    enter=0.
    minimum_span=pixel_span_tolerance(width,height)
    maximum_delta=max(map(abs,delta))
    for iteration in range(256):
        if enter>=1 or result['steps']>=steps:
            break
        grid_crossings=tuple((cells[i]+(1 if signs[i]>0 else 0)-p0[i])/delta[i]
                        if signs[i] else math.inf for i in range(2))
        leave=min(1.,*grid_crossings)
        if leave<=enter:
            return result
        # Numerical corner slivers below the explicit screen-space precision
        # threshold are not samples and do not consume the processed-cell budget.
        if maximum_delta*(leave-enter)<=minimum_span:
            enter=leave
            for coordinate in range(2):
                if grid_crossings[coordinate]<=leave:
                    cells[coordinate]+=signs[coordinate]
            continue
        result['steps']+=1
        pixel=tuple(cells)
        if any(pixel[i]<0 or pixel[i]>=(width,height)[i] for i in range(2)):
            return result
        # Every nonzero crossed pixel segment is visited, including diagonal
        # minor-axis entries. Exact corner contact advances both coordinates.
        first,last=point_at(enter),point_at(leave)
        if first is None or last is None:
            return result
        x,y=pixel
        rgba=color[y][x];recorded=depth[y][x];raw=opaque_depth[y][x]
        if len(rgba)!=4 or not finite(rgba) or not math.isfinite(recorded) or not math.isfinite(raw) or not 0<=raw<=1:
            return result
        if rgba[3]==0:
            if tuple(rgba[:3])!=(0,0,0) or recorded!=1:
                return result
            if raw<1:
                unknown=depth_position(pixel,raw)
                if unknown is None or max(-first[2],-last[2])>=-unknown[2]:
                    return result
        else:
            if rgba[3]!=1 or any(c<0 or c>65504 for c in rgba[:3]) or not 0<=recorded<1 or recorded!=raw:
                return result
            scene=depth_position(pixel,recorded)
            if scene is None:
                return result
            front=-scene[2]
            # Pixel-depth uncertainty is bounded; this is not physical surface thickness.
            back=front+max(.15,min(.5,abs(first[2]-last[2])))
            if pixel!=origin_pixel and max(-first[2],-last[2])>=front and min(-first[2],-last[2])<=back:
                first_t=max(.05,dot(tuple(x-o for x,o in zip(first,origin)),ray))
                last_t=min(maximum,dot(tuple(x-o for x,o in zip(last,origin)),ray))
                rate=-ray[2]
                overlaps=last_t>=first_t
                if abs(rate)>1e-7:
                    crossings=((front+origin[2])/rate,(back+origin[2])/rate)
                    first_t=max(first_t,min(crossings));last_t=min(last_t,max(crossings))
                    overlaps=overlaps and last_t>=first_t
                else:
                    overlaps=overlaps and front<=-origin[2]<=back
                if overlaps:
                    hit=tuple(o+first_t*d for o,d in zip(origin,ray))
                    projected=project(hit,projection)
                    if projected is None:
                        return result
                    hit_pixel=tuple(math.floor(projected[0][i]*(width,height)[i]) for i in range(2))
                    if hit_pixel!=pixel and last_t>first_t:
                        first_t=first_t+(last_t-first_t)*.001
                        hit=tuple(o+first_t*d for o,d in zip(origin,ray));projected=project(hit,projection)
                        if projected is None:
                            return result
                        hit_pixel=tuple(math.floor(projected[0][i]*(width,height)[i]) for i in range(2))
                    if hit_pixel==pixel:
                        screen=tuple(projected[0][i]*(width,height)[i] for i in range(2))
                        edge=min(screen[0],screen[1],width-screen[0],height-screen[1])
                        confidence=smooth(0,8,edge)*(1-smooth(48,64,first_t))*(1-smooth(.75*steps,steps,result['steps']))
                        if confidence>0:
                            result.update(valid=True,pixel=pixel,position=hit,radiance=tuple(rgba[:3]),distance=first_t,confidence=confidence)
                            return result
        enter=leave
        for coordinate in range(2):
            if grid_crossings[coordinate]<=leave:
                cells[coordinate]+=signs[coordinate]
    return result


def analytic_plane_hit(origin,direction,plane,projection):
    """Continuous ray/plane intersection; does not use depth samples or DDA."""
    denominator=dot(plane['normal'],direction)
    if abs(denominator)<1e-12:
        return None
    t=dot(plane['normal'],tuple(p-o for p,o in zip(plane['point'],origin)))/denominator
    if t<=0:
        return None
    position=tuple(o+t*d for o,d in zip(origin,direction))
    projected=project(position,projection)
    if projected is None:
        return None
    u,v=projected[0]
    left,bottom,right,top=plane.get('rect',(0,0,1,1))
    if not left<=u<right or not bottom<=v<top:
        return None
    return dict(distance=t,position=position,uv=(u,v),recorded=plane.get('recorded',True))


def analytic_first_hit(origin,direction,planes,projection):
    ray=unit(direction)
    if ray is None or not finite(origin):
        return None
    hits=[hit for hit in (analytic_plane_hit(origin,ray,plane,projection) for plane in planes) if hit is not None]
    return min(hits,key=lambda hit:hit['distance']) if hits else None


def raster_scene(width,height,projection,planes):
    inv=inverse(projection)
    colors=[];depths=[];opaque=[]
    for y in range(height):
        color_row=[];depth_row=[];raw_row=[]
        for x in range(width):
            camera_point=reconstruct(((x+.5)/width,(y+.5)/height),.5,inv)
            hits=[(hit,plane) for plane in planes for hit in [analytic_plane_hit((0,0,0),camera_point,plane,projection)]
                  if hit is not None and 0 <= project(hit['position'],projection)[1] < 1]
            if not hits:
                color_row.append((0,0,0,0));depth_row.append(1.);raw_row.append(1.)
                continue
            hit,plane=min(hits,key=lambda item:-item[0]['position'][2])
            depth=project(hit['position'],projection)[1]
            raw_row.append(depth)
            color_row.append(tuple(plane.get('color',(.25,.5,1)))+(1,) if plane.get('recorded',True) else (0,0,0,0))
            depth_row.append(depth if plane.get('recorded',True) else 1.)
        colors.append(color_row);depths.append(depth_row);opaque.append(raw_row)
    return colors,depths,opaque


def point_on_plane(uv,plane,projection):
    point=reconstruct(uv,.5,inverse(projection))
    return analytic_plane_hit((0,0,0),point,plane,projection)['position']


def fixture(name,size,projection,planes,queries,budgets=(64,128)):
    color,depth,opaque=raster_scene(*size,projection,planes)
    return dict(name=name,projection=projection,inverse_projection=inverse(projection),
                color=color,depth=depth,opaque_depth=opaque,queries=queries,planes=planes,budgets=budgets)


@lru_cache(maxsize=1)
def trace_fixtures():
    scenes=[]
    wall=dict(point=(0,0,-12),normal=(0,0,1),color=(.25,.5,1))
    for name,size,fov in (('wall-wide',(96,64),45),('wall-tall',(64,96),95),('wall-square',(80,80),70)):
        projection=perspective(fov,size[0]/size[1])
        queries=[]
        for origin_z,u,v in product((-2,-20),(.2,.35,.65,.8),(.3,.7)):
            target=point_on_plane((u,v),wall,projection)
            origin=(0,0,origin_z)
            queries.append(dict(origin=origin,direction=tuple(x-o for x,o in zip(target,origin)),truth='plane'))
        if name=='wall-wide':
            original=queries[1]
            for adjustment in (-2**-20,-2**-22,2**-22,2**-20):
                direction=list(original['direction']);direction[0]*=1+adjustment
                queries.append(dict(origin=original['origin'],direction=tuple(direction),truth='plane'))
        scenes.append(fixture(name,size,projection,[wall],queries))
    projection=perspective(70,1.5)
    for name,plane,uvs in (
        ('slanted',dict(point=(0,0,-12),normal=(.18,-.12,1),color=(1,.5,.25)),product((.2,.35,.65,.8),(.25,.4,.6,.75))),
        ('floor',dict(point=(0,-3,-10),normal=(0,1,0),color=(.5,.25,.125)),product((.2,.35,.65,.8),(.15,.25,.35)) )):
        queries=[]
        for u,v in uvs:
            target=point_on_plane((u,v),plane,projection);origin=(.125,.25,-2)
            queries.append(dict(origin=origin,direction=tuple(x-o for x,o in zip(target,origin)),truth='plane'))
        scenes.append(fixture(name,(96,64),projection,[plane],queries))
    poles=[];queries=[]
    for column in (41,54):
        pole=dict(wall,rect=(column/96,.2,(column+1)/96,.8))
        poles.append(pole)
        for origin_u,v in product((.25,.75),(.35,.65)):
            origin=point_on_plane((origin_u,.5),dict(wall,point=(0,0,-2)),projection)
            target=point_on_plane(((column+.5)/96,v),pole,projection)
            queries.append(dict(origin=origin,direction=tuple(x-o for x,o in zip(target,origin)),truth='thin'))
    scenes.append(fixture('thin-poles',(96,64),projection,poles,queries))
    masked=[dict(wall,rect=(.15,.1,.4,.9)),dict(wall,rect=(.6,.1,.85,.9))]
    queries=[]
    for u,v in product((.2,.3,.45,.55,.7,.8),(.3,.7)):
        target=point_on_plane((u,v),wall,projection)
        queries.append(dict(origin=(0,0,-2),direction=(target[0],target[1],target[2]+2),truth='masked'))
    scenes.append(fixture('masked-rectangles',(96,64),projection,masked,queries))
    query_target=point_on_plane((.82,.6),wall,projection)
    queries=[dict(origin=(0,0,-2),direction=(query_target[0],query_target[1],query_target[2]+2),truth='occlusion')]
    unknown=dict(point=(0,0,-4),normal=(0,0,1),rect=(.57,.1,.75,.9),recorded=False)
    scenes.append(fixture('unknown-occluder',(96,64),projection,[wall,unknown],queries))
    sky=fixture('unknown-sky-gap',(96,64),projection,[wall],queries)
    for y in range(64):
        for x in range(55,72):
            sky['color'][y][x]=(0,0,0,0);sky['depth'][y][x]=sky['opaque_depth'][y][x]=1.
    scenes.append(sky)
    for name,rgba,dvalue,rvalue in (
        ('invalid-alpha',(.25,.5,1,.5),None,None),('invalid-nan-color',(math.nan,0,0,1),None,None),
        ('invalid-infinite-color',(math.inf,0,0,1),None,None),('invalid-negative-color',(-.25,0,0,1),None,None),
        ('invalid-clear-color',(.25,0,0,0),1.,1.),('invalid-depth',None,math.nan,None),
        ('invalid-raw-depth',None,None,math.nan),('mismatched-recorded-depth',None,None,.5)):
        broken=fixture(name,(32,24),perspective(70,4/3),[wall],[dict(origin=(0,0,-2),direction=(3,1,-10),truth='invalid')])
        for y in range(24):
            for x in range(32):
                if rgba is not None: broken['color'][y][x]=rgba
                if dvalue is not None: broken['depth'][y][x]=dvalue
                if rvalue is not None: broken['opaque_depth'][y][x]=rvalue
        scenes.append(broken)
    mismatch=fixture('dimension-mismatch',(32,24),perspective(70,4/3),[wall],queries)
    mismatch['opaque_depth']=mismatch['opaque_depth'][:-1]
    scenes.append(mismatch)
    projection=perspective(70,2)
    origin=point_on_plane((.15,.5),dict(wall,point=(0,0,-2)),projection)
    targets=[point_on_plane((u,v),wall,projection) for u,v in product((.48,.58),(.4,.6))]
    queries=[dict(origin=origin,direction=tuple(x-o for x,o in zip(target,origin)),truth='budget') for target in targets]
    scenes.append(fixture('budget',(256,128),projection,[wall],queries))
    projection=perspective(70,1.5)
    edge_queries=[]
    for u,v in ((.005,.4),(.995,.6),(.4,.008),(.6,.992)):
        target=point_on_plane((u,v),wall,projection)
        edge_queries.append(dict(origin=(0,0,-2),direction=(target[0],target[1],target[2]+2),truth='border'))
    scenes.append(fixture('borders',(96,64),projection,[wall],edge_queries))
    queries=[dict(origin=o,direction=d,truth='guard') for o,d in (
        ((0,0,-2),(0,0,-1)),((0,0,-11.99),(1,0,0)),((0,0,-2),(1,.5,3)),
        ((0,0,-.01),(1,0,-1)),((0,0,1),(1,0,-1)),((math.nan,0,-2),(1,0,-1)),
        ((0,0,-2),(0,0,0)),((0,0,-2),(math.inf,0,-1)))]
    scenes.append(fixture('self-near-and-invalid-rays',(96,64),projection,[wall],queries))
    for distance in (60,72):
        plane=dict(wall,point=(0,0,-distance))
        target=point_on_plane((.6,.6),plane,projection)
        scenes.append(fixture('distance-'+str(distance),(96,64),projection,[plane],
            [dict(origin=(0,0,-2),direction=(target[0],target[1],target[2]+2),truth='distance')]))
    foreground=dict(wall,rect=(.61,.1,.7,.9))
    scenes.append(fixture('finite-slab-behind-rectangle',(96,64),projection,[foreground],
        [dict(origin=(0,0,-2),direction=(2.5,0,-10),truth='behind-slab'),
         dict(origin=(0,0,-13),direction=(4,0,-10),truth='behind-slab')]))
    # This diagonal entered an omitted minor-axis cell in the first thin-DDA
    # prototype. An unrecorded one-pixel occluder must stop the ray, not leak the wall.
    background=dict(wall,point=(0,0,-20))
    blocker=dict(wall,rect=(28/96,19/64,29/96,20/64),recorded=False)
    target=point_on_plane((.3,.3),wall,projection)
    query=[dict(origin=(0,0,-2),direction=(target[0],target[1],target[2]+2),truth='occlusion')]
    scenes.append(fixture('diagonal-unknown-pixel',(96,64),projection,[background,blocker],query))
    gap=fixture('diagonal-sky-pixel',(96,64),projection,[background],query)
    gap['color'][19][28]=(0,0,0,0);gap['depth'][19][28]=gap['opaque_depth'][19][28]=1.
    scenes.append(gap)
    for name,radiance in (('valid-black',(0,0,0)),('valid-fp16-maximum',(65504,32,.125))):
        plane=dict(wall,color=radiance)
        scenes.append(fixture(name,(32,24),perspective(70,4/3),[plane],
            [dict(origin=(0,0,-2),direction=(3,1,-10),truth='plane')]))
    return scenes


WATER_RESTORATIONS = (('#include "/lib/water_screen_reflection.glsl"\n', ''),
 ('#if WATER_SCREEN_REFLECTIONS == 0\n    if (skyAccess <= 0.0) return scene;\n#endif\n',
  '    if (skyAccess <= 0.0) return scene;\n'),
 ('#if SKY_STYLE != 0 || WATER_SCREEN_REFLECTIONS != 0\n',
  '#if SKY_STYLE == 0\n    return tinted;\n#else\n'),
 ('#if WATER_SCREEN_REFLECTIONS == 0\n'
  '    if (reflectionWeight <= 0.0) return tinted;\n'
  '#else\n'
  '    float localReflectionWeight = clamp(WATER_REFLECTION_STRENGTH, 0.0, 1.0) * environment;\n'
  '    if (localReflectionWeight <= 0.0) return tinted;\n'
  '#endif\n',
  '    if (reflectionWeight <= 0.0) return tinted;\n'),
 ('#if WATER_SCREEN_REFLECTIONS == 0\n'
  '    if (reflectionWeight <= 0.0) return tinted;\n'
  '    // Analytic M7 sky color only: no scene textures, clouds, discs, aurora or SSR.\n'
  '    vec3 reflectedSky = auroraSkyLinear(reflected, vanillaFog);\n'
  '    // Native alpha subsequently attenuates this whole source, including reflection.\n'
  '    // Never divide by alpha; this is an artistic source blend, not physical water.\n'
  '    return mix(tinted, reflectedSky, clamp(reflectionWeight, 0.0, 1.0));\n'
  '#else\n'
  "    // Keep the old sky weight's arithmetic unchanged: every trace miss restores\n"
  '    // exactly that fallback. Local scene reflection is independent of sky access.\n'
  '    vec3 fallback = tinted;\n'
  '#if SKY_STYLE != 0\n'
  '    if (reflectionWeight > 0.0) {\n'
  '        vec3 reflectedSky = auroraSkyLinear(reflected, vanillaFog);\n'
  '        fallback = mix(tinted, reflectedSky, clamp(reflectionWeight, 0.0, 1.0));\n'
  '    }\n'
  '#endif\n'
  '    localReflectionWeight *= upwardSurface * waterFresnel(dot(normal, towardEye));\n'
  '    return applyWaterScreenReflection(tinted, fallback, viewPosition, celestialUnit(normalView), '
  'reflected, localReflectionWeight);\n'
  '#endif\n'
  '#else\n'
  '    return tinted;\n'
  '#endif\n'
  '#endif\n'
  '}\n'
  '#endif\n',
  '    if (reflectionWeight <= 0.0) return tinted;\n'
  '    // Analytic M7 sky color only: no scene textures, clouds, discs, aurora or SSR.\n'
  '    vec3 reflectedSky = auroraSkyLinear(reflected, vanillaFog);\n'
  '    // Native alpha subsequently attenuates this whole source, including reflection.\n'
  '    // Never divide by alpha; this is an artistic source blend, not physical water.\n'
  '    return mix(tinted, reflectedSky, clamp(reflectionWeight, 0.0, 1.0));\n'
  '#endif\n'
  '#endif\n'
  '}\n'
  '#endif\n'))

LANGUAGE_RESTORATIONS = {'lang/en_us.lang': (('screen.WATER=Water Surface and Reflections\n',
                      'screen.WATER=Water Color and Sky Reflection\n'),
                     ('option.WATER_REFLECTION_STRENGTH=Water Reflection Strength\n',
                      'option.WATER_REFLECTION_STRENGTH=Water Sky Reflection\n'),
                     ('option.WATER_REFLECTION_STRENGTH.comment=Scales screen-space scene reflections '
                      'and the analytic sky fallback. Screen hits do not require Aurora Sky or sky '
                      'light. Native alpha still applies.\n',
                      'option.WATER_REFLECTION_STRENGTH.comment=Angle-dependent analytic sky color on '
                      'upper water faces. Requires Aurora Sky and sky light; no terrain, clouds, '
                      'sun/moon or aurora reflections. Native alpha still applies.\n')),
 'lang/zh_cn.lang': (('screen.WATER=水面与反射\n', 'screen.WATER=水面颜色与天空反射\n'),
                     ('option.WATER_REFLECTION_STRENGTH=水面反射强度\n',
                      'option.WATER_REFLECTION_STRENGTH=水面天空反射\n'),
                     ('option.WATER_REFLECTION_STRENGTH.comment=控制屏幕空间场景反射与解析天空回退。场景命中不需要开启 Aurora '
                      '天空，也不要求天空光。原生 alpha 仍参与混合。\n',
                      'option.WATER_REFLECTION_STRENGTH.comment=在朝上的水面上加入随角度变化的解析天空色。需要 Aurora '
                      '天空和天空光；不反射地形、云、太阳／月亮或极光。原生 alpha 仍参与混合。\n'))}

def restore_water_screen_reflection_source(relative,source):
    """Restore only the exact W3 water integration, menu token and UI additions."""
    relative=relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative=relative[len('shaders/'):]
    pairs=()
    if relative=='lib/water.glsl':
        pairs=WATER_RESTORATIONS
    elif relative=='shaders.properties':
        pairs=((' WATER_REFLECTION_STRENGTH WATER_SCREEN_REFLECTIONS WATER_REFLECTION_STEPS WATER_WAVES ',
                ' WATER_REFLECTION_STRENGTH WATER_WAVES '),)
    elif relative in LANGUAGE_RESTORATIONS:
        pairs=LANGUAGE_RESTORATIONS[relative]
    for current,previous in pairs:
        assert source.count(current)==1,'Missing or changed W3 source fragment: '+current
        source=source.replace(current,previous,1)
    if relative in LANGUAGE_RESTORATIONS:
        marker='\noption.WATER_SCREEN_REFLECTIONS='
        assert source.count(marker)==1
        prefix,tail=source.split(marker,1)
        keys=[line.split('=',1)[0] for line in ('option.WATER_SCREEN_REFLECTIONS='+tail).splitlines()]
        assert len(keys)==len(REFLECTION_LABELS) and set(keys)==REFLECTION_LABELS
        source=prefix
    return source


def validate_trace_math():
    assert pixel_span_tolerance(96,64)==.0001
    assert pixel_span_tolerance(256,128)==2**-13
    assert pixel_span_tolerance(4096,2160)==2**-9
    for extent in (96,256,1024,4096,16384):
        tolerance=pixel_span_tolerance(extent,extent)
        assert .0001<=tolerance<.01
        assert extent*(tolerance/extent)==tolerance
    total=hits=geometric=0
    max_pixel_error=max_distance_error=0.
    by_name={scene['name']:scene for scene in trace_fixtures()}
    for scene in trace_fixtures():
        width,height=len(scene['color'][0]),len(scene['color'])
        for budget in scene['budgets']:
            for query in scene['queries']:
                actual=trace_scene(query['origin'],query['direction'],scene['projection'],scene['inverse_projection'],
                                   scene['color'],scene['depth'],scene['opaque_depth'],budget)
                truth=analytic_first_hit(query['origin'],query['direction'],scene['planes'],scene['projection'])
                assert 0<=actual['steps']<=budget and 0<=actual['confidence']<=1
                if actual['valid']:
                    assert .05<=actual['distance']<=64 and actual['confidence']>0
                    assert finite(actual['position']+actual['radiance'])
                    uv=project(actual['position'],scene['projection'])[0]
                    assert tuple(math.floor(x*n) for x,n in zip(uv,(width,height)))==actual['pixel']
                    ray=unit(query['direction'])
                    expected=tuple(o+actual['distance']*d for o,d in zip(query['origin'],ray))
                    assert max(abs(a-b) for a,b in zip(actual['position'],expected))<1e-10
                else:
                    assert actual['pixel']==(-1,-1) and actual['position']==actual['radiance']==(0,0,0)
                    assert actual['distance']==actual['confidence']==0
                if query['truth'] in ('plane','thin','masked'):
                    # This continuous ray/plane answer is independent of the DDA
                    # and of raster depth samples; none of the original miss cases
                    # was removed or retargeted to make the implementation pass.
                    wanted=bool(truth and truth['recorded'] and .05<=truth['distance']<=64)
                    assert actual['valid']==wanted,(scene['name'],query,budget,truth,actual)
                    if wanted:
                        ray=unit(query['direction'])
                        depth_budget=.5/max(abs(ray[2]),.05)
                        distance_error=abs(actual['distance']-truth['distance'])
                        assert distance_error<=depth_budget,(scene['name'],distance_error,depth_budget)
                        actual_uv=project(actual['position'],scene['projection'])[0]
                        pixel_error=max(abs(a-b)*n for a,b,n in zip(actual_uv,truth['uv'],(width,height)))
                        assert pixel_error<=1.5,(scene['name'],pixel_error)
                        max_pixel_error=max(max_pixel_error,pixel_error)
                        max_distance_error=max(max_distance_error,distance_error)
                    geometric+=1
                elif query['truth'] in ('invalid','guard','behind-slab') or scene['name']=='dimension-mismatch':
                    assert not actual['valid'],scene['name']
                elif scene['name'] in ('unknown-occluder','diagonal-unknown-pixel'):
                    assert truth is not None and not truth['recorded'] and not actual['valid']
                elif scene['name'] in ('unknown-sky-gap','diagonal-sky-pixel'):
                    assert truth is not None and truth['recorded'] and actual['valid']
                elif query['truth']=='budget':
                    assert truth is not None and truth['recorded'] and actual['valid']==(budget==128)
                elif query['truth']=='border':
                    assert actual['valid'] and actual['confidence']<.1
                elif query['truth']=='distance':
                    assert actual['valid']==(truth['distance']<=64)
                    if actual['valid']:
                        assert actual['confidence']<1
                total+=1;hits+=actual['valid']
    # Test malformed projection, dimensions and source metadata independently of
    # half-float fixture upload. 65505 is invalid here but rounds down in RGBA16F.
    scene=by_name['wall-square'];query=scene['queries'][0]
    zero=tuple((0.,0.,0.,0.) for _ in range(4))
    assert not trace_scene(query['origin'],query['direction'],zero,zero,scene['color'],scene['depth'],scene['opaque_depth'])['valid']
    for invalid in (-.001,65505,math.nan,math.inf,-math.inf):
        color=[[tuple((invalid,0,0,1)) for pixel in row] for row in scene['color']]
        assert not trace_scene(query['origin'],query['direction'],scene['projection'],scene['inverse_projection'],color,scene['depth'],scene['opaque_depth'])['valid']
    for bad in (-.001,1.001,math.nan,math.inf,-math.inf):
        depth=[[bad for pixel in row] for row in scene['depth']]
        assert not trace_scene(query['origin'],query['direction'],scene['projection'],scene['inverse_projection'],scene['color'],depth,depth)['valid']
    print('PASS: W3 {} scenes / {} ray-budget cases; {} hits and {} coherent misses'.format(len(trace_fixtures()),total,hits,total-hits))
    print('PASS: W3 {} independent analytic-plane comparisons across FOV/aspect/directions; max pixel/ray-distance error {:.6g}/{:.6g}'.format(geometric,max_pixel_error,max_distance_error))
    print('PASS: W3 diagonal single-pixel occlusion/sky pair, finite .5 depth cap, clip/border/budget/self/source/invalid guards')


def validate_water_screen_reflection(root,expand,preprocess,compact,function_body):
    from validate_settings_profiles import (option_definitions,parse_properties,parse_language,
                                            menu_options,load_profiles,matching_profiles,PROFILE_KEYS)
    root=Path(root);shaders=root/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    def body(source,name):
        return compact(function_body(source,name))
    @lru_cache(maxsize=None)
    def previous(relative):
        return subprocess.check_output(['git','-C',str(root),'show',W2_BASELINE+':shaders/'+relative]).decode('utf-8').replace('\r\n','\n')
    @lru_cache(maxsize=None)
    def expanded_previous(relative):
        return re.sub(r'^#include "([^"]+)"\s*$',lambda match:expanded_previous(match[1].lstrip('/')),previous(relative),flags=re.M)
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',W2_BASELINE,'shaders']).decode().splitlines()
    assert len(old_files)==102
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files==set(old_files)|{'shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'}
    for path in old_files:
        relative=path[len('shaders/'):]
        assert restore_water_screen_reflection_source(relative,read(relative))==previous(relative),relative
    helper=read('lib/water_screen_reflection.glsl');code=compact(helper)
    assert set(re.findall(r'uniform sampler2D (\w+);',helper))=={'colortex5','colortex6','depthtex1'}
    for forbidden in ('imageStore','gl_FragDepth','gl_Position','frameTimeCounter','random','textureLod'):
        assert forbidden not in code,forbidden
    for token in ('minimumTravel=0.05','maximumTravel=64.0','payload.a!=1.0','depth!=opaqueDepth',
                  'if(rayDepthMax>=-unknownView.z)returnfalse;',
                  'surfaceView+originalNormalView*0.01','returnmix(fallback,mix(tinted,radiance,clamp(localWeight,0.0,1.0)),confidence);'):
        assert token in code,token
    assert 'textureSize(colortex5,0)' in code and 'textureSize(colortex6,0)' in code and 'textureSize(depthtex1,0)' in code
    for token in ('floatthickness=clamp(rayDepthMax-rayDepthMin,0.15,0.5);',
                  'floatminimumPixelSpan=max(0.0001,4.76837158203125e-7*float(max(size.x,size.y)));',
                  'for(intiteration=0;iteration<256;++iteration)',
                  'if(stepsTaken>=stepLimit||enterFraction>=1.0)break;',
                  'ivec2pixel=cell;', 'stepsTaken+=1;'):
        assert token in code,token
    trace=body(helper,'traceWaterScene')
    assert trace.index('if(projectedSpan*(exitFraction-enterFraction)<=minimumPixelSpan)') < trace.index('stepsTaken+=1;') < trace.index('texelFetch(')
    water=read('lib/water.glsl')
    for mode,style,sky,debug in product((0,1),(0,1),(0,1),range(7)):
        options={'WATER_SCREEN_REFLECTIONS':0,'SCENE_COLOR_MODE':mode,'WATER_STYLE':style,'SKY_STYLE':sky}
        actual=preprocess(expand(shaders/'gbuffers_water.fsh'),debug,False,overrides=options)
        before=preprocess(expanded_previous('gbuffers_water.fsh'),debug,False,overrides=options)
        assert body(actual,'applyWaterStyle')==body(before,'applyWaterStyle')
        assert body(actual,'main')==body(before,'main')
        assert body(actual,'applyWaterScreenReflection')=='returnfallback;'
    active=preprocess(expand(shaders/'gbuffers_water.fsh'),0,False,overrides={'SKY_STYLE':0})
    active_body=body(active,'applyWaterStyle')
    assert 'applyWaterScreenReflection(' in active_body and 'auroraSkyLinear(' not in active_body
    assert 'if(skyAccess<=0.0)returnscene;' not in active_body
    assert 'localReflectionWeight=clamp(WATER_REFLECTION_STRENGTH,0.0,1.0)*environment;' in active_body
    assert 'localReflectionWeight*=upwardSurface*waterFresnel(dot(normal,towardEye));' in active_body
    for path in shaders.glob('*.fsh'):
        selected=preprocess(expand(path),0,False)
        assert ('traceWaterScene(' in selected)==(path.stem=='gbuffers_water'),path.name
        uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms)==len(set(uniforms)),path.name
    options=option_definitions(root);props=parse_properties(read('shaders.properties'))
    controls,screens=menu_options(props,options)
    assert len(options)==len(controls)==60 and len(screens)==12
    assert options['WATER_SCREEN_REFLECTIONS']==dict(kind='number',default='1',values=('0','1'))
    assert options['WATER_REFLECTION_STEPS']==dict(kind='number',default='64',values=('64','128'))
    profiles=load_profiles(root);controlled=PROFILE_KEYS|{'FOLIAGE_WIND'}
    assert all(set(profile)==controlled for profile in profiles.values()) and len(set(options)-controlled)==53
    defaults={key:value['default'] for key,value in options.items()}
    for name,profile in profiles.items():
        for enabled,budget in product(('0','1'),('64','128')):
            selected=dict(defaults,**profile,WATER_SCREEN_REFLECTIONS=enabled,WATER_REFLECTION_STEPS=budget)
            assert matching_profiles(profiles,selected)==(name,)
    en,zh=(parse_language(read('lang/'+language)) for language in ('en_us.lang','zh_cn.lang'))
    assert len(en)==len(zh)==191 and set(en)==set(zh) and REFLECTION_LABELS<=set(en)
    assert all(re.search(r'[\u3400-\u9fff]',zh[key]) for key in REFLECTION_LABELS)
    validate_trace_math()
    print('PASS: W3 all 102 W2 files pinned after exact authorized restoration; two new shader files')
    print('PASS: W3 exact SSR-off shader behavior, sky-independent local hits, original alpha/fog/geometry and stable snapshot inputs')
    print('PASS: W3 60 controls, 12 screens, unchanged seven-control profiles retain 53 settings, 191 bilingual keys')
    print('LIMIT: one visible depth layer and bounded screen rays; no hidden geometry, physical water volumes, reflected-path fog or hardware ray tracing')
