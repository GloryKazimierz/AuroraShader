"""Focused FFT capability/offline compiler matrix and exact old-path proof.
The --baseline directory is an independently captured prior shader tree; this
validator never restores/relabels the current source as its own reference.
"""
import argparse,hashlib,itertools,json,re,shutil,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,configure,expand
from validate_gpu import require,write_text


def expanded(path,shaders):
 text=path.read_text(encoding='utf-8')
 return re.sub(r'^#include "([^"]+)"\s*$',lambda m:expanded(shaders/m[1].lstrip('/'),shaders),text,flags=re.M)

def normalized(text):
 text='\n'.join(line for line in text.splitlines() if not line.startswith('#line'))
 return re.sub(r'\s+','',text)

def integration_checks(compiler,baseline):
 require(baseline.is_dir() and baseline.resolve()!=SHADERS.resolve(),'Independent baseline shader tree required')
 scratch=Path(tempfile.mkdtemp(prefix='.m6-offline-',dir=str(ROOT))).resolve()
 compiled=[];exact=[];cache={}
 def execute(args):
  result=subprocess.run([str(compiler)]+list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',timeout=30)
  require(result.returncode==0,result.stdout+result.stderr)
  return result.stdout
 def source(name,suffix,options,reference=False):
  path=(baseline if reference else SHADERS)/(name+suffix)
  return configure(expanded(path,baseline) if reference else expand(path),options)
 def pp(text,stage):
  key=(text,stage)
  if key not in cache:
   path=scratch/('preprocessed-{}.'.format(len(cache))+stage);write_text(path,text)
   cache[key]=normalized(execute(['-E','-S',stage,path]))
  return cache[key]
 try:
  common=dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_CAUSTICS=1,
              WATER_FOAM=2,WATER_CELESTIAL_GLINT=1,WATER_REFRACTION=2)
  variants=[]
  for compute,images,fft in itertools.product((False,True),repeat=3):
   variants.append(dict(common,IRIS_FEATURE_COMPUTE_SHADERS=compute,IRIS_FEATURE_CUSTOM_IMAGES=images,WATER_FFT=int(fft)))
  variants += [dict(common,IRIS_FEATURE_COMPUTE_SHADERS=True,IRIS_FEATURE_CUSTOM_IMAGES=True,WATER_FFT=1,**change)
               for change in ({'WATER_SURFACE_DETAIL':0},{'WATER_WAVES':0},{'WATER_WAVE_STRENGTH':0.0},{'WATER_WAVE_SPEED':0},{'WATER_WAVE_SPEED':2})]
  for index,options in enumerate(variants):
   active=options['IRIS_FEATURE_COMPUTE_SHADERS'] and options['IRIS_FEATURE_CUSTOM_IMAGES'] and options['WATER_FFT']==1 and options.get('WATER_SURFACE_DETAIL',1)==1 and options.get('WATER_WAVES',1)==1
   for program in ('gbuffers_water','shadow','composite1'):
    pair=[]
    for suffix,stage in (('.vsh','vert'),('.fsh','frag')):
     text=source(program,suffix,options);path=scratch/('{}-'.format(index)+program+'.'+stage);write_text(path,text);pair.append(path)
     if not active:
      old=source(program,suffix,options,True)
      require(pp(text,stage)==pp(old,stage),'FFT fallback source changed: '+str((program,suffix,options)))
      exact.append(dict(program=program,stage=stage,options=options))
    execute(['-l']+pair);compiled.append(dict(program=program,options=options))
   for program in ('setup','begin','begin1','begin2'):
    path=scratch/('{}-'.format(index)+program+'.comp');write_text(path,configure(expand(SHADERS/(program+'.csh')),options));execute(['-S','comp',path])
    compiled.append(dict(program=program,options=options))
  return dict(compilations=len(compiled),exact_disabled_stage_comparisons=len(exact),
              compiler=str(compiler),variants=variants,baseline_sha256={str(p.relative_to(baseline)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline.rglob('*') if p.is_file()},
              scope='Offline GLSL compile/link and exact preprocessed disabled paths; actual Iris properties parser checked separately')
 finally:
  require(scratch.parent==ROOT.resolve() and scratch.name.startswith('.m6-offline-'),'Unsafe scratch cleanup');shutil.rmtree(str(scratch))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',required=True);parser.add_argument('--report',required=True);parser.add_argument('--compiler',default=r'C:\VulkanSDK\1.4.363.0\Bin\glslangValidator.exe');args=parser.parse_args()
 result=integration_checks(Path(args.compiler),Path(args.baseline));destination=(ROOT/args.report).resolve()
 require(ROOT.resolve() in destination.parents,'Report must be within candidate')
 with destination.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2)
 print('PASS {} compiles, {} exact disabled-stage comparisons'.format(result['compilations'],result['exact_disabled_stage_comparisons']))

if __name__=='__main__':main()
