"""Bounded native timer for the three per-frame spectral dispatches; no Minecraft FPS claim."""
import argparse,hashlib,json,math,os,shutil,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,configure,expand
from validate_gpu import require,write_text
from validate_gpu_water_fft import OPTIONS

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('--exclusive-window',action='store_true');parser.add_argument('--cxx',default=r'C:\msys64\ucrt64\bin\g++.exe');args=parser.parse_args()
 scratch=Path(tempfile.mkdtemp(prefix='.m6-cost-',dir=str(ROOT))).resolve()
 try:
  env=dict(os.environ,TMP=str(scratch),TEMP=str(scratch),TMPDIR=str(scratch))
  executable=scratch/'fft-timer.exe'
  build=subprocess.run([args.cxx,'-std=c++17','-O2','-Wall','-Wextra','-Wpedantic','-static',str(ROOT/'tools/gpu_fft_dynamics_harness.cpp'),'-lopengl32','-lgdi32','-luser32','-o',str(executable)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=120,env=env)
  require(build.returncode==0 and not build.stdout.strip(),'Timer build diagnostic: '+build.stdout)
  paths=[]
  for program in ('setup','begin','begin1','begin2'):
   path=scratch/(program+'.comp');write_text(path,configure(expand(SHADERS/(program+'.csh')),OPTIONS));paths.append(path)
  completed=subprocess.run([str(executable),'--time']+list(map(str,paths))+['17.5'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',timeout=90,env=env)
  require(completed.returncode==0 and not completed.stderr.strip(),completed.stderr+completed.stdout)
  payload=json.loads(completed.stdout);require(payload['ok'] and payload['image_bytes']==526400,'Compute timer did not execute')
  values=payload['elapsed_nanoseconds'];require(len(values)==25 and all(v>0 for v in values),'Incomplete GPU timing samples')
  ordered=sorted(values)
  payload.update(median_ms=ordered[12]/1e6,p95_ms=ordered[int(math.ceil(.95*len(values)))-1]/1e6,
    warmup_frames=6,timed_frames=25,coordinated_exclusive_gpu_window=args.exclusive_window,
    scope='Actual two-cascade row, column and moment reduction dispatches with image barriers per frame; setup, allocation, compilation, upload/readback excluded. Synthetic native OpenGL, no Minecraft FPS extrapolation.',
    source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'tools/gpu_fft_dynamics_harness.cpp',ROOT/'tools/gpu_harness.cpp']+[SHADERS/(name+'.csh') for name in ('setup','begin','begin1','begin2')]})
  destination=(ROOT/args.report).resolve();require(ROOT.resolve() in destination.parents,'Report must remain in candidate')
  with destination.open('x',encoding='utf-8') as out:json.dump(payload,out,indent=2)
  print('PASS FFT GPU median {:.6f} ms, p95 {:.6f} ms'.format(payload['median_ms'],payload['p95_ms']))
 finally:
  require(scratch.parent==ROOT.resolve() and scratch.name.startswith('.m6-cost-'),'Unsafe scratch cleanup');shutil.rmtree(str(scratch))

if __name__=='__main__':main()
