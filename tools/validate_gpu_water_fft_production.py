"""Real water/shadow fragments consume the same actual IFFT image.
Synthetic fullscreen geometry establishes precise world derivatives; this is
not a Minecraft vertex attribute, program scheduling or runtime acceptance test.
"""
import math
import struct
from compile_glsl import SHADERS,expand
from validate_gpu import require,write_text,compare
from validate_gpu_depth import matrix_uniform
from validate_gpu_water_capture import constant,WATER_TARGETS

ACTIVE=dict(WATER_FFT=1,IRIS_FEATURE_COMPUTE_SHADERS=True,IRIS_FEATURE_CUSTOM_IMAGES=True,
            WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_CAUSTICS=1,
            FOG_ENABLED=0,WATER_SCREEN_REFLECTIONS=0,WATER_WAVE_STRENGTH=0.6)
INV_VIEW=((1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1))
VIEW=((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1))
VERTEX="""#version 330 compatibility
out vec2 texcoord,lmcoord;out vec4 glcolor;out vec3 normalView;
flat out int waterSurface;
void main(){gl_Position=gl_Vertex;texcoord=gl_MultiTexCoord0.xy;lmcoord=vec2(.96875);
glcolor=vec4(1,1,1,.55);normalView=vec3(0,0,1);waterSurface=1;}
"""
SHADOW_VERTEX="""#version 330 compatibility
uniform vec2 positionOffset;
out vec2 texcoord;out vec4 glcolor;out vec3 causticPlayerPosition,causticNormalWorld;
flat out int causticWaterMaterial;
void main(){gl_Position=gl_Vertex;texcoord=gl_MultiTexCoord0.xy;glcolor=vec4(1);
causticPlayerPosition=vec3(gl_Vertex.x*16.0+positionOffset.x,-4.0,-gl_Vertex.y*8.0+positionOffset.y);
causticNormalWorld=vec3(0,1,0);causticWaterMaterial=1;}
"""

def smooth(a,b,x):
 t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)

def normalized(v):
 length=math.sqrt(sum(x*x for x in v));return tuple(x/length for x in v)

def sampled_gradient(field,world,footprint=.5):
 result=[0.,0.]
 for cascade,period,shortest in ((0,16.,1.5),(1,64.,8.)):
  weight=1-smooth(.25,.5,footprint/shortest)
  location=[(v%period)*64/period for v in world];first=[int(math.floor(v)) for v in location]
  fraction=[v-int(math.floor(v)) for v in location]
  for y in (0,1):
   for x in (0,1):
    value=field[(first[1]+y)%64][cascade*64+(first[0]+x)%64]
    w=(fraction[0] if x else 1-fraction[0])*(fraction[1] if y else 1-fraction[1])*weight
    for axis in (0,1):result[axis]+=value[axis+1]*w
 length=math.hypot(*result)
 if length>.12:result=[v*.12/length for v in result]
 return result

def production_tests(runner,field):
 width=height=64
 vertex=runner.scratch/'fft-water.vert';write_text(vertex,VERTEX)
 shadow_vertex=runner.scratch/'fft-shadow.vert';write_text(shadow_vertex,SHADOW_VERTEX)
 textures=[('gtexture',constant((.25,.5,.75,1),1,1),'RGBA32F'),
           ('lightmap',constant((1,1,1,1),1,1),'RGBA32F'),
           ('waterFftOutputSampler',field,'RGBA32F')]
 def uniforms(anchor=(16777217,64,-16777217),offset=(0.,0.)):
  inv=((16,0,0,offset[0]),(0,8,0,-offset[1]),(0,0,1,-4),(0,0,0,1))
  return [('gbufferProjectionInverse','m4',matrix_uniform(inv)),
          ('gbufferModelViewInverse','m4',matrix_uniform(INV_VIEW)),
          ('cameraPositionInt','i3',anchor),('cameraPositionFract','f3',(.125,0,.375)),
          ('frameTimeCounter','f1',(17.5,)),('upPosition','f3',(0,0,1)),
          ('sunPosition','f3',(40,20,80)),('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),
          ('isEyeInWater','i1',(0,)),('blindness','f1',(0.,)),('darknessFactor','f1',(0.,)),
          ('rainStrength','f1',(0.,)),('eyeBrightnessSmooth','i2',(240,240)),
          ('fogColor','f3',(.55,.65,.7)),('viewWidth','f1',(width,)),('viewHeight','f1',(height,)),
          ('blendFunc','i4',(770,771,1,771)),('alphaTestRef','f1',(.1,))]
 # Inputs which legitimately optimize away at different compile-time settings.
 optional=['frameTimeCounter','cameraPositionInt','cameraPositionFract','gbufferModelViewInverse',
           'waterFftOutputSampler','sunPosition','eyeBrightnessSmooth','fogColor']
 _,fragment=runner.pair('gbuffers_water',ACTIVE)
 base=runner.render('FFT actual water normals',(vertex,fragment),width,height,textures,uniforms(),
                    optional=optional,extra_targets=WATER_TARGETS,read_target=1)
 counts=runner.render('FFT actual water ownership',(vertex,fragment),width,height,textures,uniforms(),
                      optional=optional,extra_targets=WATER_TARGETS,read_target=2)
 error=0.;changed=0
 for y in range(height):
  for x in range(width):
   world=(1+.125+32*((x+.5)/width-.5),127+.375-16*((y+.5)/height-.5))
   slope=sampled_gradient(field,world)
   expected=normalized((-.6*slope[0],.6*slope[1],1.))
   actual=base[y][x];delta=max(abs(a-b) for a,b in zip(actual[:3],expected));error=max(error,delta)
   require(delta<2e-6,'Actual water did not consume FFT slopes: '+str((x,y,delta)))
   require(actual[3]==.5,'FFT changed native water raster depth')
   require(abs(counts[y][x][0]-1/255)<1e-9 and counts[y][x][1:]==(1,1,0),'FFT changed eligible water ownership')
   changed+=max(abs(v) for v in actual[:2])>1e-4
 require(changed>4000,'FFT wave field was not spatially varied')
 shifted=runner.render('FFT anchor movement',(vertex,fragment),width,height,textures,
                      uniforms((16777218,64,-16777218),(-1.,1.)),optional=optional,
                      extra_targets=WATER_TARGETS,read_target=1)
 anchor_error=max(abs(a-b) for ar,br in zip(base,shifted) for ap,bp in zip(ar,br) for a,b in zip(ap,bp))
 require(anchor_error<2e-6,'FFT normals swim when camera integer anchor changes')
 shadow_uniforms=[v for v in uniforms() if v[0] in ('gbufferModelViewInverse','cameraPositionInt','cameraPositionFract','frameTimeCounter')]
 shadow_uniforms += [('gbufferModelView','m4',matrix_uniform(VIEW)),('positionOffset','f2',(0.,0.))]
 _,shadow_fragment=runner.pair('shadow',ACTIVE)
 shadow=runner.render('FFT actual packed shadow normals',(shadow_vertex,shadow_fragment),width,height,
     [textures[0],textures[2]],shadow_uniforms,storage='RGBA16',optional=['frameTimeCounter'])
 shadow_error=0.
 for y in range(height):
  for x in range(width):
   record=shadow[y][x];code=[int(math.floor(v*65535+.5)) for v in record]
   require(code[0]>0 and code[1]>0,'Actual FFT shadow capture was invalid')
   depth=struct.unpack('<f',struct.pack('<I',((code[2]<<16)|code[3])-1))[0]
   require(depth==.5,'Actual FFT shadow record lost source depth')
   normal=normalized(((code[0]-32768)/65534.,1.,(code[1]-32768)/65534.))
   view=base[y][x][:3];expected=(view[0],view[2],-view[1])
   delta=max(abs(a-b) for a,b in zip(normal,expected));shadow_error=max(shadow_error,delta)
   require(delta<1.6e-5,'Water and packed shadow normals disagree: '+str((x,y,delta)))
 # Off and each absent capability must use the exact same pre-existing source
 # path, not an empty compute substitute or an uninitialized image.
 comparisons=[]
 _,off_fragment=runner.pair('gbuffers_water',dict(ACTIVE,WATER_FFT=0))
 off=runner.render('FFT baseline off',(vertex,off_fragment),width,height,textures,uniforms(),
                   optional=optional,extra_targets=WATER_TARGETS,read_target=1)
 for compute,images in ((False,False),(False,True),(True,False)):
  opts=dict(ACTIVE,IRIS_FEATURE_COMPUTE_SHADERS=compute,IRIS_FEATURE_CUSTOM_IMAGES=images)
  _,fs=runner.pair('gbuffers_water',opts)
  current=runner.render('FFT absent capability',(vertex,fs),width,height,textures,uniforms(),
                       optional=optional,extra_targets=WATER_TARGETS,read_target=1)
  comparisons.append(compare(current,off,'Missing compute={} images={}'.format(compute,images)))
 # Invalid image dimensions have a defined six-wave fallback, not black/NaN water.
 invalid=[textures[0],textures[1],('waterFftOutputSampler',constant((0,0,0,0),1,1),'RGBA32F')]
 fallback=runner.render('FFT invalid image fallback',(vertex,fragment),width,height,invalid,uniforms(),
                        optional=optional,extra_targets=WATER_TARGETS,read_target=1)
 comparisons.append(compare(fallback,off,'Invalid FFT image falls back exactly'))
 _,flat_fragment=runner.pair('gbuffers_water',dict(ACTIVE,WATER_WAVE_STRENGTH=0.0))
 flat=runner.render('FFT zero strength',(vertex,flat_fragment),width,height,textures,uniforms(),
                    optional=optional,extra_targets=WATER_TARGETS,read_target=1)
 require(all(p==(0,0,1,.5) for row in flat for p in row),'FFT strength0 is not exact flat baseline')
 # Real helper bodies: no legacy six-mode Jacobian/variance may survive in FFT mode.
 models=expand(SHADERS/'lib/water_foam_model.glsl')+'\n'+expand(SHADERS/'lib/water_glint_model.glsl')
 wrapper='#version 330 compatibility\n'+models+"""
layout(location=0) out vec4 result;
layout(location=1) out vec4 evidence;
void main(){
 WaterFoamFlow f=waterFoamFlowAt(vec2(gl_FragCoord.xy),17.5,.6,1.,vec2(.01,0),vec2(0,.01));
 result=vec4(f.displacement,f.areaRatio,waterUnresolvedSlopeVariance(vec2(1,0),vec2(0,1),.6));
 evidence=vec4(waterFoamEvidence(f.areaRatio,-1.,1.,1.),waterFoamEvidence(f.areaRatio,.05,1.,1.),f.velocity);
 if(!f.valid)result=vec4(-99);
}
"""
 pair=runner.pair('composite1',ACTIVE,wrapper=wrapper)
 flow=runner.render('FFT identity foam and base variance',pair,8,8,extra_targets=((1,1,'RGBA32F'),))
 evidence=runner.render('FFT shore-only foam evidence',pair,8,8,extra_targets=((1,1,'RGBA32F'),),read_target=1)
 require(all(p==(0,0,1,0) for row in flow for p in row),'FFT pretends to use legacy displacement or variance')
 require(all(p[0]==0 and p[1]>.5 and p[2:]==(0,0) for row in evidence for p in row),'FFT shoreline/crest foam downgrade failed')
 return dict(resolution=[width,height],actual_water_max_normal_error=error,
             actual_shadow_quantized_max_normal_error=shadow_error,camera_anchor_max_error=anchor_error,
             varied_water_pixels=changed,exact_fallbacks=comparisons,zero_strength_exact=True,
             fft_foam_identity_and_shore_evidence=True,fft_legacy_unresolved_variance_disabled=True,
             scope='Actual water/shadow fragment programs on authored geometry, with actual native compute output; no Iris scheduling or Minecraft runtime claim')

def spectral_views(runner,fields,path):
    from render_water_bench import WIDTH,HEIGHT,display_rows,draw_text,png,unit
    from validate_gpu_water_refraction import scene_capture
    from validate_gpu_water_transport import FORMATS
    sheet=[[(20,24,32)]*(3*WIDTH) for _ in range(20+3*(HEIGHT+18))]
    draw_text(sheet,4,6,'SPECTRAL SURFACE / NATIVE HDR SHADE AND FINAL / AUTHORED POOL')
    rows=[]
    for row,(label,pitch) in enumerate((('OVERHEAD',68.),('OBLIQUE',35.),('GRAZING',10.))):
        images=[];depths=None
        for col,(field,seconds,title) in enumerate(((None,0.,'ANALYTIC'),(fields[0.],0.,'SPECTRAL 0 S'),(fields[17.5],17.5,'SPECTRAL 17.5 S'))):
            scene=scene_capture(runner,pitch,field,seconds)
            textures=scene['textures']
            geo=[[pixel[3] for pixel in line] for line in textures['colortex7']]
            if depths is None:depths=geo
            else:require(geo==depths,'Wave model changed the actual capture depth')
            uniforms={n:(n,k,v) for n,k,v in scene['uniforms']}
            projection=uniforms['gbufferProjection'][2];up=uniforms['upPosition'][2]
            viewer=unit((-.06/projection[0],.14/projection[5],1.))
            cosine=sum(x*y for x,y in zip(viewer,up))
            sunlight=tuple(2*cosine*u-v for u,v in zip(up,viewer))
            uniforms.update(shadowLightPosition=('shadowLightPosition','f3',sunlight),sunPosition=('sunPosition','f3',sunlight))
            opts=dict(WATER_OPTICS=1,IRIS_FEATURE_PER_BUFFER_BLENDING=True,WATER_CELESTIAL_GLINT=1,WATER_SCREEN_REFLECTIONS=0,SHADOWS_ENABLED=False,FOG_ENABLED=0)
            if field is not None:opts.update(WATER_FFT=1,IRIS_FEATURE_COMPUTE_SHADERS=True,IRIS_FEATURE_CUSTOM_IMAGES=True)
            inputs=[(n,img,FORMATS[n]) for n,img in textures.items()]
            raw=runner.render('Spectral water optics',runner.pair('composite1',opts),WIDTH,HEIGHT,inputs,list(uniforms.values()),storage='RGBA16F',optional=list(textures)+list(uniforms))
            out=runner.render('Spectral water display',runner.pair('final'),WIDTH,HEIGHT,[('colortex0',raw,'RGBA16F')])
            pixels=display_rows(out);images.append(pixels)
            y0=20+row*(HEIGHT+18);x0=col*WIDTH
            draw_text(sheet,x0+4,y0+5,label+' / '+title)
            for dy,line in enumerate(pixels):sheet[y0+18+dy][x0:x0+WIDTH]=line
        differences=[sum(max(abs(a-b) for a,b in zip(p,q))>2 for line,other in zip(images[i],images[j]) for p,q in zip(line,other)) for i,j in ((0,1),(1,2))]
        require(min(differences)>10,'Wave model or elapsed time made no visible difference at '+label)
        rows.append(dict(pitch=pitch,water_pixels=scene['water_pixels'],changed_display_pixels_over_two=differences))
    png(path,sheet)
    return rows
