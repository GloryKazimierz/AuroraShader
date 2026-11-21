"""W3 synthetic native screen-ray diagnostics, not Minecraft/Iris rendering."""
import math

from compile_glsl import SHADERS, expand
from validate_gpu import require, half
from validate_gpu_depth import matrix_uniform
from validate_water_waves import f32

TARGETS=((1,1,'RGBA32F'),(2,2,'RGBA32F'))


def screen_reflection_tests(runner,compare):
    from validate_water_screen_reflection import trace_scene, trace_fixtures, reconstruct, unit
    helper='#version 330 compatibility\n'+expand(SHADERS/'lib/water_screen_reflection.glsl')+'''
uniform sampler2D testOrigins;
uniform sampler2D testDirections;
layout(location=0) out vec4 diagnostic;
layout(location=1) out vec4 location;
layout(location=2) out vec4 payload;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec3 origin=texelFetch(testOrigins,p,0).xyz;
    vec3 direction=texelFetch(testDirections,p,0).xyz;
    ivec2 hitPixel;
    vec3 hitView,hitRGB;
    float hitDistance,hitConfidence;
    int stepsTaken;
    bool hit=traceWaterScene(origin,direction,hitPixel,hitView,hitRGB,
                            hitDistance,hitConfidence,stepsTaken);
    diagnostic=vec4(vec2(hitPixel),hitDistance,hitConfidence);
    location=vec4(hitView,hit?1.0:0.0);
    payload=vec4(hitRGB,float(stepsTaken));
}
'''
    comparisons=[]; cases=[];queries_checked=0;valid_hits=0;misses=0
    for fixture in trace_fixtures():
        name=fixture['name']
        # Match storage and matrix upload before running the independent CPU model.
        projection=tuple(tuple(map(f32,row)) for row in fixture['projection'])
        inverse=tuple(tuple(map(f32,row)) for row in fixture['inverse_projection'])
        color=[[tuple(half(v) for v in pixel) for pixel in row] for row in fixture['color']]
        depth=[[f32(v) for v in row] for row in fixture['depth']]
        opaque=[[f32(v) for v in row] for row in fixture['opaque_depth']]
        queries=fixture['queries']
        require(bool(queries),name+': empty fixture')
        width,height=len(queries),1
        require(width<=2048,name+': too many query pixels')
        origins=[[tuple(map(f32,q['origin']))+(1,) for q in queries]]
        directions=[[tuple(map(f32,q['direction']))+(1,) for q in queries]]
        textures=[('colortex5',color,'RGBA16F'),
                  ('colortex6',[[(v,0,0,1) for v in row] for row in depth],'R32F'),
                  ('depthtex1',[[(v,0,0,1) for v in row] for row in opaque],'R32F'),
                  ('testOrigins',origins,'RGBA32F'),('testDirections',directions,'RGBA32F')]
        uniforms=[('gbufferProjection','m4',matrix_uniform(projection)),
                  ('gbufferProjectionInverse','m4',matrix_uniform(inverse))]
        for budget in fixture.get('budgets',(64,128)):
            expected=[trace_scene(o[:3],d[:3],projection,inverse,color,depth,opaque,steps=budget)
                      for o,d in zip(origins[0],directions[0])]
            outputs=[
                [[tuple(e['pixel'])+(e['distance'],e['confidence']) for e in expected]],
                [[tuple(e['position'])+(float(e['valid']),) for e in expected]],
                [[tuple(e['radiance'])+(float(e['steps']),) for e in expected]],
            ]
            label='screen-reflection-{}-{}'.format(name,budget)
            pair=runner.pair('composite',dict(WATER_SCREEN_REFLECTIONS=1,
                                             WATER_REFLECTION_STEPS=budget),helper)
            actual=[]
            for slot,want in enumerate(outputs):
                image=runner.render(label+'-'+str(slot),pair,width,height,textures,uniforms,
                                    extra_targets=TARGETS,read_target=slot)
                # Position/distance use perspective divide and ray/plane math.
                # Exact discrete hit, pixel, step, radiance and miss tests follow.
                comparisons.append(compare(image,want,label+'-'+str(slot),absolute=5e-4,relative=2e-5))
                actual.append(image[0])
            hits=0
            for index,e in enumerate(expected):
                p,v,c=(actual[slot][index] for slot in range(3))
                require(p[:2]==tuple(e['pixel']),label+': selected pixel differs')
                require(v[3]==float(e['valid']),label+': hit validity differs')
                require(c[3]==float(e['steps']),label+': visited-cell count differs')
                require(c[:3]==tuple(e['radiance']),label+': recorded radiance differs')
                require(0<=p[3]<=1,label+': confidence outside [0,1]')
                require(0<=c[3]<=budget,label+': traversal exceeded budget')
                if e['valid']:
                    hits+=1
                    require(.05-5e-4<=p[2]<=64+5e-4,label+': invalid hit distance')
                    # Reproject the actual GPU ray point independently: it must
                    # lie in the reported sample cell, not an unrelated surface.
                    h=[sum(row[j]*tuple(v[:3]+(1,))[j] for j in range(4)) for row in projection]
                    require(h[3]>0,label+': hit is behind the camera')
                    xy=((h[0]/h[3]*.5+.5)*len(depth[0]),(h[1]/h[3]*.5+.5)*len(depth))
                    require(all(p[j]-5e-3<=xy[j]<=p[j]+1+5e-3 for j in range(2)),
                            label+': hit point does not project into accepted pixel')
                    ix,iy=map(int,p[:2])
                    require(color[iy][ix][3]==1 and depth[iy][ix]==opaque[iy][ix],
                            label+': accepted unmatched snapshot')
                    require(c[:3]==color[iy][ix][:3],label+': radiance is not from accepted texel')
                    scene_point=reconstruct(((ix+.5)/len(depth[0]),(iy+.5)/len(depth)),
                                            depth[iy][ix],inverse)
                    require(scene_point is not None,label+': invalid recorded scene point')
                    # Independent hard cap: adaptive tolerance never represents
                    # an infinitely thick surface behind the sampled front.
                    front=-scene_point[2]
                    tolerance=5e-4+2e-5*abs(front)
                    require(front-tolerance<=-v[2]<=front+.5+tolerance,
                            label+': hit lies outside capped depth slab')
                    direction=unit(directions[0][index][:3])
                    ray_point=tuple(o+d*p[2] for o,d in zip(origins[0][index][:3],direction))
                    require(all(abs(a-b)<=5e-4+2e-5*abs(b) for a,b in zip(v[:3],ray_point)),
                            label+': hit is not on its actual ray')

                else:
                    require(p==(-1,-1,0,0) and v==(0,0,0,0) and c[:3]==(0,0,0),
                            label+': miss is not initialized exactly')
            queries_checked+=len(expected);valid_hits+=hits;misses+=len(expected)-hits
            cases.append(dict(scene=name,budget=budget,queries=len(expected),hits=hits))
        print('PASS: W3 native scene '+name,flush=True)
    require(valid_hits>0 and misses>0,'Ray fixtures need meaningful hits and misses')
    return dict(scene_configurations=len(cases),queries=queries_checked,hits=valid_hits,misses=misses,
                cases=cases,comparisons=comparisons,water_style=water_style_integration_tests(runner,compare),
                scope='Actual GLSL ray helper, frozen synthetic RGBA16F/R32F scene inputs and MRT diagnostic readback. CPU fixture geometry has independent analytic ray-plane truth; no Iris transforms/world.')


def water_style_integration_tests(runner,compare):
    """Exercise the real water-style helper's scene/sky selection and RGB mix."""
    from validate_water_screen_reflection import perspective,inverse,project,trace_scene
    from validate_water_waves import unit
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/water.glsl')+'''
uniform sampler2D testScene;
uniform sampler2D testSurfaces;
uniform vec3 testNormal;
uniform vec2 testLightmap;
uniform int testMaterial;
uniform ivec4 testBlend;
layout(location=0) out vec4 color;
void main() {
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec4 scene=texelFetch(testScene,p,0);
    vec3 surface=texelFetch(testSurfaces,p,0).xyz;
    color=vec4(applyWaterStyle(scene.rgb,surface,testNormal,testLightmap,
               testMaterial,testBlend,vec3(.2,.3,.4),vec2(0),vec2(0)),scene.a);
}
'''
    sw,sh=128,96
    projection=tuple(tuple(map(f32,row)) for row in perspective(70,sw/sh,1,128))
    inv=tuple(tuple(map(f32,row)) for row in inverse(projection))
    z=f32(project((0,0,-8),projection)[1])
    depth=[[z]*sw for _ in range(sh)]
    colors=[[((.75,.125,.0625,1) if x//16%2 else (.0625,.5,.75,1))
             for x in range(sw)] for _ in range(sh)]
    empty=[[(0,0,0,0)]*sw for _ in range(sh)]
    clear=[[1.]*sw for _ in range(sh)]
    surfaces=[[(x*.125-.5,-1.0-(x%3)*.125,-3.5-(x%2)*.25,1) for x in range(8)]]
    inputs=[[(.0625*(x+1),.25,.5,(x+1)/8) for x in range(8)]]
    fixtures=[
        dict(name='local-day'),dict(name='cave',sky=0),
        dict(name='sky-style-off',style=0),dict(name='sky-blend-zero',blend=0.0),
        dict(name='scene-miss',miss=True),dict(name='nonwater',material=0,bypass=True),
        dict(name='underwater',eye=1,bypass=True),dict(name='debug',debug=5,bypass=True),
        dict(name='legacy',mode=0,bypass=True),dict(name='water-off',water=0,bypass=True),
    ]
    comparisons=[];recorded=[];changed_total=0
    for case in fixtures:
        name=case['name']
        options=dict(FOG_ENABLED=0,WATER_DEPTH_TINT=0,WATER_TINT_STRENGTH=0.0,
                     WATER_WAVES=0,WATER_REFLECTION_STRENGTH=1.0,WATER_REFLECTION_STEPS=64,
                     SKY_STYLE=case.get('style',1),SKY_BLEND=case.get('blend',1.0),
                     SCENE_COLOR_MODE=case.get('mode',1),DEBUG_VIEW=case.get('debug',0),
                     WATER_STYLE=case.get('water',1))
        image=empty if case.get('miss') else colors
        values=clear if case.get('miss') else depth
        textures=[('colortex5',image,'RGBA16F'),
                  ('colortex6',[[(v,0,0,1) for v in row] for row in values],'R32F'),
                  ('depthtex1',[[(v,0,0,1) for v in row] for row in values],'R32F'),
                  ('testScene',inputs,'RGBA32F'),('testSurfaces',surfaces,'RGBA32F')]
        uniforms=[('gbufferProjection','m4',matrix_uniform(projection)),
                  ('gbufferProjectionInverse','m4',matrix_uniform(inv)),
                  ('testNormal','f3',(0,1,0)),('testLightmap','f2',(.5/16,.5/16+case.get('sky',1)*15/16)),
                  ('testMaterial','i1',(case.get('material',1),)),('testBlend','i4',(770,771,1,0)),
                  ('sunPosition','f3',(0,1,0)),('upPosition','f3',(0,1,0)),
                  ('hasSkylight','i1',(1,)),('hasCeiling','i1',(0,)),
                  ('isEyeInWater','i1',(case.get('eye',0),)),('blindness','f1',(0,)),
                  ('darknessFactor','f1',(0,)),('rainStrength','f1',(0,))]
        if not options['SCENE_COLOR_MODE'] or options['DEBUG_VIEW'] or not options['WATER_STYLE']:
            optional=[n for n,_,_ in textures+uniforms if n!='testScene']
            off_optional=optional
        else:
            optional=['sunPosition'] if not options['SKY_STYLE'] or options['SKY_BLEND']==0 else []
            off_optional=optional+['colortex5','colortex6','depthtex1','gbufferProjection','gbufferProjectionInverse']
            if not options['SKY_STYLE'] or options['SKY_BLEND']==0:
                off_optional+=['testSurfaces','testNormal','upPosition']
        off=runner.render('water-style-'+name+'-off',runner.pair('composite',dict(options,WATER_SCREEN_REFLECTIONS=0),source),
                          8,1,textures,uniforms,optional=off_optional)
        on=runner.render('water-style-'+name+'-on',runner.pair('composite',dict(options,WATER_SCREEN_REFLECTIONS=1),source),
                         8,1,textures,uniforms,optional=optional)
        expected=[];hits=0
        for i,point in enumerate(surfaces[0]):
            old=off[0][i]
            if case.get('bypass') or case.get('miss'):
                expected.append(old);continue
            incident=unit(point[:3])
            reflected=(incident[0],-incident[1],incident[2])
            origin=(point[0],f32(point[1]+f32(.01)),point[2])
            hit=trace_scene(origin,reflected,projection,inv,image,values,values,steps=64)
            if not hit['valid']:
                expected.append(old);continue
            hits+=1
            fresnel=.02+.98*(1-max(0,min(1,-incident[1])))**5
            local=tuple(s*(1-fresnel)+r*fresnel for s,r in zip(inputs[0][i][:3],hit['radiance']))
            rgb=tuple(a*(1-hit['confidence'])+b*hit['confidence'] for a,b in zip(old[:3],local))
            expected.append(rgb+(inputs[0][i][3],))
        comparisons.append(compare(on,[expected],'water-style-'+name,absolute=4e-5))
        require(all(a[3]==b[3] for a,b in zip(on[0],inputs[0])),name+': source alpha changed')
        changed=sum(a!=b for a,b in zip(on[0],off[0]))
        if case.get('bypass') or case.get('miss'):
            comparisons.append(compare(on,off,'water-style-'+name+'-exact-fallback'))
        else:
            require(hits>0 and changed>0,name+': scene reflection was not exercised')
        changed_total+=changed
        recorded.append(dict(case=name,hits=hits,changed_pixels=changed))
    # Also retain actual pack-fragment comparisons from W2 with new tracing off.
    from validate_gpu_water_filtered import actual_fragment_tests
    actual_fragment=actual_fragment_tests(runner,compare)
    return dict(configurations=len(fixtures),pixels_per_configuration=8,changed_pixels=changed_total,
                cases=recorded,comparisons=comparisons,actual_fragment_regression=actual_fragment,
                scope='Actual water-style helper on synthetic surface inputs: Fresnel-weighted replacement, cave/sky controls, misses, gates and exact source alpha. Actual fragment regressions use SSR off.')
