"""M16 synthetic native-driver fixtures; no Minecraft water rasterization."""
import math

from compile_glsl import SHADERS, expand
from validate_water_waves import f32, matrix_vector, unit
from validate_water_depth import depth_color, depth_drop, inverse_matrix, perspective_matrix, reconstruct_view


def matrix_uniform(matrix):
    return [matrix[row][col] for col in range(4) for row in range(4)]


def rotation_inverse(pitch, translation=(0,0,0)):
    c,s=math.cos(pitch),math.sin(pitch)
    rows=((1,0,0,translation[0]),(0,c,-s,translation[1]),(0,s,c,translation[2]),(0,0,0,1))
    return tuple(tuple(f32(x) for x in row) for row in rows)


def depth_tests(runner,compare):
    common='''
uniform sampler2D testScene;
uniform sampler2D testSurface;
uniform vec3 testNormal;
layout(location=0) out vec4 color;
'''
    helper='#version 330 compatibility\n'+expand(SHADERS/'lib/water_depth.glsl')+common+'''
uniform float testLighting;
void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec4 source=texelFetch(testScene,pixel,0);
    vec3 surface=texelFetch(testSurface,pixel,0).xyz;
    color=vec4(applyWaterDepthTint(source.rgb,surface,testNormal,testLighting),source.a);
}
'''
    integrated='#version 330 compatibility\n'+expand(SHADERS/'lib/water.glsl')+common+'''
uniform vec2 testLightmap;
uniform int testMaterial;
uniform ivec4 testBlend;
void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec4 source=texelFetch(testScene,pixel,0);
    vec3 surface=texelFetch(testSurface,pixel,0).xyz;
    color=vec4(applyWaterStyle(source.rgb,surface,testNormal,testLightmap,testMaterial,testBlend,vec3(0.2)),source.a);
}
'''
    width,height=7,3
    scene=[[((1+x%3)*.125,(1+y)*.25,(1+(x+y)%4)*.125,(1+(x+2*y)%7)/8.0)
            for x in range(width)] for y in range(height)]
    scene[0][0]=(0,0,0,.25)
    scene[0][2]=(-.125,.25,.5,.5)
    scene[0][3]=(0,0,0,.75)
    scene[1][1]=(60000,60000,60000,.5)
    scene[-1][-1]=(8,4,2,.875)
    values=(.25,.5,.55,.75,.95,.9999,1.0,math.nan,math.inf,-.1)
    background=[[(f32(values[(x+3*y)%len(values)]),0,0,1) for x in range(width)] for y in range(height)]
    cases=[dict(label='default'),dict(label='off',enabled=0),dict(label='zero-strength',strength=0.0),
           dict(label='no-light',lighting=0.0),dict(label='partial-light',lighting=.25),
           dict(label='side-face',side=True),dict(label='sloped-face',sloped=True),dict(label='zero-normal',normal=(0,0,0)),
           dict(label='invalid-normal',normal=(math.nan,0,0)),dict(label='upward-camera',pitch=.8),
           dict(label='translation',translation=(1000,-2000,3000)),dict(label='near-small',near=.05),
           dict(label='near-large',near=4.0),dict(label='scale4',scale=4.0),dict(label='scale16',scale=16.0),
           dict(label='scale32',scale=32.0),dict(label='strength15',strength=.15),
           dict(label='strength25',strength=.25),dict(label='shallow-camera',pitch=-.25),
           dict(label='singular-inverse',singular=True),dict(label='invalid-inverse',invalid=True),
           dict(label='small-depth',small=True),dict(label='zero-projection',projection_zero=True),
           dict(label='invalid-projection',projection_invalid=True),dict(label='negative-ray-gap',far_surface=True),
           dict(label='invalid-lighting',lighting=math.nan),dict(label='invalid-up',up=(math.nan,0,0)),
           dict(label='zero-up',up=(0,0,0))]
    # Full source integration must retain the effect when old tint/reflection are zero.
    cases += [dict(label='full-style',integrated=True),dict(label='full-torch',integrated=True,block=1.0),
              dict(label='full-cave',integrated=True,sky=0.0),dict(label='full-nonwater',integrated=True,material=0),
              dict(label='full-underwater',integrated=True,eye=1),dict(label='full-vision',integrated=True,vision=1.0),
              dict(label='full-no-skylight',integrated=True,skylight=0),
              dict(label='full-unsupported-blend',integrated=True,blend=(1,1,1,1)),
              dict(label='full-debug',integrated=True,debug=5),dict(label='full-legacy',integrated=True,mode=0),
              dict(label='full-off',integrated=True,enabled=0),dict(label='full-zero',integrated=True,strength=0.0)]
    comparisons=[]
    bypass_pixels=0
    for case in cases:
        enabled=case.get('enabled',1); strength=case.get('strength',.35); scale=case.get('scale',8.0)
        mode=case.get('mode',1); debug=case.get('debug',0)
        projection=perspective_matrix(70,width/height,case.get('near',1.0),192.0)
        inv_projection=tuple(tuple(f32(x) for x in row) for row in inverse_matrix(projection))
        surface=[[tuple(f32(x) for x in reconstruct_view(((x+.5)/width,(y+.5)/height),.5,inv_projection))+(1.0,)
                  for x in range(width)] for y in range(height)]
        if case.get('far_surface'):
            surface=[[tuple(f32(c*1000) for c in p[:3])+(1.0,) for p in row] for row in surface]
        if case.get('projection_zero'):
            inv_projection=((0,0,0,0),)*4
        if case.get('projection_invalid'):
            inv_projection=((math.nan,0,0,0),)+inv_projection[1:]
        inverse=rotation_inverse(case.get('pitch',-1.1),case.get('translation',(0,0,0)))
        if case.get('singular'):
            inverse=((0,0,0,0),)*3+((0,0,0,1),)
        if case.get('invalid'):
            inverse=((math.nan,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))
        up=tuple(f32(x) for x in (unit(tuple(inverse[1][i] for i in range(3))) or (0,1,0)))
        normal=case.get('normal',(1,0,0) if case.get('side') else up)
        if case.get('sloped'):
            normal=tuple(f32(x) for x in (math.sqrt(1-.7*.7),.7*up[1],.7*up[2]))
        up=case.get('up',up)
        n,u=unit(normal),unit(up)
        face_dot=sum(a*b for a,b in zip(n,u)) if n and u else 0.0
        face_t=min(1,max(0,(face_dot-.5)/.45))
        eligible=face_t*face_t*(3-2*face_t)
        depth=[[(.95,0,0,1)]] if case.get('small') else background
        active_scene=[list(row) for row in scene]
        if case.get('small'):
            active_scene[0][0]=(.25,.5,.75,.25)
        dw,dh=len(depth[0]),len(depth)
        lighting=case.get('lighting',1.0)
        uniforms=[('gbufferProjectionInverse','m4',matrix_uniform(inv_projection)),
                  ('gbufferModelViewInverse','m4',matrix_uniform(inverse)),('upPosition','f3',up),
                  ('testNormal','f3',normal)]
        options=dict(WATER_DEPTH_TINT=enabled,WATER_DEPTH_STRENGTH=strength,WATER_DEPTH_SCALE=scale,
                     SCENE_COLOR_MODE=mode,DEBUG_VIEW=debug)
        wrapper=helper
        forced_bypass=False
        if case.get('integrated'):
            wrapper=integrated
            options.update(SKY_STYLE=0,WATER_TINT_STRENGTH=0.0,WATER_REFLECTION_STRENGTH=0.0)
            sky=case.get('sky',1.0);block=case.get('block',0.0)
            uniforms += [('hasSkylight','i1',(case.get('skylight',1),)),('hasCeiling','i1',(0,)),
                         ('isEyeInWater','i1',(case.get('eye',0),)),('blindness','f1',(case.get('vision',0.0),)),
                         ('darknessFactor','f1',(0.0,)),('rainStrength','f1',(0.0,)),
                         ('testLightmap','f2',(.5/16+block*15/16,.5/16+sky*15/16)),
                         ('testMaterial','i1',(case.get('material',1),)),
                         ('testBlend','i4',case.get('blend',(770,771,1,0)))]
            forced_bypass=bool(case.get('eye') or case.get('vision') or case.get('skylight',1)==0
                               or case.get('material',1)!=1 or case.get('blend') or not mode or debug)
            lighting=0.0 if forced_bypass else sky*(1-block)
        else:
            uniforms.append(('testLighting','f1',(lighting,)))
        textures=[('testScene',active_scene,'RGBA32F'),('testSurface',surface,'RGBA32F'),('depthtex2',depth,'RGBA32F')]
        optional=[]
        if not enabled or strength==0 or not mode or debug:
            optional=[name for name,_,_ in uniforms]+['testSurface','depthtex2']
        label='water-depth-'+case['label']
        actual=runner.render(label,runner.pair('composite',options,wrapper),width,height,textures,uniforms,optional=optional)
        expected=[]
        exact=[]
        for y in range(height):
            row=[]
            for x in range(width):
                drop=0.0
                if x<dw and y<dh:
                    drop=depth_drop(((x+.5)/dw,(y+.5)/dh),.5,depth[y][x][0],surface[y][x][:3],inv_projection,inverse)
                input_rgb=active_scene[y][x][:3]
                rgb=depth_color(input_rgb,drop,strength=strength,scale=scale,eligibility=eligible,
                                environment=lighting,enabled=bool(enabled and mode and not debug))
                row.append(tuple(rgb)+(active_scene[y][x][3],))
                if rgb is input_rgb or not enabled or not mode or debug or strength==0 or lighting==0 or eligible==0 or drop<=0:
                    exact.append((x,y))
            expected.append(row)
        comparisons.append(compare(actual,expected,label,absolute=3e-6,relative=3e-5))
        for x,y in exact:
            if actual[y][x]!=active_scene[y][x]:
                raise RuntimeError(label+': bypass pixel {},{} changed'.format(x,y))
        if any(actual[y][x][3]!=active_scene[y][x][3] for y in range(height) for x in range(width)):
            raise RuntimeError(label+': wrapper alpha changed')
        bypass_pixels+=len(exact)
    return dict(cases=len(cases),color_samples=len(cases)*width*height,exact_bypass_pixels=bypass_pixels,
                comparisons=comparisons,input='Actual depth helper and full water-style wrappers, true perspective synthetic positions; no Minecraft draws or blending')
