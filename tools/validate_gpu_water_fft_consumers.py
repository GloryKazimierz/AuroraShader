"""Native sampled-map/Jacobian/history/missing-power consumers; actual FFT inputs."""
import math
from compile_glsl import SHADERS,expand
from validate_gpu import require
from validate_gpu_water_fft_production import ACTIVE,smooth
from validate_water_fft_choppy import sample_derivative,retained_energy


def reference(frame,q,dx,dy,previous=False):
 image=frame['previous' if previous else 'displacement'];result=[0.,0.];columns=[[0.,0.],[0.,0.]]
 footprint=max(math.hypot(*dx),math.hypot(*dy))
 for cascade,period,shortest in ((0,16.,1.5),(1,64.,8.)):
  weight=1-smooth(.25,.5,footprint/shortest)
  for axis in (0,1):
   field=[[image[y][x+64*cascade][axis] for x in range(64)] for y in range(64)]
   value,gx,gz=sample_derivative(field,q[0],q[1],period)
   result[axis]+=value*weight;columns[0][axis]+=gx*weight;columns[1][axis]+=gz*weight
 scale=.5*max(0.,min(1.,q[2]));d=[v*scale for v in result]
 j=[[1+scale*columns[0][0],scale*columns[1][0]],[scale*columns[0][1],1+scale*columns[1][1]]]
 return d,j,j[0][0]*j[1][1]-j[0][1]*j[1][0]

def variance(frame,q,dx,dy):
 footprint=max(math.hypot(*dx),math.hypot(*dy));missing=0.
 for cascade,period,shortest in ((0,16.,1.5),(1,64.,8.)):
  f=[((value%period)*64/period)%1 for value in q[:2]]
  moments=frame['moments'][64][cascade];weight=1-smooth(.25,.5,footprint/shortest)
  missing+=moments[0]-retained_energy(moments,f[0],f[1],weight)
 return missing*max(0.,min(1.,q[2]))**2

def consumer_tests(runner,native,times):
 source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_foam_model.glsl')+"""
uniform sampler2D queries;uniform vec2 testDx,testDy;uniform float requestedTime;
layout(location=0) out vec4 result;layout(location=1) out vec4 matrixResult;
layout(location=2) out vec4 statistics;layout(location=3) out vec4 inverseResult;
void main(){
 vec4 q=texelFetch(queries,ivec2(gl_FragCoord.xy),0);
 WaterFoamFlow flow=waterFoamFlowAt(q.xy,requestedTime,q.z,float(WATER_WAVE_SPEED),testDx,testDy);
 result=vec4(flow.displacement,flow.areaRatio,flow.valid?1:0);
 matrixResult=vec4(flow.jacobian[0],flow.jacobian[1]);
 statistics=vec4(flow.velocity,waterFftMissingSlopeVariance(vec3(q.x,0,q.y),testDx,testDy,q.z),1);
 vec2 material;WaterFoamFlow solved;
 bool valid=waterFoamMaterialPoint(q.xy,requestedTime,q.z,float(WATER_WAVE_SPEED),testDx,testDy,material,solved);
 inverseResult=vec4(material,solved.areaRatio,valid?1:0);
}
"""
 queries=[(x,z,strength,1.) for strength in (0.,.6,1.) for x,z in ((0.,0.),(.125,.375),(.2,.3),(2.75,3.125),(-.25,15.875),(63.75,63.5),(127.875,-127.75),(31.5,17.25))]
 # Quantize authored queries exactly as the raw GPU texture upload.
 import struct
 queries=[tuple(struct.unpack('<f',struct.pack('<f',v))[0] for v in q) for q in queries]
 pair=runner.pair('composite1',ACTIVE,wrapper=source);targets=((1,1,'RGBA32F'),(2,2,'RGBA32F'),(3,3,'RGBA32F'))
 reports=[]
 for frame_index,previous,footprint in ((2,False,0.),(3,False,0.),(3,True,0.),(3,False,.5),(3,False,4.),(7,False,0.),(7,True,0.)):
  frame=native[frame_index];now=times[frame_index];requested=times[frame_index-1] if previous else now
  dx=(footprint,0.);dy=(0.,footprint*.5)
  textures=[('queries',[queries],'RGBA32F'),('waterFftDisplacementSampler',frame['displacement'],'RG32F'),
            ('waterFftPreviousDisplacementSampler',frame['previous'],'RG32F'),('waterFftMomentSampler',frame['moments'],'RGBA32F')]
  uniforms=[('frameTimeCounter','f1',(now,)),('requestedTime','f1',(requested,)),('testDx','f2',dx),('testDy','f2',dy),
            ('cameraPositionInt','i3',(0,0,0)),('cameraPositionFract','f3',(0,0,0))]
  images=[runner.render('FFT consumer slot'+str(slot),pair,len(queries),1,textures,uniforms,extra_targets=targets,read_target=slot)[0] for slot in range(4)]
  max_d=max_j=max_area=max_velocity=max_variance=max_inverse=0.
  for index,q in enumerate(queries):
   d,j,area=reference(frame,q,dx,dy,previous);flat=(j[0][0],j[1][0],j[0][1],j[1][1])
   actual=images[0][index];require(actual[3]==1.,'Valid FFT material mapping rejected')
   error=max(abs(a-b) for a,b in zip(actual[:2],d));max_d=max(max_d,error);require(error<3e-6,'FFT D mismatch')
   error=max(abs(a-b) for a,b in zip(images[1][index],flat));max_j=max(max_j,error);require(error<4e-6,'FFT Jacobian is not derivative of same bilinear D')
   error=abs(actual[2]-area);max_area=max(max_area,error);require(error<4e-6,'FFT area mismatch')
   expected_velocity=(0.,0.);elapsed=frame['moments'][65][0][0]-frame['moments'][65][0][1]
   if elapsed<0:elapsed+=3600
   if frame['moments'][65][0][3]==1 and 0<elapsed<=.1:
    current=reference(frame,q,dx,dy,False)[0];old=reference(frame,q,dx,dy,True)[0]
    expected_velocity=tuple((a-b)/elapsed for a,b in zip(current,old))
   error=max(abs(a-b) for a,b in zip(images[2][index][:2],expected_velocity));max_velocity=max(max_velocity,error);require(error<4e-6,'FFT interval velocity mismatch')
   error=abs(images[2][index][2]-variance(frame,q,dx,dy));max_variance=max(max_variance,error);require(error<3e-9,'FFT filtered missing-power mismatch')
   solved=images[3][index];require(solved[3]==1.,'FFT three-step material inverse rejected')
   residual=reference(frame,(solved[0],solved[1],q[2]),dx,dy,previous)[0]
   error=math.hypot(solved[0]+residual[0]-q[0],solved[1]+residual[1]-q[1]);max_inverse=max(max_inverse,error);require(error<4e-5,'FFT inverse residual exceeds independent map truth')
   if q[2]==0.:require(actual==(0,0,1,1) and images[1][index]==(1,0,0,1),'FFT zero-strength material map is not exact identity')
  reports.append(dict(frame_index=frame_index,previous=previous,footprint=footprint,queries=len(queries),max_D_error=max_d,max_J_error=max_j,max_area_error=max_area,max_velocity_error=max_velocity,max_missing_power_error=max_variance,max_inverse_residual=max_inverse))
 # Corrupt independently one required ownership/size/value constraint at a time.
 import copy
 invalid=[]
 for label in ('stale-time','invalid-current','wrong-moment-size','missing-previous','wrong-current-size',
               'wrong-previous-size','oversized-D','nonmodel-J','invalid-power','extreme-footprint','unavailable-time'):
  frame=copy.deepcopy(native[3]);requested=times[2] if label in ('missing-previous','wrong-previous-size') else times[3]
  expected_flow=label=='invalid-power';expected_zero_power=label in ('stale-time','invalid-current','wrong-moment-size','invalid-power','extreme-footprint')
  dx,dy=(0.,0.),(0.,0.)
  if label in ('stale-time','invalid-current','missing-previous'):
   state=list(frame['moments'][65][0]);state[0 if label=='stale-time' else 2 if label=='invalid-current' else 3]+=1. if label=='stale-time' else -1.;frame['moments'][65][0]=tuple(state)
  if label=='wrong-moment-size':frame['moments']=[[(0,0,0,0)]]
  if label=='wrong-current-size':frame['displacement']=[[(0,0,0,1)]]
  if label=='wrong-previous-size':frame['previous']=[[(0,0,0,1)]]
  if label=='oversized-D':frame['displacement']=[[(3,3,0,1)]*128 for _ in range(64)]
  if label=='nonmodel-J':frame['displacement']=[[(.4 if x%2 else -.4,0,0,1) for x in range(128)] for _ in range(64)]
  if label=='invalid-power':frame['moments'][64][0]=(-.1,0,0,0)
  if label=='extreme-footprint':dx=(65537.,0.)
  if label=='unavailable-time':requested=42.
  textures=[('queries',[queries],'RGBA32F'),('waterFftDisplacementSampler',frame['displacement'],'RG32F'),
            ('waterFftPreviousDisplacementSampler',frame['previous'],'RG32F'),('waterFftMomentSampler',frame['moments'],'RGBA32F')]
  uniforms=[('frameTimeCounter','f1',(times[3],)),('requestedTime','f1',(requested,)),('testDx','f2',dx),('testDy','f2',dy),
            ('cameraPositionInt','i3',(0,0,0)),('cameraPositionFract','f3',(0,0,0))]
  result=runner.render('FFT rejection '+label,pair,len(queries),1,textures,uniforms,extra_targets=targets)[0]
  power=runner.render('FFT rejection power '+label,pair,len(queries),1,textures,uniforms,extra_targets=targets,read_target=2)[0]
  require(all(p[3]==float(expected_flow) for p in result),'Incorrect invalid-data material fallback: '+label)
  require(all(math.isfinite(v) for p in result+power for v in p),'Invalid data escaped finite guards: '+label)
  if expected_zero_power:require(all(p[2]==0. for p in power),'Invalid power did not preserve base roughness: '+label)
  invalid.append(label)
 return dict(cases=reports,rejections=invalid,gl=runner.gl,scope='Native exact bilinear material mapping, Jacobian, previous-field advection and global filtered spectral power; not full resolved-water visual test')
