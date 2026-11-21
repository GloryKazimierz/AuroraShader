"""Geometry-derived current direction and animated water sheets on synthetic raster planes."""
import math
from compile_glsl import SHADERS, expand
from validate_gpu import require, write_text
from render_water_bench import WATER_VERTEX, make_scene, unit

def current_tests(runner,panels=None):
    source = '#version 330 compatibility\n'+expand(SHADERS/'lib/water_filtered_waves.glsl')+'\n'+expand(SHADERS/'lib/water_flow.glsl')+'''
uniform vec3 facet, shift;
uniform float seconds;
layout(location=0) out vec4 result;
void main() {
    vec3 v=waterFlowVelocity(normalize(facet));
    vec3 p=vec3(gl_FragCoord.x*.09,gl_FragCoord.y*.07,2.0)+shift;
    result=vec4(waterFlowGradient(p,v,seconds,vec3(.09,0,0),vec3(0,.07,0)),length(v));
}
'''
    pair=runner.pair('composite',wrapper=source)
    width,height=32,16
    def sample(normal,dx,t):
        return runner.render('current advection',pair,width,height,uniforms=[
            ('facet','f3',normal),('shift','f3',dx),('seconds','f1',(t,))])
    down=sample((0,0,1),(0,0,0),0.)
    carried=sample((0,0,1),(0,-2.56,0),1.)
    stationary=sample((0,0,1),(0,0,0),1.)
    wrong=sample((0,0,1),(0,2.56,0),1.)
    wrap=sample((0,0,1),(0,0,0),3600.)
    def error(a,b):
        return max(abs(x-y) for ra,rb in zip(a,b) for pa,pb in zip(ra,rb) for x,y in zip(pa,pb))
    adv_error=error(down,carried)
    require(adv_error<3e-6 and error(down,stationary)>.01 and error(down,wrong)>.01,
            'Falling pattern failed direction or speed test')
    require(error(down,wrap)==0.,'Current discontinuity at the time wrap')
    # Positive production control uses actual slope from rasterized plane depth.
    # All faces share a plane-at-distance vertex; the material and environment
    # are the only changes in the rejection cases.
    vertex=runner.scratch/'flow-creek-plane.vert'
    header='''
uniform vec2 levels;
uniform int material;
out vec2 lmcoord,texcoord;
out vec4 glcolor;
out vec3 normalView;
flat out int waterSurface;
'''
    setup='''texcoord=gl_MultiTexCoord0.xy;lmcoord=levels;glcolor=vec4(1);
    normalView=benchNormal;waterSurface=material;
'''
    write_text(vertex,WATER_VERTEX.replace('void main() {',header+'\nvoid main() {'+setup))
    changes={}
    for kind,pitch,world_n,material,sky,slot in (
            ('flat',60.,(0,1,0),1,1,1),('river',55.,(.16,.98,.10),1,1,1),
            ('falls',-12.,(.72,0,.69),1,1,0),('glass',-12.,(.72,0,.69),0,1,0),
            ('dark-falls',-12.,(.72,0,.69),1,0,0)):
        c,s=math.cos(math.radians(pitch)),math.sin(math.radians(pitch))
        nx,ny,nz=unit(world_n)
        n=(nx,c*ny-s*nz,s*ny+c*nz)
        w,h=80,48
        scene=make_scene(pitch)
        bindings={n:(n,k,v) for n,k,v in scene['uniforms']}
        values={'benchNormal':n,'benchEyeHeight':(4.,),'viewWidth':(w,),'viewHeight':(h,)}
        for key,value in values.items(): bindings[key]=(key,bindings[key][1],value)
        bindings['levels']=('levels','f2',(.5/16,(15*sky+.5)/16))
        bindings['material']=('material','i1',(material,))
        names=['gtexture','lightmap','colortex5','colortex6','depthtex1']
        textures=[(names[0],[[(.25,.38,.42,.6)]],'RGBA32F'),(names[1],[[(1.,1.,1.,1.)]],'RGBA32F')]
        textures.extend((name,[[(1.,0,0,0)]],'R32F') for name in names[2:])
        outputs=[]
        samples=((0,.0),(1,.0),(1,.7))
        for enabled,seconds in samples:
            bindings['frameTimeCounter']=('frameTimeCounter','f1',(seconds,))
            opt=dict(WATER_OPTICS=1,WATER_FLOW=enabled,IRIS_FEATURE_PER_BUFFER_BLENDING=True,
                     WATER_DEPTH_TINT=0,WATER_SCREEN_REFLECTIONS=0,WATER_WAVE_STRENGTH=1.0,FOG_ENABLED=0)
            _,fs=runner.pair('gbuffers_water',opt)
            outputs.append(runner.render(kind,(vertex,fs),w,h,textures,list(bindings.values()),
                optional=list(bindings)+names,extra_targets=((1,1,'RGBA32F'),(2,2,'RGBA8')),read_target=slot))
        baseline,on,next_frame=outputs
        count=sum(a!=b for ar,br in zip(baseline,on) for a,b in zip(ar,br))
        moving=sum(a!=b for ar,br in zip(on,next_frame) for a,b in zip(ar,br))
        require(all(a[3]==b[3] for ar,br in zip(baseline,on) for a,b in zip(ar,br)),kind+' alpha/depth changed')
        require((count>100 and moving>100) if kind in ('river','falls') else count==0,kind+': wrong active pixels '+str(count))
        if panels is not None and kind in ('river','falls'):
            from render_water_bench import display_rows
            cells=[]
            for image in outputs:
                if slot==1:
                    def encode(p):
                        return tuple(int(255.*min(1.,max(0.,.5+2.*(x-y)))) for x,y in zip(p[:3],n))
                    cells.append([[encode(pixel) for pixel in row] for row in reversed(image)])
                else:
                    final=runner.render('falls final',runner.pair('final'),w,h,[('colortex0',image,'RGBA32F')])
                    cells.append(display_rows(final))
            panels['RIVER / NORMAL' if slot==1 else 'FALLS / COLOR']=cells
        changes[kind]=dict(changed=count,animated=moving)
    return dict(waterfall_advection_error=adv_error,wrap_error=error(down,wrap),faces=changes)

def motion_plate(panels,path):
    from render_water_bench import draw_text,png
    width,height=160,96
    rows=[[(18,24,30)]*(width*3) for _ in range(20+len(panels)*(height+18))]
    draw_text(rows,4,5,'SYNTHETIC WATER / OFF - ACTIVE - LATER')
    for i,(kind,images) in enumerate(panels.items()):
        y=20+i*(height+18)
        for j,image in enumerate(images):
            x=j*width
            draw_text(rows,x+3,y+5,kind+' / '+('OFF','ACTIVE','LATER')[j])
            ih,iw=len(image),len(image[0])
            for dy in range(height):
                scan=image[dy*ih//height]
                rows[y+18+dy][x:x+width]=[scan[dx*iw//width] for dx in range(width)]
    png(path,rows)
