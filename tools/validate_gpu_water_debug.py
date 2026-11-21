"""Exercise the pack's actual water capture and final debug view on the same plane."""
import math
import re
import subprocess
from compile_glsl import ROOT, SHADERS, expand
from render_water_bench import (WIDTH, HEIGHT, WATER_VERTEX, make_scene, display_rows,
                                draw_text, png)
from validate_gpu import require, write_text
from validate_water_depth import reconstruct_view


def compare_fresnel_baseline(runner):
    frozen = 'df94fe404146c1364920f709569898359c84c8ed'
    old = subprocess.check_output(['git','-C',str(ROOT),'show',frozen+':shaders/lib/water.glsl'],
                                  encoding='utf-8')
    match = re.search(r'^float waterFresnel\([^}]+}', old, re.M)
    require(match is not None, 'W3 Fresnel function unavailable')
    fragment = ('#version 330 compatibility\n' + expand(SHADERS/'lib/water.glsl') + '\n'
                + match.group().replace('waterFresnel','referenceFresnel',1) + """
layout(location=0) out vec4 result;
void main() {
    float cosine = (gl_FragCoord.x - 1.5) / 1024.0;
    result = vec4(waterFresnel(cosine), referenceFresnel(cosine), 0.0, 1.0);
}
""")
    row = runner.render('fresnel-W3',runner.pair('composite1',wrapper=fragment),1027,1)[0]
    require(all(math.isfinite(p[0]) and p[0]==p[1] for p in row),'Fresnel differs from W3')
    require(row[1][0]==1 and abs(row[-2][0]-.02)<1e-8,'Fresnel endpoints differ')
    return len(row)


def nearest_candidates(index, source, window):
    numerator = (2*index+1)*source
    texel, remainder = divmod(numerator, 2*window)
    # At an exact mathematical texel edge either neighboring
    # center is equally near. Interpolated UV is finite precision.
    return (texel-1,texel) if remainder==0 else (texel,)


def debug_tests(runner, plate_path=None):
    scene = make_scene(35.0)
    # Use the same oblique perspective water plane as W3. Its analytic coverage
    # becomes atlas alpha so the production fragment's own discard is exercised.
    vertex = runner.scratch / 'debug-plane.vert'
    varyings = '''
uniform int material;
out vec2 lmcoord, texcoord;
out vec4 glcolor;
out vec3 normalView;
flat out int waterSurface;
'''
    setup = '''
    texcoord = gl_MultiTexCoord0.xy;
    lmcoord = vec2(0.5);
    glcolor = vec4(1.0);
    normalView = benchNormal;
    waterSurface = material;
'''
    write_text(vertex, WATER_VERTEX.replace('void main() {', varyings + '\nvoid main() {' + setup))
    common = {name: (name, kind, value) for name, kind, value in scene['uniforms']}
    plane_uniforms = [common[name] for name in ('gbufferProjection', 'benchNormal', 'benchEyeHeight')]
    z_shader = '#version 330 compatibility\nlayout(location=0) out vec4 result;\nvoid main(){result=vec4(gl_FragCoord.z,0,0,1);}\n'
    # Separate diagnostic draw measures raster depth independently of the producer.
    _, fs = runner.pair('composite1', wrapper=z_shader)
    water_z = runner.render('plane-depth', (vertex, fs), WIDTH, HEIGHT, uniforms=plane_uniforms)
    mask = scene['mask']
    atlas = [[(.25, .5, .75, pixel[0]) for pixel in row] for row in mask]
    tint = [[(1, 1, 1, 1)]]
    background = scene['depth']
    inv_data = common['gbufferProjectionInverse'][2]
    inverse = tuple(tuple(inv_data[col*4+row] for col in range(4)) for row in range(4))

    def capture(mode, material=1, waves=1):
        options = dict(DEBUG_VIEW=mode, WATER_WAVES=waves, FOG_ENABLED=0)
        _, fragment = runner.pair('gbuffers_water', options)
        names = ['viewWidth','viewHeight','gbufferProjectionInverse','gbufferModelViewInverse',
                 'upPosition','cameraPositionInt','cameraPositionFract','frameTimeCounter']
        uniforms = plane_uniforms + [('material', 'i1', (material,))] + [common[name] for name in names]
        textures = [('gtexture',atlas,'RGBA32F'),('lightmap',tint,'RGBA32F')]
        # Stage optimizers drop unused bindings in views that only need the water ID.
        optional = names + ['lightmap']
        image = runner.render('capture-'+str(mode), (vertex, fragment), WIDTH, HEIGHT, textures,
                              uniforms, optional=optional, extra_targets=((1,1,'RGBA32F'),), read_target=1)
        for y, row in enumerate(image):
            for x, record in enumerate(row):
                if not mask[y][x][0]:
                    require(record[3] == -13, 'atlas hole did not discard')
                    # The harness clears to a sentinel. Model the declared Iris
                    # clear only after proving every hole still has its sentinel.
                    row[x] = (0,0,0,0)
                else:
                    require(record[3] != -13, 'covered fragment did not write capture')
        return image

    def display(mode, record, final_z, opaque=background, size=(WIDTH, HEIGHT)):
        pair = runner.pair('final', {'DEBUG_VIEW':mode})
        textures = [('colortex7',record,'RGBA32F'),('depthtex0',final_z,'R32F'),
                    ('depthtex2',opaque,'R32F')]
        uniforms = [common['gbufferProjectionInverse'],common['gbufferModelViewInverse']]
        return runner.render('display-'+str(mode), pair, *size, textures, uniforms,
                             optional=['depthtex2','gbufferProjectionInverse','gbufferModelViewInverse'])

    frames = []
    stats = {}
    up = common['upPosition'][2]
    for mode in (7,8,9):
        record = capture(mode)
        result = display(mode, record, water_z)
        changed_normals = valid_count = 0
        max_gap_error = 0.0
        for y,row in enumerate(result):
            for x,pixel in enumerate(row):
                if not mask[y][x][0]:
                    require(pixel == (0,0,0,1),'lit pixel outside water mask')
                    continue
                valid_count += 1
                if mode == 7:
                    require(pixel == (1,1,1,1), 'mask missed water')
                elif mode == 8:
                    normal = tuple(2*c-1 for c in pixel[:3])
                    require(abs(math.sqrt(sum(c*c for c in normal))-1) < 2e-5,'normal is not unit length')
                    require(sum(a*b for a,b in zip(normal,up)) > .94,'normal in wrong space')
                    changed_normals += max(abs(a-b) for a,b in zip(normal,up)) > 1e-4
                else:
                    uv = ((x+.5)/WIDTH,(y+.5)/HEIGHT)
                    front = reconstruct_view(uv, water_z[y][x][0], inverse)
                    opaque_z = background[y][x][0]
                    back = reconstruct_view(uv, opaque_z, inverse)
                    require(opaque_z < 1 and back is not None and front is not None,'fixture missing floor')
                    expected = min(1.0, math.dist(front,back)/GAP_METERS)
                    max_gap_error = max(max_gap_error, abs(pixel[0]-expected))
                    require(max(abs(c-expected) for c in pixel[:3]) < 3e-4,'ray-gap display differs from independent depth reconstruction')
        if mode == 8:
            require(changed_normals > valid_count // 2, 'filtered wave detail absent')
        # An odd-sized output verifies screen UV addressing when Iris presents
        # the internal render target at a different window resolution.
        size = (173, 97)
        scaled = display(mode, record, water_z, size=size)
        for y,row in enumerate(scaled):
            for x,value in enumerate(row):
                xs = nearest_candidates(x,WIDTH,size[0])
                ys = nearest_candidates(y,HEIGHT,size[1])
                require(any(value==result[sy][sx] for sy in ys for sx in xs),
                        f'view {mode} window ({x},{y}) differs from nearest source texel')
        frames.append(display_rows(result))
        stats[str(mode)] = dict(water_pixels=valid_count, perturbed_normals=changed_normals,
                                max_gap_display_error=max_gap_error)
    black = (0,0,0,1)
    for label, mode, material, final_depth in [('glass',7,0,water_z),('front-depth',7,1,[[(.2,0,0,1)]*WIDTH for _ in range(HEIGHT)])]:
        tested = display(mode, capture(mode, material=material), final_depth)
        require(all(p == black for row in tested for p in row),label+' displayed false water')
    # A cleared background depth cannot describe an optical path length.
    missing = [[(1,0,0,1)]*WIDTH for _ in range(HEIGHT)]
    result = display(9,record,water_z,opaque=missing)
    for y,row in enumerate(result):
        for x,value in enumerate(row):
            require(value == ((1,0,1,1) if mask[y][x][0] else black), 'missing floor ambiguity')
    fresnel_samples = compare_fresnel_baseline(runner)
    if plate_path:
        sheet = [[(21,25,32)]*(3*WIDTH) for _ in range(HEIGHT+21)]
        for index,(label,rows) in enumerate(zip(('WATER MASK','FILTERED VIEW NORMAL','RAY GAP / 16 M'),frames)):
            draw_text(sheet,index*WIDTH+5,6,label)
            for y,row in enumerate(rows):
                sheet[y+21][index*WIDTH:(index+1)*WIDTH] = row
        png(plate_path,sheet)
    return dict(views=stats,fresnel_samples_exact=fresnel_samples,scaled_window_pixels_checked=173*97*3,
                negative_cases=['glass','front-depth','missing-floor'],resolution=[WIDTH,HEIGHT],
                scope='Actual pack fragment and final shaders on synthetic oblique pool. CPU transfer between passes. No live Iris ordering or GPU timing.')


GAP_METERS = 16.0
