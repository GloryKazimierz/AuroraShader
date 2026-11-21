"""Finite shadow-sampled near-plane medium reconstruction, independent CPU geometry."""
import json,math,struct,zlib
from pathlib import Path
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def length(a):return math.sqrt(dot(a,a))
def unit(a):return mul(a,1/length(a))
def f32(v):return struct.unpack("<f",struct.pack("<f",v))[0]
def bits(v):return struct.unpack("<I",struct.pack("<f",v))[0]
def from_bits(v):return struct.unpack("<f",struct.pack("<I",v))[0]
def inside(p,b):return b[0]<=p[0]<=b[1] and b[2]<=p[2]<=b[3]
def ray_box(o,d,box):
    lo=0.;hi=math.inf
    for j in range(3):
        if abs(d[j])<1e-10:
            if not box[0][j]<=o[j]<=box[1][j]:return None
        else:
            a=(box[0][j]-o[j])/d[j];b=(box[1][j]-o[j])/d[j]
            lo=max(lo,min(a,b));hi=min(hi,max(a,b))
    return lo if hi>=lo else None
def pack(depth,normal=(0.,1.,0.)):
    slope=(normal[0]/normal[1],normal[2]/normal[1]);word=bits(depth)+1
    code=(int(math.floor(slope[0]*65534+32768+.5)),int(math.floor(slope[1]*65534+32768+.5)),word>>16,word&65535)
    return tuple(f32(v/65535) for v in code)
def decode(record,depth):
    if any(not math.isfinite(v) or not 0<=v<=1 for v in record):return None
    c=[int(math.floor(v*65535+.5)) for v in record];word=c[2]<<16|c[3]
    if c[0]==0 or c[1]==0 or word==0:return None
    old=from_bits(word-1)
    if not math.isfinite(old) or abs(old-depth)>1/16777215:return None
    return unit(((c[0]-32768)/65534,1.,(c[1]-32768)/65534))
class World:
    def __init__(self,light=(.3,.9,.2),top=8/9,bed=-3.,bounds=(-32,32,-32,32),opaque=(),glass=(),water_step=False,bed_step=False):
        self.light=unit(light);self.right=unit(cross(self.light,(0,0,1)))
        self.vertical=cross(self.right,self.light)
        self.top=top;self.bed=bed;self.bounds=bounds;self.opaque=opaque;self.glass=glass
        self.water_step=water_step;self.bed_step=bed_step
        self.size=256;self.half=8.;self.range=32.;self.cache={}
    def project(self,p):
        return (.5+.5*dot(p,self.right)/self.half,.5+.5*dot(p,self.vertical)/self.half,
                .5-.5*dot(p,self.light)/self.range)
    def point(self,x,y,z):
        u=2*(x+.5)/self.size-1;v=2*(y+.5)/self.size-1
        return add(add(mul(self.right,u*self.half),mul(self.vertical,v*self.half)),mul(self.light,(1-2*z)*self.range))
    def sample(self,x,y):
        if not 0<=x<self.size or not 0<=y<self.size:return None
        key=x,y
        if key in self.cache:return self.cache[key]
        o=self.point(x,y,0);d=mul(self.light,-1);hits=[];opaque=[]
        # Actual finite surfaces, not a plane filled across the shadow map.
        for height,kind in ((self.top,"water"),(self.bed,"bed")):
            heights=(height,height+.10) if (self.water_step if kind=="water" else self.bed_step) else (height,)
            for h in heights:
                t=(h-o[1])/d[1];p=add(o,mul(d,t))
                step=self.water_step if kind=="water" else self.bed_step
                edge=0. if step is True else float(step)
                allowed=not step or (h==height and p[0]<edge) or (h!=height and p[0]>=edge)
                if t>=0 and inside(p,self.bounds) and allowed:
                    hits.append((t,kind,p))
                    if kind=="bed":opaque.append((t,kind,p))
        for box in self.opaque+self.glass:
            t=ray_box(o,d,box)
            if t is not None:
                item=(t,"opaque" if box in self.opaque else "glass",add(o,mul(d,t)))
                hits.append(item)
                if box in self.opaque:opaque.append(item)
        first=min(hits,default=None);back=min(opaque,default=None)
        if first is None:return ((0,0,0,0),1.,1.)
        raw=f32(self.project(first[2])[2])
        depth=f32(round(raw*16777215)/16777215)
        bed=f32(round(self.project(back[2])[2]*16777215)/16777215) if back else 1.
        rec=pack(raw) if first[1]=="water" else (0,0,0,0)
        self.cache[key]=(rec,depth,bed)
        return self.cache[key]
def barycentric(p,a,b,c):
    v0=sub(b,a);v1=sub(c,a);v2=sub(p,a)
    d00=dot(v0,v0);d01=dot(v0,v1);d11=dot(v1,v1);d20=dot(v2,v0);d21=dot(v2,v1)
    den=d00*d11-d01*d01
    if den<=1e-14:return False
    v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den
    return min(1-v-w,v,w)>=-1e-6
def patch_at(world,query,poison=None):
    uv=world.project(query);bx=math.floor(uv[0]*world.size-.5);by=math.floor(uv[1]*world.size-.5)
    if bx<1 or by<1 or bx+1>=world.size-1 or by+1>=world.size-1:return None,"border"
    pts=[];beds=[]
    for dy,dx in ((0,0),(0,1),(1,0),(1,1)):
        x=bx+dx;y=by+dy;record,front,back=world.sample(x,y)
        if poison and dx==dy==0:
            if poison=="missing":record=(0,0,0,0)
            if poison=="mismatch":front+=.001
            if poison=="bottom":back=front
        normal=decode(record,front)
        if normal is None or not math.isfinite(back) or back<=front+1/16777215 or back>=1:
            return None,"record/depth"
        pts.append(world.point(x,y,front));beds.append(world.point(x,y,back))
    n=unit(cross(sub(pts[1],pts[0]),sub(pts[2],pts[0])))
    if n[1]<0:n=mul(n,-1)
    if n[1]<.995 or abs(dot(n,sub(pts[3],pts[0])))>.002:return None,"plane"
    if max(length(sub(a,b)) for a,b in ((pts[0],pts[1]),(pts[0],pts[2]),(pts[3],pts[1]),(pts[3],pts[2])))>.5:
        return None,"footprint"
    if max(p[1] for p in pts)-min(p[1] for p in pts)>.004:return None,"height"
    if max(p[1] for p in beds)-min(p[1] for p in beds)>.025 or min(p[1] for p in pts)-max(p[1] for p in beds)<.08:
        return None,"bed"
    return dict(points=pts,normal=n,beds=beds,key=(bx,by)),None
def triangle_interval(start,end,a,b,c):
    # Barycentric coordinates are affine along a line. Clip each of the three
    # inequalities to get the exact finite interval contained by this triangle.
    v0=sub(b,a);v1=sub(c,a);d00=dot(v0,v0);d01=dot(v0,v1);d11=dot(v1,v1)
    denominator=d00*d11-d01*d01
    if denominator<=1e-14:return None
    def bary(p):
        v=sub(p,a);d20=dot(v,v0);d21=dot(v,v1)
        y=(d11*d20-d01*d21)/denominator;z=(d00*d21-d01*d20)/denominator
        return 1-y-z,y,z
    first=bary(start);last=bary(end);lo=0.;hi=1.
    for a0,a1 in zip(first,last):
        delta=a1-a0
        if abs(delta)<1e-12:
            if a0<0:return None
        elif delta>0:lo=max(lo,-a0/delta)
        else:hi=min(hi,-a0/delta)
    return (lo,hi) if hi>=lo else None
def covered_segment(start,end,patches):
    intervals=[]
    for patch in patches:
        p=patch["points"]
        for tri in ((p[0],p[1],p[2]),(p[3],p[2],p[1])):
            result=triangle_interval(start,end,*tri)
            if result is not None:intervals.append(result)
    covered=0.
    for lo,hi in sorted(intervals):
        if lo>covered+1e-6:return False
        covered=max(covered,hi)
    return covered>=1-1e-6
def reconstruct(world,eye,near,owner_empty=True,poison=None):
    if not owner_empty or world.light[1]<.15:return {"medium":"unknown","reason":"native/light"}
    initial,why=patch_at(world,eye,poison)
    if initial is None:return {"medium":"unknown","reason":why}
    n=initial["normal"];anchor=initial["points"][0]
    se=dot(n,sub(eye,anchor));sn=dot(n,sub(near,anchor))
    if abs(se)>.05:return {"medium":"unknown","reason":"not near water"}
    foot_eye=sub(eye,mul(n,se));foot_near=sub(near,mul(n,sn))
    # The bootstrap plane only locates real samples. Both endpoint projections
    # are re-sampled, and their entire joining segment must lie in finite patches.
    first,why=patch_at(world,foot_eye,poison)
    if first is None:return {"medium":"unknown","reason":why}
    second,why=patch_at(world,foot_near,poison)
    if second is None:return {"medium":"unknown","reason":why}
    patches=[first,second]
    if any(dot(n,p["normal"])<.99999 or max(abs(dot(n,sub(q,anchor))) for q in p["points"])>.002 for p in patches):
        return {"medium":"unknown","reason":"patch discontinuity"}
    if not covered_segment(foot_eye,foot_near,patches):return {"medium":"unknown","reason":"finite support gap"}
    bed_top=max(q[1] for p in patches for q in p["beds"])
    if abs(sn)<.0001 or near[1]<=bed_top+.01:return {"medium":"unknown","reason":"boundary/bottom"}
    distance=length(sub(near,eye));crossing=None
    if se*sn<0:
        t=se/(se-sn);crossing=add(eye,mul(sub(near,eye),t));water=distance*(t if se<0 else 1-t)
    else:water=distance if sn<0 else 0.
    return dict(medium="water" if sn<0 else "air",water_length=water,crossing=crossing,normal=n,
                patches=[p["points"] for p in patches],near_height=sn,
                unique_2x2_patches=len({initial["key"],first["key"],second["key"]}))

def near_point(eye,x,y,w=64,h=36,pitch=0.,yaw=0.,fov=50.,near=.05):
    t=math.tan(math.radians(fov)/2);v=((2*(x+.5)/w-1)*t*w/h*near,(2*(y+.5)/h-1)*t*near,-near)
    a=math.radians(pitch);b=math.radians(yaw)
    # Inverse of the pitched view rotation, then yaw about world up.
    q=(v[0],math.cos(a)*v[1]+math.sin(a)*v[2],-math.sin(a)*v[1]+math.cos(a)*v[2])
    return add(eye,(math.cos(b)*q[0]+math.sin(b)*q[2],q[1],-math.sin(b)*q[0]+math.cos(b)*q[2]))
def exact_water_length(eye,near,top):
    a=eye[1]-top;b=near[1]-top;distance=length(sub(near,eye))
    if a*b<0:
        t=a/(a-b);return distance*(t if a<0 else 1-t)
    return distance if b<0 else 0.
def png(path,rows):
    def chunk(k,b):return struct.pack(">I",len(b))+k+b+struct.pack(">I",zlib.crc32(k+b)&0xffffffff)
    raw=b"".join(b"\0"+bytes(v for p in row for v in p) for row in rows)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",len(rows[0]),len(rows),8,2,0,0,0))
                     +chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))
def main():
    records=[];maximum=0.;accepted=0;crossings=0;masks=[];colors={"air":(237,195,95),"water":(39,127,194),"unknown":(51,54,60)}
    for light in ((.3,.9,.2),(.7,.5,.3),(.9,.2,.1)):
        strip=[]
        for offset in (-.04,-.01,0.,.01,.04):
            world=World(light);eye=(.017,world.top+offset,.027);counts=dict(air=0,water=0,unknown=0);mask=[]
            for y in range(36):
                row=[]
                for x in range(64):
                    near=near_point(eye,x,y);r=reconstruct(world,eye,near);counts[r["medium"]]+=1;row.append(colors[r["medium"]])
                    if r["medium"]!="unknown":
                        assert (r["medium"]=="water")==(near[1]<world.top)
                        error=abs(r["water_length"]-exact_water_length(eye,near,world.top));maximum=max(maximum,error)
                        assert error<.00025  # <=1e-4 relative Beer error at maximum configured red extinction .384/m
                        accepted+=1;crossings+=r["crossing"] is not None
                mask.append(row)
            assert counts["air"]+counts["water"]>0,(light,offset,counts)
            if abs(offset)<=.01:assert counts["air"] and counts["water"],(light,offset,counts)
            records.append(dict(light=light,eye_offset=offset,counts=counts));strip.append(mask)
        masks.append(strip)
    negatives=[];base=World();eye=(0.,base.top+.005,0.);near=near_point(eye,32,10)
    roof=((-2.,base.top+.8,-2.),(2.,base.top+1.,2.))
    glass=((-2.,base.top+.4,-2.),(2.,base.top+.45,2.))
    cases=[("missing-water",base,eye,near,{"poison":"missing"}),("unmatched-depth",base,eye,near,{"poison":"mismatch"}),
      ("opaque-not-separated",base,eye,near,{"poison":"bottom"}),("native-overlay",base,eye,near,{"owner_empty":False}),
      ("roof",World(opaque=(roof,)),eye,near,{}),("glass",World(glass=(glass,)),eye,near,{}),
      ("bed-too-close",World(bed=base.top-.03),eye,near,{}),
      ("shore",World(bounds=(-4,.01,-4,4)),eye,near,{}),
      ("water-step",World(water_step=True),eye,near,{}),("bed-step",World(bed_step=-1.26),eye,near,{}),
      ("low-light",World(light=(1.,.1,.2)),eye,near,{})]
    for label,w,e,n,kw in cases:
        r=reconstruct(w,e,n,**kw);assert r["medium"]=="unknown",(label,r)
        negatives.append(dict(label=label,reason=r["reason"]))
    rows=[]
    for strip in masks:
        for y in range(35,-1,-1):
            row=[]
            for mask in strip:
                for pixel in mask[y]:row.extend([pixel]*3)
            rows.extend([row]*3)
    root=Path(__file__).parent
    report=dict(ok=True,scope="Independent finite world geometry and simulated D24/RGBA16 shadow samples; CPU only, no Iris/GPU/game.",
        accepted_pixels=accepted,clipped_crossings=crossings,max_water_length_error_m=maximum,cases=records,negative_controls=negatives,
        contract="Four matched top-water samples form a finite quad. Optical shading normals do not define geometry. Unknown and native-overlaid pixels are unchanged.",
        limits=["No arbitrary volume inference","No information about sub-texel holes absent from all four samples","No covered/under-roof or bottom-face recovery","No game near-plane/medium evidence"])
    target=root/"NEARCLIP_CPU.json";assert not target.exists()
    target.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    png(root/"NEARCLIP_classification.png",rows)
    print(json.dumps({k:report[k] for k in ("accepted_pixels","clipped_crossings","max_water_length_error_m","negative_controls")},indent=2))
if __name__=="__main__":main()
