"""Compare art-directed water media under the same neutral bed and light."""
from render_water_bench import display_rows, draw_text, png
from validate_gpu import compare, require
from validate_gpu_water_transport import render_resolve, slab_expected, slab_scene


def material_tests(runner, plate=None):
    width,height=112,60
    names=('FRESHWATER','GLACIAL','AMBER STREAM','BLUE SEA')
    depths=(.35,2.,8.)
    samples=[]
    if plate:
        sheet=[[(14,19,24)]*width*4 for _ in range((height+18)*len(depths)+19)]
        draw_text(sheet,3,4,'WATER BODY / MATCHED WHITE BED AND SUN / DEPTH IN METRES')
    for index,depth in enumerate(depths):
        scene=slab_scene(width,height,depth=depth,pitch=60.,source_rgb=(.75,.75,.75))
        colors=[]
        for body,label in enumerate(names):
            frame=render_resolve(runner,scene,{'WATER_BODY':body},label=label)
            comparison=compare(frame,slab_expected(scene,body=body),label,absolute=4e-5,relative=4e-4)
            require(all(pixel[3]==source[3] for row,original in zip(frame,scene['textures']['colortex0'])
                        for pixel,source in zip(row,original)),label+' changed scene alpha')
            rgb=frame[height//2][width//2][:3]
            colors.append(rgb)
            samples.append(dict(body=label,depth_m=depth,center_linear=rgb,comparison=comparison))
            if plate:
                display=runner.render('material final',runner.pair('final'),width,height,[('colortex0',frame,'RGBA32F')])
                x0=body*width;y0=19+index*(height+18)
                draw_text(sheet,x0+2,y0+4,label+' '+str(depth))
                for y,row in enumerate(display_rows(display)):
                    sheet[y0+18+y][x0:x0+width]=row
        require(len(set(colors))==4,'Water material selector has duplicate results')
        if depth==8.:
            fresh,glacial,amber,blue=colors
            require(amber[0]>amber[1]>amber[2] and blue[2]>blue[1]>blue[0]
                    and glacial[1]>glacial[0],'Deep-water channel ordering is inconsistent')
    transitions=[]
    small=slab_scene(48,28,depth=2.,pitch=60.,source_rgb=(.75,.75,.75))
    for label,upload,weights in (
        ('fresh',(0,0,0),(1,0,0,0)),('frozen river',(1,0,0),(0,1,0,0)),
        ('swamp',(0,1,0),(0,0,1,0)),('ocean',(0,0,1),(0,0,0,1)),
        ('river to swamp',(0,.25,0),(.75,0,.25,0)),('melting coast',(.4,0,.6),(0,.4,0,.6)),
        ('lagged blend',(.8,.8,0),(0,.5,.5,0)),('invalid',(float('nan'),0,0),(1,0,0,0))):
        scene=dict(small,uniforms=small['uniforms']+[('auroraWaterBiomeWeights','f3',upload)])
        actual=render_resolve(runner,scene,{'WATER_BODY':4},label=label)
        result=compare(actual,slab_expected(scene,body=weights),label,absolute=4e-5,relative=4e-4)
        require(all(p[3]==q[3] for row,old in zip(actual,scene['textures']['colortex0']) for p,q in zip(row,old)),'Automatic water changed scene alpha')
        transitions.append(dict(case=label,comparison=result))
    if plate:
        png(plate,sheet)
    return dict(pixels=len(samples)*width*height,samples=samples,automatic=transitions,
                input='Native full composite and final, synthetic neutral checker bed and identical lighting')
