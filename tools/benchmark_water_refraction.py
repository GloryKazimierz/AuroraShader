"""Actual producer+resolve timing; ordinary planar quality only."""
import argparse,array,json,math,shutil,statistics,struct,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,expand
from validate_gpu import Runner,shader_digest
from validate_gpu_water_planar import OPTIONS
from validate_gpu_water_transport import FORMATS
from compile_glsl import configure
from validate_gpu import require,quote
from validate_gpu_water_transport import slab_scene
def f32(x):return struct.unpack("<f",struct.pack("<f",x))[0]
def setup(scratch,w,h,depth=2.,pitch=55.):
 scene=slab_scene(16,9,depth,pitch)
 names=("colortex0","colortex1","colortex5","colortex6","colortex7","colortex8","colortex9","depthtex0","depthtex1")
 paths={n:scratch/(n+".raw") for n in names};files={n:p.open("xb") for n,p in paths.items()}
 proj=next(v for n,k,v in scene["uniforms"] if n=="gbufferProjection")
 a=math.radians(pitch);c,s=math.cos(a),math.sin(a);up=(0.,f32(c),f32(s));normal=tuple(.5+.5*v for v in up)+(1.,)
 try:
  for y in range(h):
   rows={n:array.array("f") for n in names};ry=(2*(y+.5)/h-1)/proj[5]
   for x in range(w):
    rx=(2*(x+.5)/w-1)/proj[0];ray=(rx,ry,-1.);wy=c*ry-s
    tf=-4/wy;tb=(-4-depth)/wy;front=tuple(v*tf for v in ray);bed=tuple(v*tb for v in ray)
    zf=f32(.5+.5*(proj[10]*front[2]+proj[14])/-front[2]);zb=f32(.5+.5*(proj[10]*bed[2]+proj[14])/-bed[2])
    checker=.7 if (math.floor(bed[0])+math.floor(-s*bed[1]+c*bed[2]))%2 else 1.
    rgb=tuple(v*checker for v in (.6,.4,.2))
    values={"colortex0":tuple(.55*a+.45*b for a,b in zip((.045,.11,.13),rgb))+(1.,),
      "colortex1":normal,"colortex5":rgb+(1.,),"colortex6":(zb,0,0,1),"colortex7":up+(zf,),
      "colortex8":(1/255,0,1,0),"colortex9":(.65,0,0,1),"depthtex0":(zf,0,0,1),"depthtex1":(zb,0,0,1)}
    for n in names:rows[n].extend(values[n])
   for n in names:files[n].write(rows[n].tobytes())
 finally:
  for f in files.values():f.close()
 return scene["uniforms"],paths
def native(runner,manifest,command="--time-render"):
 # Own child PID and bounded communication make cancellation precise.
 process=subprocess.Popen([str(runner.executable),command,str(manifest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    encoding="utf-8",errors="replace",env=runner.environment)
 marker=runner.scratch/"active_owned_pid.txt";marker.write_text(str(process.pid),encoding="ascii")
 try:
  out,err=process.communicate(timeout=90)
 except BaseException:
  process.kill();process.communicate();raise
 finally:
  marker.unlink(missing_ok=True)
 require(not err.strip(),"Native stderr: "+err)
 result=json.loads(out);require(process.returncode==0 and result.get("ok"),str(result))
 if runner.gl is None:runner.gl=result["gl"]
 require(runner.gl==result["gl"],"Driver changed")
 return result
def draw(runner,folder,label,program,mode,w,h,uniforms,paths,dimensions,timed=True):
 options=dict(OPTIONS,WATER_REFRACTION=mode)
 vertex=folder/(label+".vert");fragment=folder/(label+".frag");output=folder/(label+".raw");manifest=folder/(label+".txt")
 vertex.write_text(configure(expand(ROOT/"shaders"/(program+".vsh")),options),encoding="utf-8")
 fragment.write_text(configure(expand(ROOT/"shaders"/(program+".fsh")),options),encoding="utf-8")
 lines=["shaders {} {}".format(quote(vertex),quote(fragment)),"target {} {} RGBA32F {}".format(w,h,quote(output)),"read_target 0"]
 for n,p in paths.items():
  tw,th=dimensions[n];lines.append("texture {} {} {} {} {}".format(quote(n),tw,th,FORMATS[n],quote(p)))
 for n,k,v in uniforms:lines.append("uniform {} {} {}".format(quote(n),k," ".join(map(str,v))))
 manifest.write_text("\n".join(lines)+"\n",encoding="utf-8")
 payload=native(runner,manifest,"--time-render" if timed else "--render")
 if not timed:return output
 values=[n/1e6 for n in payload["gpu_nanoseconds"]]
 row=dict(label=label,warmups=6,samples_ms=values,median_ms=statistics.median(values),p95_ms=sorted(values)[math.ceil(len(values)*.95)-1])
 print(json.dumps({k:row[k] for k in ("label","median_ms","p95_ms")}),flush=True)
 return row,output
def compare_files(a,b,w,h):
 changed=0;maxerror=0.;alpha=0.
 with a.open("rb") as af,b.open("rb") as bf:
  for _ in range(h):
   aa=struct.unpack("<"+"f"*(w*4),af.read(w*16));bb=struct.unpack("<"+"f"*(w*4),bf.read(w*16))
   for x in range(w):
    p=aa[x*4:x*4+4];q=bb[x*4:x*4+4]
    require(all(math.isfinite(v) for v in p+q),"Nonfinite pixels")
    changed+=p[:3]!=q[:3];maxerror=max(maxerror,max(abs(u-v) for u,v in zip(p[:3],q[:3])));alpha=max(alpha,abs(p[3]-q[3]))
 return dict(changed_rgb_pixels=changed,max_rgb_difference=maxerror,max_alpha_difference=alpha)
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--cxx",default=shutil.which("g++"),help="Installed compiler; no download")
 parser.add_argument("--report",type=Path,required=True,help="New checkpointed JSON under this project")
 args=parser.parse_args()
 target=(ROOT/args.report).resolve()
 require(ROOT.resolve() in target.parents and target.parent.is_dir(),"Report outside project or missing parent")
 require(not target.exists(),"Evidence exists")
 scratch=Path(tempfile.mkdtemp(prefix="tile-timer-",dir=ROOT)).resolve();require(scratch.parent==ROOT,"Unsafe scratch")
 digest=shader_digest()
 report=dict(ok=False,shader_sha256=digest,scope="Actual post-water proof + actual optical resolve; horizontal2m checker pool at55deg,100% authored water. Separate draw-only GL timer queries: upload/readback excluded. Six warmups,25 samples; no Minecraft/FPS or clocks/thermal claim.",resolutions=[],completed_draws=[])
 def save():target.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
 try:
  runner=Runner(scratch,args.cxx);previous=None
  for w,h in ((320,180),(640,360),(1280,720)):
   if previous is not None:require(previous*8<600,"Progressive-resolution safety gate")
   folder=scratch/str(w);folder.mkdir();uniforms,paths=setup(folder,w,h)
   dimensions={n:(w,h) for n in paths}
   proof,proof_file=draw(runner,folder,"producer"+str(w),"composite",1,w//8,h//8,uniforms,paths,dimensions)
   report["completed_draws"].append(proof);report["gl"]=runner.gl;save()
   paths["colortex11"]=proof_file;dimensions["colortex11"]=(w//8,h//8)
   baseline,off_file=draw(runner,folder,"same-ray"+str(w),"composite1",0,w,h,uniforms,paths,dimensions)
   report["completed_draws"].append(baseline);save()
   fast,on_file=draw(runner,folder,"planar"+str(w),"composite1",1,w,h,uniforms,paths,dimensions)
   report["completed_draws"].append(fast);save()
   active=compare_files(off_file,on_file,w,h)
   require(active["changed_rgb_pixels"]>1000 and active["max_alpha_difference"]==0,"Fast path inactive or alpha changed")
   # Explicit invalid proof tests ordinary fallback cost and exact full-size result.
   invalid=folder/"invalid-proof.raw"
   invalid.write_bytes(struct.pack("<4f",1e20,-1e20,1e20,-1e20)*((w//8)*(h//8)))
   invalid_paths=dict(paths,colortex11=invalid)
   bypass,bypass_file=draw(runner,folder,"unproved"+str(w),"composite1",1,w,h,uniforms,invalid_paths,dimensions)
   report["completed_draws"].append(bypass);save()
   fallback=compare_files(off_file,bypass_file,w,h)
   require(fallback["max_rgb_difference"]<2e-6 and fallback["max_alpha_difference"]==0,"Unproven ordinary path modified baseline")
   row=dict(resolution=[w,h],producer=proof,baseline=baseline,resolve=fast,unproven_resolve=bypass,active=active,fallback=fallback,
      combined_median_ms=proof["median_ms"]+fast["median_ms"],
      incremental_median_ms=proof["median_ms"]+fast["median_ms"]-baseline["median_ms"],
      note="Sum of separately measured pass medians, not end-to-end frame time.")
   report["resolutions"].append(row);report["gl"]=runner.gl;save()
   previous=max(proof["p95_ms"],fast["p95_ms"],bypass["p95_ms"])
  require(shader_digest()==digest,"Shader changed during measurement")
  report["ok"]=True;save()
 except BaseException as error:
  report["interrupted_or_failed"]=type(error).__name__+": "+str(error);save();raise
 finally:
  require(scratch.parent==ROOT and scratch.name.startswith("tile-timer-"),"Unsafe cleanup");shutil.rmtree(scratch)
if __name__=="__main__":main()
