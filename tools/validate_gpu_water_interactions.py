"""Verify the actual prepare1 contact history and the world-space rain/interaction gradients."""
import math
from compile_glsl import SHADERS, expand
from validate_gpu import require

def interaction_tests(runner,panels=None):
    options=dict(WATER_OPTICS=1, WATER_INTERACTIONS=1, IRIS_FEATURE_PER_BUFFER_BLENDING=True)
    pair=runner.pair('prepare1',options)
    blank=[[(0.,0.,0.,0.) for _ in range(16)] for _ in range(2)]
    def frame(previous,t,offset,actor,kind=2,dt=.05,cut=False):
        anchor=(t//4 if not cut else 90,0,0)
        last=((t-1)//4 if t>0 else 0,0,0)
        # Hard camera steps exercise both third-person orbit and rereferencing of old wakes.
        cam=anchor[0]+offset
        oldoffset=(.35 if t%2 else .15) if t>0 else offset
        relative=(cam-actor,0.,0.)
        u=[('frameCounter','i1',(t,)),('frameTime','f1',(dt,)),('isSpectator','i1',(int(kind<0),)),
           ('isRiding','i1',(int(kind==2),)),('vehicleInWater','i1',(int(kind==2),)),('feetInWater','i1',(int(kind==1),)),
           ('cameraPositionInt','i3',anchor),('previousCameraPositionInt','i3',last),
           ('cameraPositionFract','f3',(offset,0,0)),('previousCameraPositionFract','f3',(oldoffset,0,0)),
           ('relativeVehiclePosition','f3',relative),('relativeEyePosition','f3',relative)]
        return runner.render('contact history',pair,16,2,[('colortex15',previous,'RGBA32F')],u)
    history=blank
    per=[]
    for t in range(14):
        offset=(.15 if t%2 else .35)
        history=frame(history,t,offset,t*.1)
        packets=[x for x in range(1,16) if history[1][x][2]==2.]
        if packets:
            for i in packets:
                speed=history[1][i][0]
                require(abs(speed-2.)<5e-5,'Camera motion entered actor velocity')
                require(history[0][i][3]>=0. and history[0][i][3]<1.5,'Invalid wake age')
        per.append(len(packets))
    require(per[-1]>=5,'Moving ridden vehicle produced no wake')
    still=blank
    for t in range(8):
        still=frame(still,t,(.15 if t%2 else .35),.3)
    require(all(s[2]==0. for s in still[1][1:]),'Orbiting a stationary entity produced a wake')
    for label,t,dt,cut in [('skip',17,.05,False),('lag',14,.5,False),('teleport',14,.05,True)]:
        cleared=frame(history,t,.15,t*.1,dt=dt,cut=cut)
        require(all(v==(0.,0.,0.,0.) for row in cleared for v in row[1:]),label+' retained stale ripples')
    # Use actual GLSL rain and wake gradient on water with independent contact inputs.
    shader='#version 330 compatibility\n'+expand(SHADERS/'lib/water_filtered_waves.glsl')+'\n'+expand(SHADERS/'lib/water_ripples.glsl')+'''
uniform vec3 origin;
uniform float sky, footprint;
layout(location=0) out vec4 outputSlope;
void main() {
    vec2 p=(gl_FragCoord.xy-vec2(32,16))*.035;
    vec3 point=origin+vec3(p.x,0,p.y);
    vec2 dx=vec2(footprint,0),dy=dx.yx;
    outputSlope=vec4(waterRainSlope(point,dx,dy,sky),waterContactSlope(point,dx,dy));
}
'''
    diagnostic=runner.pair('composite1',wrapper=shader)
    def sample(tile,camera,frac,rain=1.,precip=1,sky=1.,foot=.012,clock=17.1,origin=(0.,0.,0.)):
        u=[('origin','f3',origin),('sky','f1',(sky,)),('footprint','f1',(foot,)),('frameTimeCounter','f1',(clock,)),
           ('rainStrength','f1',(rain,)),('biome_precipitation','i1',(precip,)),('cameraPositionInt','i3',camera),
           ('cameraPositionFract','f3',frac)]
        return runner.render('ripple gradients',diagnostic,64,32,[('colortex15',tile,'RGBA32F')],u)
    source=sample(blank,(-1000000,64,3000000),(.25,0,.50))
    shifted=sample(blank,(-999999,64,2999999),(.25,0,.50),origin=(-1.,0.,1.))
    def delta(a,b,sl):
        return max(abs(x-y) for ar,br in zip(a,b) for p,q in zip(ar,br) for x,y in zip(p[sl],q[sl]))
    require(delta(source,shifted,slice(0,2))<3e-5,'Rain moved when the camera anchor changed')
    for args in [dict(rain=0.),dict(precip=2),dict(precip=0),dict(sky=.7),dict(foot=.15)]:
        dry=sample(blank,(0,0,0),(0,0,0),**args)
        require(all(p[:2]==(0.,0.) for row in dry for p in row),'Invalid rain eligibility')
    rain_count=sum(max(abs(x) for x in p[:2])>1e-4 for row in source for p in row)
    impact=sample(history,(0,0,0),(0,0,0),rain=0.,origin=(-1.5,0,0))
    wake_count=sum(max(abs(x) for x in p[2:])>1e-4 for row in impact for p in row)
    require(rain_count>15 and wake_count>30,'Visible ripple controls failed')
    if panels is not None:
        rain_later=sample(blank,(-1000000,64,3000000),(.25,0,.50),clock=17.4)
        decayed=frame(history,14,.35,1.4)
        wake_later=sample(decayed,(0,0,0),(0,0,0),rain=0.,origin=(-1.5,0.,0.))
        def slopes(grid,axis):
            def channel(v): return int(round(255.*max(0.,min(1.,.5+2.*v))))
            return [[(channel(p[axis]),channel(p[axis+1]),125) for p in row] for row in reversed(grid)]
        clear=[[tuple([128,128,125]) for _ in range(64)] for _ in range(32)]
        panels['RAIN / SLOPE']=[clear,slopes(source,0),slopes(rain_later,0)]
        panels['WAKE / SLOPE']=[clear,slopes(impact,2),slopes(wake_later,2)]
    return dict(boat_packets=per[-1],current_velocity_mps=2.,rain_pixels=rain_count,wake_pixels=wake_count,
                world_anchor_error=delta(source,shifted,slice(0,2)),reset_cases=['skip','lag','teleport'])
