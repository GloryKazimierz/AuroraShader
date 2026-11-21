"""M19 angular sun/moon glow references and isolated sky-background contracts."""
import math
import re
import struct
import subprocess
from pathlib import Path
from itertools import product
from validate_water_snapshot import restore_water_snapshot_source
from validate_water_filtered_waves import FILTER_OPTIONS
from validate_water_screen_reflection import REFLECTION_OPTIONS

M18_BASELINE = '60871f45b7e84e331bacaf541874c7ae4df86090'
GLOW_OPTIONS = {'CELESTIAL_GLOW','SUN_GLOW_STRENGTH','MOON_GLOW_STRENGTH'}
SUN_TINT = (1.0,.62,.28)
MOON_TINT = (.24,.38,1.0)
MAX_ADDED = tuple(s+.5*m for s,m in zip(SUN_TINT,MOON_TINT))
GLOW_LABELS = {'option.CELESTIAL_GLOW','value.CELESTIAL_GLOW.0','value.CELESTIAL_GLOW.1',
               'option.CELESTIAL_GLOW.comment','option.SUN_GLOW_STRENGTH','option.SUN_GLOW_STRENGTH.comment',
               'option.MOON_GLOW_STRENGTH','option.MOON_GLOW_STRENGTH.comment'}


def finite(values):
    return all(math.isfinite(x) for x in values)


def clamp(value,lo=0.0,hi=1.0):
    return value if math.isnan(value) else min(hi,max(lo,value))


def smooth(a,b,value):
    t=clamp((value-a)/(b-a))
    return t*t*(3-2*t)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def unit(vector):
    if not finite(vector):
        return None
    scale=max(map(abs,vector))
    if scale<=1e-6:
        return None
    scaled=tuple(x/scale for x in vector)
    length=math.sqrt(dot(scaled,scaled))
    return tuple(x/length for x in scaled)


def f32(value):
    try:
        return struct.unpack('f',struct.pack('f',value))[0]
    except OverflowError:
        return math.copysign(math.inf,value)


def angular_lobe(alignment):
    if not math.isfinite(alignment):
        return 0.0
    separation=1-clamp(alignment,-1,1)
    return .75*math.exp(-separation/.012)+.25*math.exp(-separation/.08)


def moon_phase_brightness(phase):
    if not isinstance(phase,int) or phase<0 or phase>7:
        return 0.0
    # Independent cosine definition; special endpoints preserve exact new/full
    # values while folding makes waxing and waning pairs bit-identical.
    folded=min(phase,8-phase)
    if folded==0:
        return 1.0
    if folded==4:
        return 0.0
    return .5*(1+math.cos(folded*math.pi/4))


def body_lobe(ray_unit,up_unit,body):
    direction=unit(body)
    if direction is None:
        return 0.0
    return smooth(-.08,.04,dot(direction,up_unit))*angular_lobe(dot(ray_unit,direction))


def celestial_glow(ray,scene,sun=(0,1,0),moon=(0,-1,0),up=(0,1,0),phase=0,
                   enabled=True,sun_strength=.4,moon_strength=.15,mode=1,debug=0,
                   sky_style=1,sky_blend=1,rain=0,skylight=True,ceiling=False,eye=0,
                   blindness=0,darkness=0,fp32_result=False):
    if not enabled or not mode or not sky_style or debug:
        return scene
    ss,ms=clamp(sun_strength),clamp(moon_strength,0,.5)
    if ss<=0 and ms<=0:
        return scene
    if not finite((ss,ms,sky_blend,rain,blindness,darkness)) or not finite(scene) or min(scene)<0:
        return scene
    r,u=unit(ray),unit(up)
    if r is None or u is None:
        return scene
    environment=0.0 if not skylight or ceiling or eye!=0 else 1-clamp(max(blindness,darkness))
    weight=clamp(sky_blend)*environment*(1-clamp(rain))**2*smooth(-.025,.04,dot(r,u))
    if not math.isfinite(weight) or weight<=0:
        return scene
    solar=ss*body_lobe(r,u,sun)
    lunar=ms*moon_phase_brightness(phase)*body_lobe(r,u,moon)
    added=tuple(weight*(solar*s+lunar*m) for s,m in zip(SUN_TINT,MOON_TINT))
    if not finite(added) or min(added)<0 or max(added)<=0:
        return scene
    result=tuple(c+a for c,a in zip(scene,added))
    if fp32_result:
        # Model only the final storage-independent float32 sum for discontinuous
        # overflow guards; angular/weight math remains an independent reference.
        result=tuple(map(f32,result))
    if not finite(result) or min(result)<0 or max(result)>65504:
        return scene
    return result


def close(a,b,tolerance=1e-10):
    return all(abs(x-y)<=tolerance for x,y in zip(a,b))

def validate_glow_math():
    values=[angular_lobe(math.cos(index*math.pi/2048)) for index in range(2049)]
    assert values[0]==1 and values[-1]>0
    assert all(0<=value<=1 for value in values)
    assert all(right<=left for left,right in zip(values,values[1:]))
    assert angular_lobe(2)==1 and angular_lobe(-2)==angular_lobe(-1)
    for invalid in (math.nan,math.inf,-math.inf):
        assert angular_lobe(invalid)==0
    phases=[moon_phase_brightness(phase) for phase in range(8)]
    assert phases[0]==1 and phases[4]==0 and phases[2]==phases[6]==.5
    assert phases[1]==phases[7] and phases[3]==phases[5]
    assert phases[:5]==sorted(phases[:5],reverse=True)
    for invalid in (-2147483648,-1,8,2147483647):
        assert moon_phase_brightness(invalid)==0
    scene=(.05,.1,.25)
    rays=[]
    for angle,height in product(range(12),(-.025,0,.04,.5,1)):
        radius=math.sqrt(max(0,1-height*height))
        azimuth=angle*math.pi/6
        rays.append((radius*math.cos(azimuth),height,radius*math.sin(azimuth)))
    cases=0
    for ray,sun,phase,rain,strengths in product(rays,((0,1,0),(0,-1,0),(1,.01,0),(-1,.4,0)),
                                               range(8),(0,.5,1),((0,0),(.4,.15),(1,.5))):
        result=celestial_glow(ray,scene,sun=sun,moon=(0,1,0),phase=phase,rain=rain,
                              sun_strength=strengths[0],moon_strength=strengths[1])
        assert finite(result)
        assert all(0<=r-s<=bound+1e-12 for r,s,bound in zip(result,scene,MAX_ADDED))
        if rain==1 or strengths==(0,0) or unit(ray)[1]<=-.025:
            assert result is scene
        cases+=1
    zero=(0,0,0)
    peak=celestial_glow((0,1,0),zero,sun=(0,1,0),moon=(0,1,0),sun_strength=1,moon_strength=.5)
    assert close(peak,MAX_ADDED) and max(MAX_ADDED)<1.5
    for phase in range(8):
        moon=celestial_glow((0,1,0),zero,sun_strength=0,moon=(0,1,0),phase=phase,moon_strength=.5)
        assert close(moon,tuple(.5*moon_phase_brightness(phase)*x for x in MOON_TINT))
        if phase==4:
            assert moon is zero
    base=celestial_glow((0,1,0),zero,moon=(0,1,0))
    for rain in (0,.25,.5,.75,1):
        assert close(celestial_glow((0,1,0),zero,moon=(0,1,0),rain=rain),tuple(x*(1-rain)**2 for x in base))
    for blend in (0,.1,.5,1):
        assert close(celestial_glow((0,1,0),zero,moon=(0,1,0),sky_blend=blend),tuple(x*blend for x in base))
    for blindness,darkness in product((0,.2,.75,1),(0,.3,.8,1)):
        actual=celestial_glow((0,1,0),zero,moon=(0,1,0),blindness=blindness,darkness=darkness)
        assert close(actual,tuple(x*(1-max(blindness,darkness)) for x in base))
    # Body and ray horizon gates vary continuously; when the ray tracks its body,
    # both gates strengthen monotonically without any screen-space projection.
    horizon=[]
    for index in range(401):
        height=-.1+index*.0005
        direction=(math.sqrt(1-height*height),height,0)
        horizon.append(celestial_glow(direction,zero,sun=direction,moon_strength=0)[0])
    assert horizon[0]==0 and all(right>=left-1e-12 for left,right in zip(horizon,horizon[1:]))
    for index,value in enumerate(horizon):
        height=-.1+index*.0005
        assert abs(value-.4*smooth(-.025,.04,height)*smooth(-.08,.04,height))<1e-12
    for boundary in (-.08,-.025,.04):
        below=(math.sqrt(1-(boundary-1e-6)**2),boundary-1e-6,0)
        above=(math.sqrt(1-(boundary+1e-6)**2),boundary+1e-6,0)
        left=celestial_glow(below,zero,sun=below,moon_strength=0)
        right=celestial_glow(above,zero,sun=above,moon_strength=0)
        assert max(abs(x-y) for x,y in zip(left,right))<1e-6
    for options in ({'enabled':False},{'mode':0},{'debug':5},{'sky_style':0},{'sky_blend':0},
                    {'sun_strength':0,'moon_strength':0},{'rain':1},{'skylight':False},{'ceiling':True},
                    {'eye':1},{'eye':2},{'blindness':1},{'darkness':1}):
        assert celestial_glow((0,1,0),scene,moon=(0,1,0),**options) is scene
    assert celestial_glow((0,-1,0),scene,moon=(0,1,0)) is scene
    invalid_vectors=((0,0,0),(1e-8,0,0),(math.nan,0,0),(0,math.inf,0))
    sun_only=celestial_glow((0,1,0),scene,moon=(0,1,0),moon_strength=0)
    moon_only=celestial_glow((0,1,0),scene,moon=(0,1,0),sun_strength=0)
    for invalid in invalid_vectors:
        assert celestial_glow(invalid,scene) is scene
        assert celestial_glow((0,1,0),scene,up=invalid) is scene
        assert celestial_glow((0,1,0),scene,sun=invalid,moon=(0,1,0))==moon_only
        assert celestial_glow((0,1,0),scene,moon=invalid)==sun_only
        assert celestial_glow((0,1,0),scene,sun=invalid,moon=invalid) is scene
    for invalid in (math.nan,math.inf,-math.inf):
        for name in ('sky_blend','rain','blindness','darkness'):
            assert celestial_glow((0,1,0),scene,**{name:invalid}) is scene
        bad=(invalid,.2,.3)
        assert celestial_glow((0,1,0),bad) is bad
    for phase in (-1,8,2147483647):
        assert celestial_glow((0,1,0),scene,moon=(0,1,0),phase=phase)==sun_only
    # Moon remains independent of sun direction/night, including non-opposite bodies.
    for sun in ((0,1,0),(0,-1,0),(1,0,0),(math.nan,0,0)):
        assert celestial_glow((0,1,0),scene,sun=sun,moon=(0,1,0),sun_strength=0)==moon_only
    assert celestial_glow((0,1,0),scene,sun=(0,-1,0),moon=(0,-1,0)) is scene
    assert close(celestial_glow((0,1e30,0),scene,sun=(0,1e30,0),moon=(0,-1e30,0),up=(0,1e30,0)),
                 celestial_glow((0,1,0),scene))
    for invalid_scene in ((-.1,.2,.3),(65504,65504,65504),(1e30,2e30,3e30)):
        assert celestial_glow((0,1,0),invalid_scene,moon=(0,1,0)) is invalid_scene
    near_half=(65503.5,10,20)
    near=celestial_glow((0,1,0),near_half,moon_strength=0,fp32_result=True)
    assert near is not near_half and max(near)<=65504 and finite(near)
    # At the float32 limit, sub-ULP red additions may round away while blue remains.
    edge=(65504,0,0)
    exact_model=celestial_glow((0,1,0),edge,moon_strength=0,sun_strength=.0001)
    rounded_model=celestial_glow((0,1,0),edge,moon_strength=0,sun_strength=.0001,fp32_result=True)
    assert exact_model is edge and rounded_model[0]==65504 and rounded_model[1]>0
    rotations=0
    ray,sun,moon,up=(.4,.8,-.2),(-.1,.7,.4),(.5,.6,-.1),(0,1,0)
    expected=celestial_glow(ray,scene,sun,moon,up,2)
    for yaw,pitch,roll in product((-2,-.5,0,1.7),(-1,0,.8),(-.4,.3)):
        cy,sy,cp,sp,cr,sr=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch),math.cos(roll),math.sin(roll)
        yaw_pitch=((cy,0,sy),(sp*sy,cp,-sp*cy),(-cp*sy,sp,cp*cy))
        def rotate(vector):
            x,y,z=(dot(row,vector) for row in yaw_pitch)
            return cr*x-sr*y,sr*x+cr*y,z
        actual=celestial_glow(rotate(ray),scene,rotate(sun),rotate(moon),rotate(up),2)
        assert close(actual,expected,1e-12)
        rotations+=1
    print('PASS: M19 2049 monotone angular samples, exact/symmetric moon phases and {} bounded source-color cases'.format(cases))
    print('PASS: M19 independent celestial failures, continuous horizon/weather masks, dimension/vision/off/debug/legacy bypasses')
    print('PASS: M19 {} common-frame rotations, finite/negative/HDR fallbacks and float32 boundary behavior'.format(rotations))

GLOW_CALL = '''            // M19 changes only background light; native sun/moon texture draws stay separate.
            color.rgb = applyCelestialGlow(pos, color.rgb);
'''


def restore_celestial_glow_plumbing(source):
    """Remove only the exact sky call before older expanded-main comparisons."""
    assert source.count(GLOW_CALL)<=1
    return source.replace(GLOW_CALL,'',1)


def restore_celestial_glow_source(relative,source):
    """Remove only the M19 sky call/include, option placements and eight labels."""
    relative=relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative=relative[len('shaders/'):]
    source=restore_water_snapshot_source(relative,source)
    if relative=='lib/geometry/sky_fragment.glsl':
        include='#include "/lib/celestial_glow.glsl"\n'
        assert source.count(include)==source.count(GLOW_CALL)==1
        source=source.replace(include,'',1).replace(GLOW_CALL,'',1)
    if relative=='shaders.properties':
        placements=(('sliders = SUN_GLOW_STRENGTH MOON_GLOW_STRENGTH ','sliders = '),
                    ('DIRECT_LIGHT CELESTIAL_GLOW SUN_GLOW_STRENGTH MOON_GLOW_STRENGTH\n','DIRECT_LIGHT\n'))
        for current,old in placements:
            assert source.count(current)==1
            source=source.replace(current,old,1)
    if relative in ('lang/en_us.lang','lang/zh_cn.lang'):
        marker='\noption.CELESTIAL_GLOW='
        assert source.count(marker)==1
        prefix,tail=source.split(marker,1)
        lines=('option.CELESTIAL_GLOW='+tail).splitlines()
        assert all('=' in line for line in lines)
        keys=[line.split('=',1)[0] for line in lines]
        assert len(keys)==len(GLOW_LABELS) and set(keys)==GLOW_LABELS
        source=prefix
    return source


def validate_celestial_glow(root,expand,preprocess,compact,function_body):
    from validate_settings_profiles import (option_definitions,parse_properties,load_profiles,menu_options,
                                            parse_language,matching_profiles,PROFILE_KEYS)
    shaders=Path(root)/'shaders'
    def read(relative):
        return (shaders/relative).read_text(encoding='utf-8')
    def body(source,name):
        return compact(function_body(source,name))
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',M18_BASELINE,'shaders']).decode().splitlines()
    for path in old_files:
        relative=path[len('shaders/'):]
        previous=subprocess.check_output(['git','-C',str(root),'show',M18_BASELINE+':'+path]).decode('utf-8').replace('\r\n','\n')
        assert restore_celestial_glow_source(relative,read(relative))==previous,relative
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files-set(old_files)=={'shaders/lib/celestial_glow.glsl','shaders/lib/celestial_glow_settings.glsl','shaders/lib/water_scene_snapshot.glsl','shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'}
    assert len(list(shaders.glob('*.vsh')))==len(list(shaders.glob('*.fsh')))==24
    helper=read('lib/celestial_glow.glsl')
    code=compact(helper)
    # Bind only integration contracts. Independent angle/phase/color oracles and
    # native-driver fixtures verify the math rather than mirroring every source line.
    assert 'uniformvec3moonPosition;' in code and 'uniformintmoonPhase;' in code
    assert 'glowBodyLobe(rayUnit,upUnit,sunPosition)' in code
    assert 'glowBodyLobe(rayUnit,upUnit,moonPosition)' in code
    assert 'glowMoonPhaseBrightness(moonPhase)' in code
    for forbidden in ('shadowLightPosition','gbufferModelView','cameraPosition','frameTimeCounter',
                      'texture(','texelFetch(','sampler','colortex','depthtex','gl_FragCoord','gl_FragDepth'):
        assert forbidden not in code,forbidden
    geometry=read('lib/geometry/sky_fragment.glsl')
    assert geometry.count(GLOW_CALL)==1
    main=body(geometry,'main')
    assert main.count('applyCelestialGlow(')==1
    assert 'if(renderStage==MC_RENDER_STAGE_SKY){color.rgb=applyCelestialGlow(pos,color.rgb);color.rgb=applyNightAurora(pos,color.rgb);}' in main
    assert main.index('applyAuroraSky(')<main.index('applyCelestialGlow(')<main.index('applyNightAurora(')
    for path in shaders.glob('*.fsh'):
        selected=preprocess(expand(path),0,False)
        assert ('applyCelestialGlow(' in selected)==(path.stem=='gbuffers_skybasic'),path.name
        uniforms=re.findall(r'^uniform\s+\w+\s+(\w+)\s*(?:=[^;]+)?;',selected,re.M)
        assert len(uniforms)==len(set(uniforms)),path.name
    for path in shaders.glob('*.vsh'):
        assert 'applyCelestialGlow(' not in preprocess(expand(path),0,False),path.name
    for mode,enabled,style,debug in product((0,1),(0,1),(0,1),range(7)):
        selected=preprocess(expand(shaders/'gbuffers_skybasic.fsh'),debug,False,
                            overrides={'SCENE_COLOR_MODE':mode,'CELESTIAL_GLOW':enabled,'SKY_STYLE':style})
        if not mode or not enabled or not style or debug:
            assert body(selected,'applyCelestialGlow')=='returnscene;'
    options={key:value for key,value in option_definitions(root).items() if key not in (FILTER_OPTIONS | REFLECTION_OPTIONS)}
    properties=parse_properties(restore_water_snapshot_source('shaders.properties',read('shaders.properties')))
    controls,screens=menu_options(properties,options)
    assert len(options)==len(controls)==57 and len(screens)==12
    for name,default,values in (('CELESTIAL_GLOW','1',('0','1')),
                                ('SUN_GLOW_STRENGTH','0.4',('0.0','0.2','0.4','0.6','1.0')),
                                ('MOON_GLOW_STRENGTH','0.15',('0.0','0.05','0.15','0.3','0.5'))):
        assert options[name]==dict(kind='number',default=default,values=values)
    profiles=load_profiles(root)
    controlled=PROFILE_KEYS|{'FOLIAGE_WIND'}
    assert all(set(profile)==controlled for profile in profiles.values())
    assert len(set(options)-controlled)==50
    defaults={key:option['default'] for key,option in options.items()}
    for name,profile in profiles.items():
        current=dict(defaults,**profile)
        for glow,sun_strength,moon_strength in product(('0','1'),('0.0','1.0'),('0.0','0.5')):
            current.update(CELESTIAL_GLOW=glow,SUN_GLOW_STRENGTH=sun_strength,MOON_GLOW_STRENGTH=moon_strength)
            assert matching_profiles(profiles,current)==(name,)
    en,zh=(parse_language(restore_water_snapshot_source('lang/'+language,read('lang/'+language))) for language in ('en_us.lang','zh_cn.lang'))
    assert len(en)==len(zh)==179 and set(en)==set(zh)
    assert GLOW_LABELS<=set(en)
    assert all(re.search(r'[\u3400-\u9fff]',zh[key]) for key in GLOW_LABELS)
    print('PASS: M19 {} prior shader/property/language files pinned; only the SKY background gains celestial glow'.format(len(old_files)))
    print('PASS: M19 independent sun/moon vectors, original discs/stars/void/alpha/fog/reflections/lighting and existing 24 passes retained')
    print('PASS: M19 57 controls once, unchanged seven-control profiles retain 50 other settings, and 179 bilingual keys')
    validate_glow_math()
    print('LIMIT: angular background glow only; no physical scattering, Minecraft appearance or performance measurement')