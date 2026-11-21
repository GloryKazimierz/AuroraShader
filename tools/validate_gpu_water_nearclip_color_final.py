"""Actual composite1 -> actual final.fsh plate and finite intermediate-coverage control."""
import argparse,copy,json,math,shutil,tempfile
from pathlib import Path
from validate_gpu import Runner,require,write_text,shader_digest
from validate_gpu_water_nearclip_color import ROOT,World,capture,scene,render,W,H
from nearclip_reference import near_point
from render_water_bench import png,draw_text

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,default=Path('docs/validation/NEARCLIP_COLOR_final_01.json'));parser.add_argument('--plate',type=Path,default=Path('docs/validation/NEARCLIP_COLOR_final_01.png'));args=parser.parse_args()
 root=ROOT.resolve();target=(root/args.report).resolve();plate=(root/args.plate).resolve()
 require(root in target.parents and root in plate.parents,'Evidence must remain in D staging')
 require(not target.exists() and not plate.exists(),'New evidence required')
 scratch=Path(tempfile.mkdtemp(prefix='nearclip-final-',dir=root)).resolve();digest=shader_digest()
 try:
  runner=Runner(scratch,r'C:\msys64\ucrt64\bin\g++.exe');display=runner.pair('final',dict(DEBUG_VIEW=0,SCENE_COLOR_MODE=1))
  strips=[];results=[];counterexample=None
  for depth,offset in ((.12,-.01),(.30,-.04),(.12,.01)):
   world=World(bed=8/9-depth);shadow,_=capture(runner,world);data=scene(world,offset)
   off=render(runner,data,shadow,dict(WATER_NEARCLIP=0));on=render(runner,data,shadow)
   final=[]
   for label,source in (('off',off),('on',on)):
    output=runner.render('actual final '+label,display,W,H,[('colortex0',source,'RGBA32F')]);final.append(output)
    require(all(p[3]==source[y][x][3] for y,row in enumerate(output) for x,p in enumerate(row)),'Final alpha changed')
   mask=[[(.1,.8,.3,1.) if on[y][x]!=off[y][x] else (.08,.08,.08,1.) for x in range(W)] for y in range(H)]
   strips.append(tuple(final)+(mask,));results.append(dict(depth_m=depth,eye_offset_m=offset,changed_pixels=sum(on[y][x]!=off[y][x] for y in range(H) for x in range(W))))
   if counterexample is None:
    def keys(point):
     uv=world.project(point);a,b=(math.floor(uv[i]*256-.5) for i in (0,1));return {(a+dx,b+dy) for dx in (0,1) for dy in (0,1)}
    candidates=[]
    for y in range(H):
     for x in range(W):
      if on[y][x]==off[y][x]:continue
      bottom=data['positions'][y][x];eye=data['eye'];near=near_point(eye,x,y,w=W,h=H)
      middle=((eye[0]+bottom[0])*.5,world.top,(eye[2]+bottom[2])*.5)
      preserved=keys(eye)|keys((eye[0],world.top,eye[2]))|keys((near[0],world.top,near[2]))|keys((bottom[0],world.top,bottom[2]))
      possible=keys(middle)-preserved
      if possible and math.dist(eye,bottom)>.6:candidates.append((math.dist(eye,bottom),x,y,next(iter(sorted(possible)))))
    require(candidates,'No independent intermediate-cell control')
    _,x,y,(sx,sy)=max(candidates);broken=copy.deepcopy(shadow)
    row=broken[0][1][sy];row[sx]=(0,0,0,0)
    image=render(runner,data,broken);require(image[y][x]==off[y][x],'Missing intermediate cell did not preserve native')
    counterexample=dict(pixel=[x,y],missing_shadow_texel=[sx,sy],endpoint_samples_preserved=True,exact_native=True)
   print('final plate row',depth,offset,flush=True)
  image=[];scale=3
  for strip in strips:
   header=[[(24,27,33)]*(W*3*scale) for _ in range(14)]
   for index,label in enumerate(('NATIVE FINAL','FINITE TRANSPORT FINAL','CHANGED MASK')):draw_text(header,index*W*scale+4,3,label)
   image.extend(header)
   for y in range(H-1,-1,-1):
    line=[]
    for field in strip:
     for p in field[y]:line.extend([tuple(round(max(0,min(1,v))*255) for v in p[:3])]*scale)
    image.extend([line]*scale)
  png(plate,image);require(shader_digest()==digest,'Source changed')
  report=dict(ok=True,shader_sha256=digest,gl=runner.gl,cases=results,intermediate_coverage_counterexample=counterexample,
   scope='Actual production composite1 including isolated near-clip experiment, then unchanged actual final.fsh. Analytic finite geometry and authored paired linear radiance; actual shadow.fsh compact records. No Minecraft screenshot, full renderer or FPS claim.')
  write_text(target,json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 finally:
  require(scratch.parent==root and scratch.name.startswith('nearclip-final-'),'Unsafe cleanup');shutil.rmtree(scratch)
if __name__=='__main__':main()
