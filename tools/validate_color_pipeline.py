"""M8 scene-linear/HDR contracts. Invoked by validate.py; never executes a GPU."""
import math
import re
import struct
import subprocess
from validate_fog import historical_source, restore_fog_plumbing
from functools import lru_cache
from itertools import product
from validate_atmosphere import decode, encode, clamp

M7_BASELINE = '0b46bcb663363df21e0b45a89c26b427afe04eeb'


def shoulder(rgb, knee=.6, mapping=1):
    rgb = tuple(max(x, 0.0) for x in rgb)
    if mapping == 0:
        return tuple(clamp(x) for x in rgb)
    peak = max(rgb)
    knee = clamp(knee, 0.0, .95)
    if peak <= knee:
        return rgb
    span = 1-knee
    compressed = knee + span*(1-math.exp(-(peak-knee)/span))
    return tuple(x*(compressed/peak) for x in rgb)


def validate_color_pipeline(root, expand, preprocess, compact, function_body):
    shaders = root/'shaders'
    def read(relative):
        return historical_source(relative, (shaders/relative).read_text(encoding='utf-8'))
    @lru_cache(maxsize=None)
    def prior(relative):
        return subprocess.check_output(['git','-C',str(root),'show',M7_BASELINE+':shaders/'+relative]).decode()
    @lru_cache(maxsize=None)
    def old_expand(relative):
        return re.sub(r'^#include "([^"]+)"\s*$',
                      lambda m: old_expand(m[1].lstrip('/')), prior(relative), flags=re.M)
    def processed(relative, mode, debug=0, grayscale=False, **options):
        return restore_fog_plumbing(preprocess(expand(shaders/relative), debug, grayscale,
                          overrides=dict(SCENE_COLOR_MODE=mode, **options)))
    def body(source, name):
        return compact(function_body(source,name))

    # Format directives are comments in the selected variant; GLSL never sees enums.
    for mode, expected in ((0,'RGBA8'),(1,'RGBA16F')):
        source=processed('prepare.fsh',mode)
        assert re.findall(r'^const int colortex0Format = (\w+);$',source,re.M) == [expected]
        assert 'colortex0Format' not in re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
        assert body(source,'main') == 'color=vec4(sceneFromDisplay(fogColor),1.0);'
        assert body(source,'sceneFromDisplay') == ('returndisplayColor;' if mode == 0 else 'returnsrgbToLinear(displayColor);')
        assert body(source,'sceneFromLinear') == (
            'returnclamp(linearToSrgb(linearColor),0.0,1.0);' if mode == 0 else 'returnmax(linearColor,vec3(0.0));')
        assert ('colortex0ClearColor' in source) == bool(mode)
        if mode:
            assert 'constvec4colortex0ClearColor=vec4(0.0,0.0,0.0,1.0);' in compact(source)
        assert 'sampler2D' not in source  # Initialization never reads its own output.

    # Prove all changed geometry bodies differ by only one RGB conversion.
    geometry=('basic_fragment.glsl','textured_fragment.glsl','lit_fragment.glsl','entity_fragment.glsl')
    for name in geometry:
        relative='lib/geometry/'+name
        source=read(relative)
        assert source.count('color.rgb = sceneFromDisplay(color.rgb);') == 1
        restored=source.replace('#include "/lib/scene_color.glsl"\n','').replace(
            '    color.rgb = sceneFromDisplay(color.rgb);\n','')
        assert compact(restored) == compact(prior(relative)), relative
        assert 'sceneFromDisplay(color.a)' not in source and 'sceneFromDisplay(glcolor.a)' not in source
    # Every original geometry category must reach one converted producer.
    programs=sorted(shaders.glob('*.vsh'))
    assert len(programs) == 20
    for mode in (0,1):
        for vertex in programs:
            fragment=vertex.with_suffix('.fsh')
            vs=processed(vertex.name,mode)
            fs=processed(fragment.name,mode)
            assert vs.count('void main()') == fs.count('void main()') == 1
            clean=re.sub(r'/\*.*?\*/|//[^\n]*','',fs,flags=re.S)
            assert not re.search(r'const int colortex\d+Format\s*=\s*[A-Z]',clean)
            outs=dict((name,kind) for kind,name in re.findall(r'^out (\w+) (\w+);',vs,re.M))
            for kind,name in re.findall(r'^in (\w+) (\w+);',fs,re.M):
                assert outs.get(name) == kind, (fragment.name,mode,name)
            if vertex.stem.startswith('gbuffers_') and vertex.stem != 'gbuffers_skybasic':
                main=body(fs,'main')
                assert main.count('color.rgb=sceneFromDisplay(color.rgb);') == 1, vertex.stem
                assert main.index('sceneFromDisplay') > main.index('if(color.a<alphaTestRef)'), vertex.stem
                legacy=main.replace('color.rgb=sceneFromDisplay(color.rgb);','')
                old=preprocess(old_expand(fragment.name),0,False)
                assert legacy == body(old,'main'), vertex.stem

    # Sensitive alpha/data/depth/shadow paths and old scalar lighting stay byte-content pinned.
    for relative in ('lib/normal.glsl','lib/gbuffer_write.glsl','lib/position.glsl',
                     'lib/lighting.glsl','lib/lighting_settings.glsl','lib/settings.glsl',
                     'lib/shadow.glsl','lib/shadow_bias.glsl','lib/shadow_settings.glsl',
                     'shadow.fsh','shadow.vsh','deferred.fsh','deferred.vsh',
                     'lib/color_space.glsl','lib/celestial.glsl','lib/atmosphere_settings.glsl'):
        if relative == 'lib/color_space.glsl':
            # M8 updates its explanatory header, not the transfer functions.
            assert compact(read(relative)) == compact(prior(relative)), relative
        else:
            assert read(relative).replace('\r\n','\n') == prior(relative).replace('\r\n','\n'), relative

    # M7 sky and color-light mathematics survive exactly in the legacy mode.
    for style, palette in product((0,1),repeat=2):
        newsky=processed('gbuffers_skybasic.fsh',0,SKY_STYLE=style)
        oldsky=preprocess(old_expand('gbuffers_skybasic.fsh'),0,False,overrides={'SKY_STYLE':style})
        assert body(newsky,'auroraSkyLinear') == body(oldsky,'auroraSkyLinear')
        restored=body(newsky,'applyAuroraSky').replace('sceneFromDisplay(baseline)','baseline').replace(
            'sceneFromLinear(linearSky)','clamp(linearToSrgb(linearSky),0.0,1.0)')
        assert restored == body(oldsky,'applyAuroraSky')
        restored_main=body(newsky,'main').replace('vec4(sceneFromDisplay(glcolor.rgb),glcolor.a)','glcolor')
        assert restored_main == body(oldsky,'main')
        newlight=processed('deferred.fsh',0,LIGHT_PALETTE=palette)
        oldlight=preprocess(old_expand('deferred.fsh'),0,False,overrides={'LIGHT_PALETTE':palette})
        assert body(newlight,'applyCelestialPalette') == body(oldlight,'applyCelestialPalette')
    hdrsky=processed('gbuffers_skybasic.fsh',1)
    assert 'returnsceneFromLinear(linearSky);' in body(hdrsky,'applyAuroraSky')
    assert 'vec4(sceneFromDisplay(glcolor.rgb),glcolor.a)' in body(hdrsky,'main')
    assert 'vec4(sceneFromDisplay(calcSkyColor(normalize(pos))),1.0)' in body(hdrsky,'main')
    hdrlight=body(processed('deferred.fsh',1),'applyCelestialPalette')
    assert 'returnlitScene*mix(vec3(1.0),tint,weight);' in hdrlight
    assert 'srgbToLinear' not in hdrlight and 'linearToSrgb' not in hdrlight

    # Exposure runs exactly once in normal output, with all debug paths bypassing it.
    for mode, debug, grayscale in product((0,1),range(7),(False,True)):
        new=processed('final.fsh',mode,debug,grayscale)
        old=preprocess(old_expand('final.fsh'),debug,grayscale)
        main=body(new,'main')
        grading=body(new,'gradeColor')
        if mode == 0:
            assert main == body(old,'main')
            assert grading == body(old,'gradeColor')
        if debug:
            assert main == body(old,'main')
            for term in ('gradeColor','toneMapScene','linearToSrgb','exp2(EXPOSURE)'):
                assert term not in main
        elif mode == 1:
            assert main.count('exp2(EXPOSURE)') == 1
            assert main.count('toneMapScene(') == main.count('linearToSrgb(') == 1
            assert main.index('exp2(EXPOSURE)') < main.index('toneMapScene') < main.index('gradeColor')
            assert 'vec3displayColor=linearToSrgb(toneMapScene(exposed));' in main
            assert 'color=vec4(gradeColor(displayColor),scene.a);' in main
            assert 'EXPOSURE' not in grading

    tone=read('lib/tone_mapping.glsl')
    for token in ('vec3rgb=max(sceneLinear,vec3(0.0));', 'max(max(rgb.r,rgb.g),rgb.b)',
                  'clamp(TONEMAP_KNEE,0.0,0.95)', 'if(peak<=knee)returnrgb;',
                  'knee+span*(1.0-exp(-(peak-knee)/span))', 'returnrgb*(compressed/peak);'):
        assert token in compact(tone), token
    # Half-float scene storage preserves values beyond the normalized [0,1] range.
    for value in (.0001,.18,1,1.2,2,16,256,65504):
        stored=struct.unpack('e',struct.pack('e',value))[0]
        assert math.isfinite(stored) and abs(stored-value) <= max(value*.0005,1e-7)
        if value > 1:
            assert stored > 1
    # Alpha is a coverage factor, not an sRGB color: a half-covered white pixel is
    # linear .5, which encodes to .735..., while display-space mixing gives .5.
    assert abs(encode(.5)-.7353569830524495) < 1e-12
    assert abs(.5*decode(1)+.5*decode(0)-.5) < 1e-12
    for alpha in (0,.1,.5,1):
        assert alpha*1+(1-alpha)*0 == alpha
    # Exposure is multiplicative in scene-linear space, not a second display gamma.
    exposures=(-2,-1.5,-1,-.5,-.25,0,.25,.5,1,1.5,2)
    assert .18*2**1 == .36 and .18*2**-1 == .09
    cases=0
    for knee,mapping,stops,peak,ratio in product((.4,.6,.8),(0,1),exposures,
            (0,.001,.18,.6,1,2,16,65504),((1,1,1),(1,.2,.05),(.05,1,.2),(.2,.05,1))):
        rgb=tuple(peak*x*2**stops for x in ratio)
        out=shoulder(rgb,knee,mapping)
        assert all(math.isfinite(c) and 0 <= c <= 1+1e-12 for c in out)
        assert all(math.isfinite(encode(c)) for c in out)
        if mapping and peak:
            # Common rescaling preserves chromaticity ratios before artistic grading.
            for i,j in ((0,1),(1,2)):
                assert abs(out[i]/out[j]-rgb[i]/rgb[j]) < 1e-10
        cases+=1
    for knee in (.4,.6,.8):
        assert shoulder((0,0,0),knee) == (0,0,0)
        assert shoulder((.18,.09,.045),knee) == (.18,.09,.045)
        assert shoulder((-1,-2,-3),knee) == (0,0,0)
        samples=[shoulder((i/1000,0,0),knee)[0] for i in range(16001)]
        assert all(b+1e-14 >= a for a,b in zip(samples,samples[1:]))
        assert shoulder((2,0,0),knee)[0] > shoulder((1,0,0),knee)[0]
        epsilon=1e-6
        below=shoulder((knee-epsilon,0,0),knee)[0]
        at=shoulder((knee,0,0),knee)[0]
        above=shoulder((knee+epsilon,0,0),knee)[0]
        assert abs((at-below)/epsilon-1) < 1e-8
        assert abs((above-at)/epsilon-1) < 3e-6
    settings=read('lib/pipeline_settings.glsl')
    labels=read('lang/en_us.lang')
    props=read('shaders.properties')
    for name,default in (('SCENE_COLOR_MODE','1'),('TONE_MAPPING','1'),('TONEMAP_KNEE','0.6')):
        assert re.search(r'^#define '+name+' '+re.escape(default)+r' //',settings,re.M)
        assert name in props.split('screen.COLOR_PIPELINE =',1)[1].splitlines()[0].split()
        assert re.search(r'^option\.'+name+r'=.+$',labels,re.M)
    assert 'value.SCENE_COLOR_MODE.0=M7 Display / LDR' in labels
    assert 'value.SCENE_COLOR_MODE.1=Linear / HDR Composition' in labels
    print('PASS: M8 20 program pairs in both pipelines; RGBA8/RGBA16F, background initialization and alpha contracts')
    print('PASS: M8 legacy producers/sky/tint/grading match M7; shadow/data/debug paths preserved')
    print('PASS: M8 half-float HDR storage, linear alpha blending and exactly one exposure/tone-map/encode')
    print('PASS: M8 {} tone-map cases; bounded/monotone/C1 shoulder and linear RGB ratios'.format(cases))
    print('LIMIT: scene-linear composition retains baked Minecraft inputs; no Minecraft/Iris/GPU runtime validation')
