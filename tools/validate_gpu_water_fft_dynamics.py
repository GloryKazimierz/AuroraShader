"""Native persistent spectral displacement/moment proof with independent DFT."""
import argparse,hashlib,json,math,os,shutil,struct,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,expand,configure
from validate_gpu import Runner,require,write_text
from validate_gpu_water_fft import OPTIONS
from validate_water_fft import N,evolved,inverse_dft2,seeds,wavevector
from validate_water_fft_choppy import spectral_fields,spectral_moments,retained_energy,sample

def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def read(path,width,height):
 values=struct.unpack('<{}f'.format(width*height*4),path.read_bytes())
 return [[tuple(values[(y*width+x)*4:(y*width+x+1)*4]) for x in range(width)] for y in range(height)]

def dynamics_tests(runner,cxx):
 executable=runner.scratch/'dynamics.exe'
 result=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Wpedantic','-static',str(ROOT/'tools/gpu_fft_dynamics_harness.cpp'),'-lopengl32','-lgdi32','-luser32','-o',str(executable)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=120,env=runner.environment)
 require(result.returncode==0 and not result.stdout.strip(),'Dynamics build failed/warned: '+result.stdout)
 paths=[]
 for program in ('setup','begin','begin1','begin2'):
  path=runner.scratch/(program+'.comp');write_text(path,configure(expand(SHADERS/(program+'.csh')),OPTIONS));paths.append(path)
 output=runner.scratch/'images';output.mkdir()
 times=tuple(map(f32,(0.,2.,17.,17.+1/60.,48.,600.,3599.984375,0.)))
 result=subprocess.run([str(executable),'--run']+list(map(str,paths))+[str(output)]+list(map(str,times)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',timeout=90,env=runner.environment)
 require(result.returncode==0 and not result.stderr.strip(),result.stdout+result.stderr)
 driver=json.loads(result.stdout);require(driver['ok'] and driver['frames']==len(times),'Incomplete persistent native frames')
 reports=[];frames=[];bounds=[]
 for index,seconds in enumerate(times):
  frame={kind:read(output/(kind+'-{}.raw'.format(index)),2 if kind=='moments' else 128,66 if kind=='moments' else 64) for kind in ('seed','field','displacement','previous','moments')}
  maximum=0.;moment_error=0.;sample_power_error=0.
  for cascade in (0,1):
   actual_seed=[[complex(frame['seed'][y][x+64*cascade][0],frame['seed'][y][x+64*cascade][1]) for x in range(N)] for y in range(N)]
   if index==0:
    expected=seeds(cascade)
    require(all(abs(a-b)<.0002+abs(b)*.00002 for ar,br in zip(actual_seed,expected) for a,b in zip(ar,br)),'Actual seed formula differs')
    bounds.append([sum(abs(wavevector(x,y,cascade)[axis])*(abs(actual_seed[y][x])+abs(actual_seed[-y%N][-x%N])) for y in range(N) for x in range(N))/(N*N) for axis in (0,1)])
   h,_=evolved(actual_seed,cascade,seconds);spectral=spectral_fields(h,cascade)
   truth={key:inverse_dft2(spectral[key]) for key in ('height','sx','sz','dx','dz')}
   for y in range(N):
    for x in range(N):
     a=frame['field'][y][x+64*cascade];d=frame['displacement'][y][x+64*cascade]
     values=(a[0],a[1],a[2],d[0],d[1]);expected=tuple(truth[key][y][x].real for key in ('height','sx','sz','dx','dz'))
     error=max(abs(v-e) for v,e in zip(values,expected));maximum=max(maximum,error)
     require(error<.00002,'Actual dynamics differs from full independent DFT: '+str((index,cascade,x,y,error)))
     require(a[3]==1. and d[2:]==(0,1),'Dynamics channel/validity layout differs')
   actual_moment=frame['moments'][64][cascade];expected_moment=spectral_moments(h,cascade)
   moment_error=max(moment_error,max(abs(a-b) for a,b in zip(actual_moment,expected_moment)))
   require(all(abs(a-b)<2e-7 for a,b in zip(actual_moment,expected_moment)),'Spectral moments differ from independent power sum')
   sx=[[frame['field'][y][x+64*cascade][1] for x in range(N)] for y in range(N)]
   sz=[[frame['field'][y][x+64*cascade][2] for x in range(N)] for y in range(N)]
   for fx,fz in ((0.,0.),(.25,.75),(.5,.5)):
    measured=sum(sample(sx,x+fx,y+fz,64.)**2+sample(sz,x+fx,y+fz,64.)**2 for y in range(N) for x in range(N))/(N*N)
    expected=retained_energy(actual_moment,fx,fz);error=abs(measured-expected);sample_power_error=max(sample_power_error,error)
    require(error<2e-8,'Published moments do not match the actual native field after bilinear filtering')
  require(frame['moments'][65][0]==(seconds,times[index-1] if index else 0.,1.,1. if index else 0.),'Current/previous frame stamp differs')
  if index:
   require(frame['previous']==frames[-1]['displacement'],'Previous D was not copied bit-exact before current overwrite')
  else:
   require(all(pixel==(0,0,0,1) for row in frame['previous'] for pixel in row),'First-frame previous displacement was not reset')
  reports.append(dict(seconds=seconds,max_full_dft_error=maximum,max_spectral_moment_error=moment_error,max_actual_field_bilinear_power_error=sample_power_error,previous_displacement_exact=True))
  frames.append(frame)
  print('PASS native dynamics t={} DFT={} actual-field-moments={}'.format(seconds,maximum,sample_power_error),flush=True)
 column=[sum(c[axis] for c in bounds) for axis in (0,1)];bound=math.hypot(*column)
 require(bound<1.25,'Actual GPU seed violates declared sampled-map bound')
 require(frames[0]['field']==frames[5]['field']==frames[7]['field'],'Normal field time reset continuity failed')
 require(frames[0]['displacement']==frames[5]['displacement']==frames[7]['displacement'],'Displacement time reset continuity failed')
 from validate_gpu_water_fft_controls import spectral_controls
 controls=spectral_controls(runner,executable,frames[0])
 from validate_gpu_water_fft_consumers import consumer_tests
 consumers=consumer_tests(runner,frames,times)
 from validate_gpu_water_fft_production import production_tests
 production=production_tests(runner,frames[2]['field'],seconds=times[2])
 return dict(speed_and_mode_controls=controls,production=production,consumers=consumers,driver=driver,frames=reports,actual_seed_column_bounds=column,actual_sampled_map_bound=bound,
             guaranteed_min_singular_at_lambda_half=1-.5*bound,reset600_and3600_exact=True,
             native_frames=frames,times=times,scope='Actual persistent compute plus DFT/filtered-field truth; production foam/glint and whole-surface visual checks are separate')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('--cxx',default=r'C:\msys64\ucrt64\bin\g++.exe');args=parser.parse_args()
 scratch=Path(tempfile.mkdtemp(prefix='.m6b-native-',dir=str(ROOT))).resolve()
 try:
  runner=Runner(scratch,args.cxx);result=dynamics_tests(runner,args.cxx);result.pop('native_frames')
  result['shader_sha256']={str(p.relative_to(SHADERS)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in SHADERS.rglob('*') if p.is_file()}
  destination=(ROOT/args.report).resolve();require(ROOT.resolve() in destination.parents,'Report must stay in candidate')
  with destination.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2)
 finally:
  require(scratch.parent==ROOT.resolve() and scratch.name.startswith('.m6b-native-'),'Unsafe scratch cleanup');shutil.rmtree(str(scratch))

if __name__=='__main__':main()
