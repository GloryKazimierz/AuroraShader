"""M17 profile semantics, complete menu reachability and language contracts.

The parser intentionally accepts only option types declared by this pack; Iris
may silently ignore unknown names, which would hide a misspelled profile entry.
"""
from collections import Counter
from pathlib import Path
import re
import subprocess
from validate_foliage import FOLIAGE_OPTIONS, restore_foliage_source
from validate_celestial_glow import GLOW_OPTIONS
from validate_water_filtered_waves import FILTER_OPTIONS
from validate_water_screen_reflection import REFLECTION_OPTIONS

M16_BASELINE = '581ffa86d0800b70cdab2d486a65606b2bc9e160'
# Primary parsing/matching contract, pinned independently of pack implementation:
# https://github.com/IrisShaders/Iris/tree/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/shaderpack/option
PROFILE_KEYS = {'SHADOWS_ENABLED','SHADOW_FILTER','BLOOM_ENABLED','AURORA_ENABLED','WATER_WAVES','WATER_DEPTH_TINT'}
OLD_ROOT = 'screen = [WATER] [CLOUDS] [AURORA] [BLOOM] [FOG] [COLOR_PIPELINE] [ATMOSPHERE] DEBUG_VIEW SHADOWS_ENABLED SHADOW_BIAS SHADOW_BIAS_MODE SHADOW_BIAS_MIN SHADOW_BIAS_MAX SHADOW_FILTER SHADOW_SOFTNESS LIGHTING_STRENGTH AMBIENT_LIGHT DIRECT_LIGHT EXPOSURE SATURATION CONTRAST TEMPERATURE TINT GRAYSCALE\n'
NEW_ROOT = 'screen = <profile> <empty> [ATMOSPHERE] [SHADOWS] [WATER] [CLOUDS] [AURORA] [BLOOM] [FOG] [COLOR] [ADVANCED] <empty>\n'
OLD_ATMOSPHERE = 'screen.ATMOSPHERE = SKY_STYLE SKY_BLEND SUNSET_GLOW NIGHT_BRIGHTNESS LIGHT_PALETTE LIGHT_PALETTE_STRENGTH\n'
NEW_ATMOSPHERE = OLD_ATMOSPHERE.rstrip('\n')+' LIGHTING_STRENGTH AMBIENT_LIGHT DIRECT_LIGHT\n'
OLD_PIPELINE = 'screen.COLOR_PIPELINE = SCENE_COLOR_MODE TONE_MAPPING TONEMAP_KNEE EXPOSURE\n'
NEW_PIPELINE = 'screen.COLOR_PIPELINE = SCENE_COLOR_MODE TONE_MAPPING TONEMAP_KNEE\n'
M17_PROPERTIES = '''
# M17 quality profiles change only six controls; artistic preferences are retained.
# All profiles keep shadows enabled. Bloom-off retains its four passes and buffers.
profile.BALANCED = SHADOWS_ENABLED SHADOW_FILTER=1 BLOOM_ENABLED=1 AURORA_ENABLED=1 WATER_WAVES=1 WATER_DEPTH_TINT=1
profile.LIGHT = profile.BALANCED SHADOW_FILTER=0 BLOOM_ENABLED=0 AURORA_ENABLED=0 WATER_WAVES=0 WATER_DEPTH_TINT=0
profile.SOFT_SHADOWS = profile.BALANCED SHADOW_FILTER=2

# M17 groups existing controls without changing any shader defaults.
screen.SHADOWS = SHADOWS_ENABLED SHADOW_FILTER SHADOW_SOFTNESS SHADOW_BIAS_MODE SHADOW_BIAS SHADOW_BIAS_MIN SHADOW_BIAS_MAX
screen.SHADOWS.columns = 2
screen.COLOR = EXPOSURE SATURATION CONTRAST TEMPERATURE TINT GRAYSCALE
screen.COLOR.columns = 2
screen.ADVANCED = DEBUG_VIEW [COLOR_PIPELINE]
screen.ADVANCED.columns = 2
'''


def restore_settings_profiles_source(relative,source):
    """Undo only the reviewed M17 menu lines and appended UI/profile section."""
    relative=relative.replace('\\','/')
    if relative.startswith('shaders/'):
        relative=relative[len('shaders/'):]
    source=restore_foliage_source(relative,source)
    if relative == 'shaders.properties':
        assert source.endswith(M17_PROPERTIES)
        source=source[:-len(M17_PROPERTIES)]
        for current,old in ((NEW_ROOT,OLD_ROOT),(NEW_ATMOSPHERE,OLD_ATMOSPHERE),(NEW_PIPELINE,OLD_PIPELINE)):
            assert source.count(current) == 1
            source=source.replace(current,old,1)
    return source


def require(condition,message):
    if not condition:
        raise ValueError(message)


def parse_properties(text):
    """Strict pack-local key=value parser: reject duplicates rather than hide them."""
    result={}
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith(('#','!')):
            continue
        require('=' in line,'Missing property delimiter on line '+str(number))
        key,value=(part.strip() for part in line.split('=',1))
        require(bool(key) and bool(value),'Empty property on line '+str(number))
        require(key not in result,'Duplicate property '+key)
        result[key]=value
    return result


def option_definitions(root):
    """Extract real macro defaults/types/domains; header/program defines are not options."""
    options={}
    pattern=r'^[ \t]*(//)?#define[ \t]+(\w+)(?:[ \t]+([^/\s]+))?[ \t]*//[ \t]*(.*)$'
    for path in sorted((Path(root)/'shaders').rglob('*.glsl')):
        for disabled,name,value,comment in re.findall(pattern,path.read_text(encoding='utf-8'),re.M):
            choices=re.match(r'^\[([^]]+)\]',comment)
            if value:
                if not choices:
                    continue
                allowed=tuple(choices[1].split())
                require(value in allowed,'Default outside option domain: '+name)
                require(len(allowed)==len(set(allowed)),'Duplicate option value: '+name)
                require(not disabled,'Commented numeric option: '+name)
                spec=dict(kind='number',default=value,values=allowed)
            else:
                spec=dict(kind='boolean',default=not bool(disabled),values=(False,True))
            require(name not in options,'Duplicate option definition: '+name)
            options[name]=spec
    return options


def parse_profiles(properties,options):
    raw={key[len('profile.'):]:value for key,value in properties.items() if key.startswith('profile.')}
    require(all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) for name in raw),'Invalid profile name')
    resolved={}
    def resolve(name,stack=()):
        require(name in raw,'Unknown profile '+name)
        require(name not in stack,'Profile cycle: '+' -> '.join(stack+(name,)))
        if name in resolved:
            return resolved[name]
        result={}
        for token in raw[name].split():
            if token.startswith('profile.'):
                result.update(resolve(token[len('profile.'):],stack+(name,)))
                continue
            if '=' in token or ':' in token:
                key,value=token.split('=' if '=' in token else ':',1)
                require(key in options,'Unknown option '+key)
                if options[key]['kind']=='boolean':
                    require(value in ('true','false'),'Invalid Boolean value '+token)
                    value=value=='true'
                else:
                    require(value in options[key]['values'],'Invalid value '+token)
            else:
                key=token[1:] if token.startswith('!') else token
                require(key in options,'Unknown option '+key)
                require(options[key]['kind']=='boolean','Bare numeric option '+key)
                value=not token.startswith('!')
            result[key]=value
        require(bool(result),'Empty profile '+name)
        resolved[name]=result
        return result
    for name in raw:
        resolve(name)
    return {name:resolved[name] for name in raw}


def load_profiles(root):
    root=Path(root)
    return parse_profiles(parse_properties((root/'shaders/shaders.properties').read_text(encoding='utf-8')),option_definitions(root))


def profile_configurations(root):
    """Actual profile selections applied to every existing vertex/fragment pair."""
    root=Path(root)
    profiles=load_profiles(root)
    for name in profiles:
        for path in sorted((root/'shaders').glob('*.vsh')):
            yield path.stem,dict(profiles[name])


def matching_profiles(profiles,current):
    # Only controlled options affect Iris matching; all unrelated user choices
    # intentionally survive profile selection and do not change its displayed name.
    return tuple(name for name,profile in profiles.items()
                 if all(current.get(key)==value for key,value in profile.items()))


def menu_options(properties,options):
    screens={key:value.split() for key,value in properties.items()
             if key=='screen' or (key.startswith('screen.') and not key.endswith('.columns'))}
    require('screen' in screens,'Missing root screen')
    visited=[]
    occurrences=[]
    profile_count=[0]
    def walk(name,stack=()):
        require(name in screens,'Missing screen '+name)
        require(name not in stack,'Screen cycle '+name)
        visited.append(name)
        for token in screens[name]:
            if token == '<empty>':
                continue
            if token == '<profile>':
                profile_count[0]+=1
                continue
            if token.startswith('[') and token.endswith(']'):
                walk('screen.'+token[1:-1],stack+(name,))
            else:
                require(token in options,'Unknown menu option '+token)
                occurrences.append(token)
    walk('screen')
    require(set(visited)==set(screens),'Unreachable screens')
    require(len(visited)==len(set(visited)),'Repeated screen reference')
    require(profile_count[0]==1,'Profile selector must appear exactly once')
    counts=Counter(occurrences)
    require(set(counts)==set(options),'Missing or extra menu controls')
    require(all(count==1 for count in counts.values()),'Duplicate menu control')
    for key,value in properties.items():
        if key.startswith('screen') and key.endswith('.columns'):
            require(key[:-len('.columns')] in screens,'Columns for missing screen')
            require(value in ('1','2','3','4'),'Invalid screen column count')
    sliders=properties.get('sliders','').split()
    require(len(sliders)==len(set(sliders)),'Duplicate slider')
    for name in sliders:
        require(name in options and options[name]['kind']=='number','Invalid slider '+name)
    return tuple(occurrences),tuple(visited)


def parse_language(text):
    require('\ufffd' not in text and not text.startswith('\ufeff'),'Invalid UTF-8 language text')
    entries=parse_properties(text)
    for key,value in entries.items():
        require(value.strip().lower() not in ('todo','tbd','placeholder','translate me','???'),'Placeholder translation: '+key)
    return entries


def expect_rejected(function,*arguments):
    try:
        function(*arguments)
    except ValueError:
        return
    raise AssertionError('Invalid fixture accepted: '+repr(arguments))


def validate_settings_profiles(root,*unused):
    root=Path(root)
    shaders=root/'shaders'
    # M17 contracts remain pinned to their six-control, 51-option view.
    # Public loading/compile generators above always use the current full options.
    options={key:value for key,value in option_definitions(root).items() if key not in (FOLIAGE_OPTIONS | GLOW_OPTIONS | FILTER_OPTIONS | REFLECTION_OPTIONS)}
    properties=parse_properties(restore_foliage_source('shaders.properties',
                                (shaders/'shaders.properties').read_text(encoding='utf-8')))
    profiles=parse_profiles(properties,options)
    assert len(options)==51
    assert set(profiles)=={'BALANCED','LIGHT','SOFT_SHADOWS'}
    assert all(set(values)==PROFILE_KEYS for values in profiles.values())
    defaults={name:spec['default'] for name,spec in options.items()}
    balanced={key:defaults[key] for key in PROFILE_KEYS}
    assert profiles['BALANCED']==balanced
    light=dict(balanced,SHADOW_FILTER='0',BLOOM_ENABLED='0',AURORA_ENABLED='0',WATER_WAVES='0',WATER_DEPTH_TINT='0')
    assert profiles['LIGHT']==light
    assert profiles['SOFT_SHADOWS']==dict(balanced,SHADOW_FILTER='2')
    assert len({tuple(sorted(values.items())) for values in profiles.values()})==3
    untouched=set(options)-PROFILE_KEYS
    assert len(untouched)==45
    for name,profile in profiles.items():
        selected=dict(defaults,**profile)
        assert matching_profiles(profiles,selected)==(name,)
        # Change every unrelated artistic/advanced option to a nondefault value;
        # applying this profile and matching it still leave those values intact.
        for key in untouched:
            selected[key]=next(value for value in options[key]['values'] if value!=defaults[key])
        artistic=dict(selected)
        selected.update(profile)
        assert all(selected[key]==artistic[key] for key in untouched)
        assert matching_profiles(profiles,selected)==(name,)
    assert matching_profiles(profiles,dict(defaults,SHADOW_FILTER='2'))==('SOFT_SHADOWS',)
    assert matching_profiles(profiles,dict(defaults,SHADOW_FILTER='3'))==()
    assert matching_profiles(profiles,dict(defaults,BLOOM_ENABLED='0'))==()
    assert matching_profiles(profiles,dict(defaults,SHADOWS_ENABLED=False))==()
    # Exercise the parser independently of the pack's present simple graph.
    fixture={'profile.BASE':'SHADOWS_ENABLED SHADOW_FILTER=1',
             'profile.CHILD':'profile.BASE SHADOW_FILTER:2 SHADOWS_ENABLED=true',
             'profile.LAST':'SHADOW_FILTER=3 profile.CHILD !SHADOWS_ENABLED SHADOW_FILTER=0'}
    parsed=parse_profiles(fixture,options)
    assert parsed['LAST']=={'SHADOWS_ENABLED':False,'SHADOW_FILTER':'0'}
    assert parsed['BASE']=={'SHADOWS_ENABLED':True,'SHADOW_FILTER':'1'}
    assert parse_profiles({'profile.FALSE':'SHADOWS_ENABLED:false'},options)['FALSE']=={'SHADOWS_ENABLED':False}
    for invalid in ('TYPO=1','SHADOW_FILTER','!BLOOM_ENABLED','BLOOM_ENABLED=true','SHADOW_FILTER=9',
                    'SHADOW_FILTER=1.0','SHADOWS_ENABLED=1','SHADOWS_ENABLED=False','!TYPO','profile.MISSING',''):
        expect_rejected(parse_profiles,{'profile.BAD':invalid},options)
    expect_rejected(parse_profiles,{'profile.A':'profile.B','profile.B':'profile.A'},options)
    expect_rejected(parse_profiles,{'profile.A':'profile.A'},options)
    expect_rejected(parse_properties,'profile.A = SHADOWS_ENABLED\nprofile.A = !SHADOWS_ENABLED\n')
    controls,screens=menu_options(properties,options)
    assert len(controls)==51
    for key,value in (('screen','[MISSING]'),('screen','[ADVANCED] [ADVANCED] <profile>'),
                      ('screen.COLOR','EXPOSURE EXPOSURE'),('screen.ADVANCED','[ADVANCED]'),
                      ('screen.COLOR','EXPOSURE SATURATION TYPO'),('sliders','GRAYSCALE'),
                      ('screen','<profile> <profile>'),('screen.MISSING.columns','2')):
        bad=dict(properties); bad[key]=value
        expect_rejected(menu_options,bad,options)
    languages={name:parse_language(restore_foliage_source('lang/'+name,(shaders/'lang'/name).read_text(encoding='utf-8'))) for name in ('en_us.lang','zh_cn.lang')}
    en,zh=languages['en_us.lang'],languages['zh_cn.lang']
    assert len(en)==len(zh)==159 and set(en)==set(zh)
    assert all('option.'+key in en for key in options)
    assert all(name in en for name in screens if name!='screen')
    assert all('profile.'+name in en for name in profiles) and 'profile.comment' in en
    # Algorithm labels and proper names legitimately remain language-neutral.
    names={'3x3 PCF','5x5 PCF','Poisson PCF','Base-330','Aurora'}
    assert all(re.search(r'[\u3400-\u9fff]',value) or (key.startswith('value.') and value==en[key] and value in names)
               for key,value in zh.items()),'Translation lacks Chinese text'
    expect_rejected(parse_language,'option.X=\n')
    expect_rejected(parse_language,'option.X=One\noption.X=Two\n')
    expect_rejected(parse_language,'option.X=TODO\n')
    old_files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',M16_BASELINE,'shaders']).decode().splitlines()
    pinned=0
    for relative in old_files:
        current=(root/relative).read_text(encoding='utf-8')
        before=subprocess.check_output(['git','-C',str(root),'show',M16_BASELINE+':'+relative]).decode('utf-8').replace('\r\n','\n')
        if relative=='shaders/lang/en_us.lang':
            old_labels=parse_language(before)
            assert len(old_labels)==152
            assert all(en[key]==value for key,value in old_labels.items())
        else:
            assert restore_settings_profiles_source(relative,current)==before,relative
            pinned+=1
    current_files={str(path.relative_to(root)).replace('\\','/') for path in shaders.rglob('*') if path.is_file()}
    assert current_files-set(old_files)=={'shaders/lang/zh_cn.lang','shaders/lib/foliage.glsl','shaders/lib/foliage_settings.glsl','shaders/lib/celestial_glow.glsl','shaders/lib/celestial_glow_settings.glsl','shaders/lib/water_scene_snapshot.glsl','shaders/lib/water_filtered_waves.glsl','shaders/lib/water_surface_settings.glsl','shaders/lib/water_screen_reflection.glsl','shaders/lib/water_screen_reflection_settings.glsl'}
    assert len(list(profile_configurations(root)))==72
    print('PASS: M17 {} prior shader/property files pinned; all GLSL/defaults and rendering properties unchanged'.format(pinned))
    print('PASS: M17 3 distinct six-control profiles; inheritance, types, invalid tokens, subset matching and 45 retained artistic controls')
    print('PASS: M17 51 options reachable exactly once across {} screens; valid sliders and one profile selector'.format(len(screens)))
    print('PASS: M17 159 unique English/Chinese keys with exact parity; all 152 previous English labels unchanged')
    print('LIMIT: profile semantics and compile fixtures only; no Iris settings-screen interaction or measured performance')


if __name__=='__main__':
    validate_settings_profiles(Path(__file__).resolve().parents[1])
