"""K source gates, finite history-clock contract and exact opt-out behavior."""
from itertools import product
from pathlib import Path
import math
from compile_glsl import ROOT,SHADERS,expand

def restore_temporal_entry(source):
    """Remove only the three exact K entry additions for older source pinning.

    Runtime equivalence below preprocesses the ACTUAL source, never this adapter.
    """
    include='#include "/lib/water_temporal.glsl"\n'
    target="""#ifdef AURORA_WATER_TEMPORAL_ACTIVE
/* RENDERTARGETS: 0,12 */
layout(location = 1) out vec4 waterHistory;
#else
/* RENDERTARGETS: 0 */
#endif
"""
    call="""#ifdef AURORA_WATER_TEMPORAL_ACTIVE
    // History contains no bloom. Filter only proven water, then add this frame's
    // bloom once below. No jitter, exposure change or temporal glow feedback.
    scene.rgb = resolveWaterTemporal(colortex0,scene.rgb,pixel,textureSize(colortex0,0),waterHistory);
#endif
"""
    for old,new in ((include,''),(target,'/* RENDERTARGETS: 0 */\n'),(call,'')):
        if source.count(old)!=1:raise ValueError('K entry adaptation changed')
        source=source.replace(old,new)
    return source


def header_valid(frame,timer,dt,second,date,medium,size,a,b):
    # Mathematical sequence predicate, deliberately independent of any shaders.
    if not all(math.isfinite(x) for x in (timer,dt)+a+b):return False
    return (0<=frame<=720719 and 2.1<=timer<3600 and 0<dt<=.1
            and a==(float(frame or 720720),float(size[0]),float(size[1]),float(medium))
            and 0<=b[0]<3600 and 0<=second-b[1]<=1 and b[2]==date and b[3]==1
            and abs((0 if b[0]+dt>=3600 else b[0]+dt)-timer)<=.001)


def test_temporal():
    from validate import select,semantic_lines,routing,require,FEATURE
    from validate_settings_profiles import option_definitions,load_profiles
    options=option_definitions(ROOT)
    require(options['WATER_TEMPORAL']['default']=='0','Temporal must remain opt-in')
    require(all('WATER_TEMPORAL' not in p for p in load_profiles(ROOT).values()),'Temporal profile override')
    source=expand(SHADERS/'composite5.fsh');checks=0
    for enabled,supported,optics,style,hdr,debug in product((0,1),(False,True),(0,1),(0,1),(0,1),(0,8)):
        case=dict(WATER_TEMPORAL=enabled,IRIS_FEATURE_PER_BUFFER_BLENDING=supported,
                  WATER_OPTICS=optics,WATER_STYLE=style,SCENE_COLOR_MODE=hdr,DEBUG_VIEW=debug)
        body,macros=select(source,case)
        active=bool(enabled and supported and optics and style and hdr and not debug)
        require(('AURORA_WATER_TEMPORAL_ACTIVE' in macros)==active,'Temporal gate mismatch')
        require(routing(body)==((0,12) if active else (0,)),'Temporal MRT route mismatch')
        for token in ('const int colortex12Format = RGBA32F;','const bool colortex12Clear = false;'):
            require((token in body)==active,'Temporal allocation/clear differs')
        if not active:
            baseline,_=select(source,dict(case,WATER_TEMPORAL=0))
            require(semantic_lines(body)==semantic_lines(baseline),'Actual disabled stage changed')
        checks+=1
    text=(SHADERS/'composite5.fsh').read_text(encoding='utf-8')
    require(text.index('resolveWaterTemporal(')<text.index('if (!bloomActive()) return;')<text.index('upsampleBloom('),
            'Temporal moved after bloom or behind bloom-off bypass')
    require('scene.a' in text and 'scene.rgb = resolveWaterTemporal' in text,'Alpha must remain native')
    a=(200.,32.,24.,1.);date=2026*372+11*31+21;b=(17.,43217.,float(date),1.)
    require(header_valid(200,17+1/60,1/60,43217,date,1,(32,24),a,b),'Normal history rejected')
    require(header_valid(200,17+1/60,1/60,43218,date,1,(32,24),a,b),'Normal wall-second boundary rejected')
    for kwargs in ((199,17+1/60,43217),(200,1.,43217),(200,17+1/60,43220),(200,17+1/60,43216)):
        frame,timer,second=kwargs
        require(not header_valid(frame,timer,1/60,second,date,1,(32,24),a,b),'Cached/reset history admitted')
    print(f'PASS: {checks} temporal gates, exact disabled stages, pre-bloom order and finite clock cases')
    return checks

if __name__=='__main__':test_temporal()
