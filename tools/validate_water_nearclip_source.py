"""Focused source preservation and offline linking for isolated near-clip experiment."""
import argparse,ast,itertools,json,re,shutil,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,configure,expand
from validate_gpu import require,shader_digest,write_text
from validate_gpu_water_nearclip_color import SETTINGS
BASE=None
COMPILER=r'C:\VulkanSDK\1.4.363.0\Bin\glslangValidator.exe'
def base_expand(path):
 text=path.read_text(encoding='utf-8')
 return re.sub(r'^#include "([^"]+)"\s*$',lambda m:base_expand(BASE/m[1].lstrip('/')),text,flags=re.M)
def main():
 global BASE
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--baseline",type=Path,required=True,help="Independent shader directory from the preceding Git commit.");parser.add_argument('--report',type=Path,default=Path('docs/validation/NEARCLIP_COLOR_source_01.json'));args=parser.parse_args()
 BASE=args.baseline.resolve();require((BASE/"composite1.fsh").is_file() and BASE!=SHADERS.resolve(),"Independent shader directory required")
 root=ROOT.resolve();target=(root/args.report).resolve();require(root in target.parents and not target.exists(),'New local evidence required')
 scratch=Path(tempfile.mkdtemp(prefix='nearclip-source-',dir=root)).resolve()
 try:
  comparisons=[];pins=0
  for p in BASE.rglob('*'):
   if not p.is_file():continue
   relative=p.relative_to(BASE)
   if str(relative).replace('\\','/') in ('composite1.fsh','shaders.properties','lang/zh_cn.lang','lang/en_us.lang'):continue
   require((SHADERS/relative).read_text(encoding='utf-8')==p.read_text(encoding='utf-8'),'Changed baseline:'+str(relative));pins+=1
  bypass=[{},dict(SETTINGS,WATER_NEARCLIP=0),dict(SETTINGS,WATER_CAUSTICS=0),dict(SETTINGS,WATER_OPTICS=0),
    dict(SETTINGS,IRIS_FEATURE_PER_BUFFER_BLENDING=False),dict(SETTINGS,SCENE_COLOR_MODE=0),
    dict(SETTINGS,DEBUG_VIEW=8),dict(SETTINGS,WATER_STYLE=0),dict(SETTINGS,SHADOWS_ENABLED=False)]
  for index,options in enumerate(bypass):
   for suffix,stage in (('vsh','vert'),('fsh','frag')):
    tokens=[]
    for label,source in (('before',base_expand(BASE/('composite1.'+suffix))),('after',expand(SHADERS/('composite1.'+suffix)))):
     path=scratch/(label+str(index)+'.'+stage);write_text(path,configure(source,options))
     result=subprocess.run([COMPILER,'-E',str(path)],capture_output=True,text=True,check=True)
     tokens.append(re.findall(r'\w+|[^\s]',result.stdout))
    require(tokens[0]==tokens[1],'Bypass active code changed:'+str((index,stage)))
    comparisons.append(dict(configuration=index,stage=stage,tokens=len(tokens[0])))
  configs=bypass+[dict(SETTINGS,WATER_FOAM=foam,WATER_REFRACTION=refraction,WATER_UNDERWATER=under,WATER_WAVES=waves)
    for foam,refraction,under,waves in itertools.product((0,2),(0,1,3),(0,1),(0,1))]
  for index,options in enumerate(configs):
   files=[]
   for suffix,stage in (('vsh','vert'),('fsh','frag')):
    path=scratch/('source'+str(index)+'.'+stage);write_text(path,configure(expand(SHADERS/('composite1.'+suffix)),options));files.append(str(path))
   run=subprocess.run([COMPILER,'-l',*files],capture_output=True,text=True)
   require(run.returncode==0,'Offline case '+str(index)+':'+run.stdout+run.stderr)
  for name in ('validate_gpu_water_nearclip_color.py','validate_gpu_water_nearclip_color_final.py','validate_water_nearclip_source.py'):
   ast.parse((root/'tools'/name).read_text(encoding='utf-8'))
  for name in ('water_nearclip.glsl','water_nearclip_color.glsl','water_nearclip_settings.glsl'):
   text=(SHADERS/'lib'/name).read_text(encoding='utf-8');require(all(line==line.rstrip() for line in text.splitlines()),'Trailing whitespace')
  write_text(target,json.dumps(dict(ok=True,shader_sha256=shader_digest(),baseline_pinned_files=pins,
   exact_bypass_stages=len(comparisons),bypass_comparisons=comparisons,offline_linked_pairs=len(configs),python_ast=True,whitespace=True),indent=2)+'\n')
  print('PASS',pins,'pins',len(comparisons),'exact stages',len(configs),'offline pairs')
 finally:
  require(scratch.parent==root and scratch.name.startswith('nearclip-source-'),'Unsafe cleanup');shutil.rmtree(scratch)
if __name__=='__main__':main()
