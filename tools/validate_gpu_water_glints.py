"""Measured Beckmann highlights and actual optical composite on controlled water."""
import math
from compile_glsl import SHADERS,expand
from validate_gpu import require
from validate_gpu_water_transport import FORMATS,slab_scene
from render_water_bench import unit

def glint_tests(runner,plate=None):
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_glint_model.glsl')+'''
uniform sampler2D views,lights;
uniform float alpha2;
layout(location=0) out vec4 outputLobe;
void main(){
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec3 n=vec3(0,1,0),v=texelFetch(views,p,0).xyz,l=texelFetch(lights,p,0).xyz;
    float forward=waterGlintBRDF(n,v,l,alpha2,1.333);
    float reverse=waterGlintBRDF(n,l,v,alpha2,1.333);
    outputLobe=vec4(forward,reverse,waterUnresolvedSlopeVariance(vec2(float(p.x)*.04,0),vec2(0,float(p.x)*.04),1),1);
}
'''
    pair=runner.pair('composite1',wrapper=source)
    views=[];lights=[]
    for i in range(64):
        angle=math.radians(i*1.3);view=(math.sin(angle),math.cos(angle),0.)
        for offset in (0.,.06,.17):
            lights.append(unit((-view[0]+offset,view[1],offset))+(1.,));views.append(view+(1.,))
    def lobe(a):
        return runner.render('highlight lobe',pair,len(views),1,[('views',[views],'RGBA32F'),('lights',[lights],'RGBA32F')],
                             [('alpha2','f1',(a,))])[0]
    water=lobe(.06**2);rough=lobe(.135**2)
    reciprocal=max(abs(f-r) for f,r,_,_ in water)
    require(all(math.isfinite(f) and f>=0. and abs(f-r)<max(2e-4,1e-5*f) for f,r,_,_ in water),
            'Invalid or nonreciprocal microfacet lobe')
    f0=((1.333-1.)/(1.333+1.))**2
    require(abs(water[0][0]-f0/(4*math.pi*.06**2))<2e-5,'Wrong normal incidence peak')
    require(rough[0][0]<water[0][0] and rough[2][0]>water[2][0], 'Rain broadened lobe incorrectly')
    require(water[0][2]==0. and abs(water[-1][2]-.00131016468)<3e-8,'Unresolved wave variance differs')
    # At the optical axis, orient the sun at the mirror direction of the flat
    # synthetic water. Compare lit, cave, new moon, bright moon and overlay.
    w,h=33,25
    scene=slab_scene(w,h,2.,55.)
    front=scene['front'][h//2][w//2];up=scene['up']
    v=unit(tuple(-q for q in front))
    nl=sum(a*b for a,b in zip(v,up))
    light=tuple(2*nl*u-c for u,c in zip(up,v))
    distances={}
    for label,sky,owner,moon,phase in (
            ('sun',1.,1/255,False,0),('cave',0.,1/255,False,0),('overlay',1.,1.,False,0),
            ('full-moon',1.,1/255,True,0),('new-moon',1.,1/255,True,4)):
        scene['textures']['colortex8']=[[(owner,0.,sky,0.)]*w for _ in range(h)]
        uniforms={n:(n,k,value) for n,k,value in scene['uniforms']}
        uniforms['shadowLightPosition']=('shadowLightPosition','f3',light)
        uniforms['sunPosition']=('sunPosition','f3',tuple((-1 if moon else 1)*q for q in light))
        uniforms['moonPhase']=('moonPhase','i1',(phase,))
        tex=[(k,img,FORMATS[k]) for k,img in scene['textures'].items()]
        out=[]
        for enabled in (0,1):
            settings=dict(WATER_OPTICS=1,WATER_CELESTIAL_GLINT=enabled,IRIS_FEATURE_PER_BUFFER_BLENDING=True,
                          WATER_SCREEN_REFLECTIONS=0,WATER_REFLECTION_STRENGTH=0.,SHADOWS_ENABLED=False,FOG_ENABLED=0)
            img=runner.render(label,runner.pair('composite1',settings),w,h,tex,list(uniforms.values()),
                              optional=list(uniforms)+list(scene['textures']))
            out.append(img)
        delta=max(abs(a[i]-b[i]) for ar,br in zip(*out) for a,b in zip(ar,br) for i in range(3))
        require(all(a[3]==b[3] for ar,br in zip(*out) for a,b in zip(ar,br)),label+' changed alpha')
        if label in ('sun','full-moon'):require(delta>.003,label+' glint inactive')
        else:require(delta==0.,label+' leaked light')
        distances[label]=delta
    require(distances['sun']>5*distances['full-moon'],'Lunar highlights too bright')
    report=dict(lobe_directions=len(views),max_absolute_reciprocity_error=reciprocal,rendered=distances,
                foam_overlap=foam_overlap_tests(runner))
    if plate is not None:
        report['plate']=glint_plate(runner,plate)
    return report

def glint_plate(runner,path):
    from validate_gpu_water_refraction import scene_capture
    from render_water_bench import png,draw_text,display_rows
    scene=scene_capture(runner,35.)
    width,height=scene['width'],scene['height']
    uniforms={n:(n,k,value) for n,k,value in scene['uniforms']}
    projection=uniforms['gbufferProjection'][2];up=uniforms['upPosition'][2]
    x,y=int(.53*width),int(.43*height)
    view=unit((-(2*(x+.5)/width-1)/projection[0],-(2*(y+.5)/height-1)/projection[5],1.))
    cosine=sum(a*b for a,b in zip(up,view))
    light=tuple(2*cosine*a-b for a,b in zip(up,view))
    textures=[(n,img,FORMATS[n]) for n,img in scene['textures'].items()]
    sheet=[[(20,24,30)]*(width*3) for _ in range(20+(height+18)*3)]
    draw_text(sheet,4,6,'DIRECTIONAL WATER HIGHLIGHTS / SYNTHETIC TEST POOL')
    measured={}
    for i,(label,moon,rain) in enumerate((('SUN',False,0.),('FULL MOON',True,0.),('RAIN',False,1.))):
        uniforms['shadowLightPosition']=('shadowLightPosition','f3',light)
        uniforms['sunPosition']=('sunPosition','f3',tuple((-1 if moon else 1)*q for q in light))
        uniforms['rainStrength']=('rainStrength','f1',(rain,))
        uniforms['moonPhase']=('moonPhase','i1',(0,))
        images=[]
        for active in (0,1):
            opts=dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_CELESTIAL_GLINT=active,
                      WATER_SCREEN_REFLECTIONS=0,SHADOWS_ENABLED=False,FOG_ENABLED=0)
            rgb=runner.render(label,runner.pair('composite1',opts),width,height,textures,list(uniforms.values()),
                              optional=list(uniforms)+list(scene['textures']))
            display=runner.render('glint final',runner.pair('final'),width,height,[('colortex0',rgb,'RGBA32F')])
            images.append(display_rows(display))
        a,b=images
        delta=[[tuple(min(255,abs(q-p)*6) for p,q in zip(pa,pb)) for pa,pb in zip(ar,br)] for ar,br in zip(a,b)]
        measured[label]=sum(max(p)>0 for row in delta for p in row)
        y0=20+i*(height+18)
        for col,img in enumerate((a,b,delta)):
            x0=col*width
            draw_text(sheet,x0+3,y0+5,label+' / '+('OFF','GLINT','DISPLAY DELTA X6')[col])
            for dy,row in enumerate(img):sheet[y0+18+dy][x0:x0+width]=row
    require(all(n>10 for n in measured.values()),'Missing visible glint control')
    png(path,sheet)
    return measured

def foam_overlap_tests(runner):
    # In linear scene RGB, foam should attenuate the existing glint by its coverage.
    w,h=64,48
    scene=slab_scene(w,h,2.,55.)
    up=scene['up'];v=unit(tuple(-p for p in scene['front'][h//2][w//2]))
    l=tuple(2*sum(a*b for a,b in zip(up,v))*a-b for a,b in zip(up,v))
    u={n:(n,k,value) for n,k,value in scene['uniforms']}
    u['shadowLightPosition']=('shadowLightPosition','f3',l);u['sunPosition']=('sunPosition','f3',l)
    u['moonPhase']=('moonPhase','i1',(0,))
    tex=[(n,img,FORMATS[n]) for n,img in scene['textures'].items()]
    overlap=0
    for seconds in (2.,17.,48.):
        u['frameTimeCounter']=('frameTimeCounter','f1',(seconds,))
        out={}
        for foam,glints in ((0,0),(0,1),(1,0),(1,1)):
            opts=dict(WATER_OPTICS=1,WATER_FOAM=foam,WATER_CELESTIAL_GLINT=glints,IRIS_FEATURE_PER_BUFFER_BLENDING=True,
                      WATER_WAVE_STRENGTH=1.,WATER_SCREEN_REFLECTIONS=0,SHADOWS_ENABLED=False,FOG_ENABLED=0)
            out[foam,glints]=runner.render('foam covers directional highlight',runner.pair('composite1',opts),w,h,
                tex,list(u.values()),optional=list(u)+list(scene['textures']))
        for i in range(h):
            for j in range(w):
                a,b,c,d=[out[k][i][j] for k in ((0,0),(0,1),(1,0),(1,1))]
                require(a[3]==b[3]==c[3]==d[3],'Foam/glint overlap changed alpha')
                for k in range(3):
                    direct=b[k]-a[k];covered=d[k]-c[k]
                    require(-1e-6<=covered<=direct+2e-6,'Foam amplified the highlight')
                    overlap+=direct>.005 and direct-covered>1e-5
    require(overlap>10,'No shared foam/glint pixels in control')
    return dict(frames=3,attenuated_channels=overlap)
