"""Independent finite-world counterexamples for temporal off-screen reflection.
No shader, game, world or network mutation. World units follow the pack's block=m convention.
"""
import json,math
from pathlib import Path
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def unit(a):return mul(a,1/norm(a))
def hit_box(origin,direction,box,minimum=1e-6):
    enter=-math.inf;leave=math.inf
    for a in range(3):
        if abs(direction[a])<1e-12:
            if not box[0][a]<=origin[a]<=box[1][a]:return None
        else:
            t0=(box[0][a]-origin[a])/direction[a];t1=(box[1][a]-origin[a])/direction[a]
            enter=max(enter,min(t0,t1));leave=min(leave,max(t0,t1))
    if leave<max(enter,minimum):return None
    return enter if enter>=minimum else leave
def uv(point,pitch,eye=(0,2,4),vfov=50,aspect=16/9):
    q=sub(point,eye);a=math.radians(pitch);c=math.cos(a);s=math.sin(a)
    # Downward pitch; view z points backward.
    x=q[0];y=c*q[1]-s*q[2];z=s*q[1]+c*q[2]
    if z>=0:return None
    scale=1/math.tan(math.radians(vfov)/2)
    return (.5+.5*x*scale/aspect/-z,.5+.5*y*scale/-z)
def visible(u):return u is not None and all(0<=v<1 for v in u)
def corners(box):
    return [(x,y,z) for x in (box[0][0],box[1][0]) for y in (box[0][1],box[1][1]) for z in (box[0][2],box[1][2])]
def segment_shadow_clear(a,b,casters,count=128):
    # Independent exact world-to-light queries, stronger than a finite shadow map.
    # Even this oracle cannot see objects absent from the caster set.
    for i in range(1,count):
        point=add(a,mul(sub(b,a),i/count))
        if any(hit_box(point,light,box,minimum=1e-5) is not None for box in casters):return False
    return True
eye=(0.,2.,4.);point=(2.,2.,-8.);surface=(1.,0.,-2.)
incoming=unit(sub(surface,eye));reflected=(incoming[0],-incoming[1],incoming[2])
assert norm(sub(reflected,unit(sub(point,surface))))<1e-12
target=((1.7,1.7,-8.5),(2.5,2.5,-8.))
middle=add(surface,mul(sub(point,surface),.97))
obstacle=(sub(middle,(.1,.1,.1)),add(middle,(.1,.1,.1)))
light=unit((-1.,1.,.3))
previous_pitch=24.5;current_pitch=26.
assert visible(uv(point,previous_pitch)) and not visible(uv(point,current_pitch))
assert visible(uv(surface,current_pitch))
assert all(p[1]>1 for p in [uv(c,current_pitch) for c in corners(obstacle)])
distance=hit_box(surface,reflected,target);near=hit_box(surface,reflected,obstacle)
assert near<distance and abs(distance-norm(sub(point,surface)))<1e-10
endpoint_clear_A=hit_box(add(point,mul(light,1e-5)),light,target) is None
endpoint_clear_B=endpoint_clear_A and hit_box(add(point,mul(light,1e-5)),light,obstacle) is None
assert endpoint_clear_A and endpoint_clear_B
clear_A=segment_shadow_clear(surface,point,[target])
clear_B=segment_shadow_clear(surface,point,[target,obstacle])
clear_non_caster=segment_shadow_clear(surface,point,[target])
assert clear_A and not clear_B and clear_non_caster
report=dict(ok=True,scope="Independent analytic 3D boxes and exact rays, NOT Minecraft, not a finite shadow texture, no GPU/FPS claim.",
 geometry=dict(eye=eye,water_point=surface,old_target=point,previous_pitch=previous_pitch,current_pitch=current_pitch,
 target=target,new_middle_obstacle=obstacle,light_direction=light),
 observations=dict(old_target_previous_uv=uv(point,previous_pitch),old_target_current_uv=uv(point,current_pitch),
 water_current_uv=uv(surface,current_pitch),middle_current_corner_uv=[uv(c,current_pitch) for c in corners(obstacle)],
 real_target_distance=distance,new_obstacle_distance=near,
 old_depth_and_color_identical_between_worlds=True,current_camera_visible_geometry_identical_between_worlds=True,
 current_shadow_depth_at_old_target_matches_both_worlds=True,
 endpoint_only_history_test_accepts_wrong_world=True,
 exact_light_queries_along_segment_reject_new_caster=not clear_B,
 noncasting_obstacle_remains_indistinguishable_even_with_exact_shadow_queries=clear_non_caster),
 implication="Endpoint reprojection/shadow validation does not prove the reflected segment. Current noncasting offscreen obstacles are absent from all selected inputs. A hard guarantee requires rejecting this case or additional current visibility data; bounded temporal contribution remains an explicit approximation.")
path=Path(__file__).with_name("OFFSCREEN_COUNTEREXAMPLE_v2.json")
if path.exists():raise RuntimeError("Do not overwrite observed evidence")
path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report["observations"],indent=2))
