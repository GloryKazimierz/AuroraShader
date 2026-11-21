"""Check surf emission in the real water resolve and final display."""
from render_water_bench import display_rows, draw_text, png
from validate_gpu import require
from validate_gpu_water_transport import render_resolve, slab_scene


def surf_scene(seconds, night, sky=1.0):
    w,h=192,108
    scene=slab_scene(w,h,depth=2.,pitch=48.,sky=sky,block=.02,
                     source_rgb=(.019,.030,.048) if night else (.50,.55,.63))
    if night:
        scene['uniforms']=[(n,k,tuple(-c for c in v) if n=='sunPosition'
                          else (.025,.038,.070) if n=='fogColor' else v) for n,k,v in scene['uniforms']]
    scene['uniforms'].append(('frameTimeCounter','f1',(seconds,)))
    t=scene['textures']
    for y in range(h):
        for x in range(w//4):
            depth=t['colortex7'][y][x][3]
            for name in ('colortex6','depthtex0','depthtex1'):t[name][y][x]=(depth,0,0,1)
            t['colortex7'][y][x]=(0,0,0,0);t['colortex8'][y][x]=(0,0,0,0)
            t['colortex5'][y][x]=(.06,.045,.035,1.);t['colortex0'][y][x]=(.06,.045,.035,.5)
    return scene


def glow_tests(runner,plate=None):
    checks=[]
    w,h=192,108
    if plate:
        sheet=[[(12,18,27)]*(3*w) for _ in range(21+3*(h+18))]
        draw_text(sheet,4,6,'BIOLUMINESCENT SURF / WATER RESOLVE AND FINAL / AUTHORED SCENE')
    for i,(label,night,seconds,sky,options,active) in enumerate((
        ('DAY',False,17.,1.,{},False),('NIGHT 17 S',True,17.,1.,{},True),
        ('NIGHT 20 S',True,20.,1.,{},True),('STATIC',True,17.,1.,{'WATER_WAVE_SPEED':0},False),
        ('NO SKY ACCESS',True,17.,0.,{},False),('NO FOAM',True,17.,1.,{'WATER_FOAM':0},False))):
        scene=surf_scene(seconds,night,sky)
        opts=dict(WATER_FOAM=1,SHADOWS_ENABLED=False);opts.update(options)
        outputs=[render_resolve(runner,scene,dict(opts,WATER_BIOLUMINESCENCE=enabled),label=label) for enabled in (0,1)]
        differences=[];changed=0
        for y,(before,after) in enumerate(zip(*outputs)):
            for x,(a,b) in enumerate(zip(before,after)):
                require(a[3]==b[3],'Surf light changed alpha')
                d=tuple(v-u for u,v in zip(a[:3],b[:3]))
                if x<w//4:require(max(map(abs,d))==0,'Surf light escaped onto dry land')
                if max(d)>1e-4:
                    require(x>=w//4 and d[2]>d[1]>d[0]>=0,'Unexpected emission spectrum or footprint')
                    differences.append(d[2]);changed+=1
                if not active:require(a==b,'Inactive case admitted surf light '+label)
        if active:require(80<changed<w*h*3//4 and max(differences)>.03,'Missing or uniform nighttime light '+label)
        checks.append(dict(case=label,changed_pixels=changed,peak_linear_blue=max(differences,default=0.)))
        if plate and i<3:
            images=[]
            for raw in outputs:
                pixels=runner.render('surf display',runner.pair('final'),w,h,[('colortex0',raw,'RGBA32F')])
                images.append(display_rows(pixels))
            delta=[[tuple(min(255,4*abs(a-b)) for a,b in zip(p,q)) for p,q in zip(left,right)]
                   for left,right in zip(*images)]
            for col,img in enumerate(images+[delta]):
                x0,y0=col*w,21+i*(h+18)
                draw_text(sheet,x0+3,y0+5,label+' / '+('OFF','SURF LIGHT','DISPLAY DELTA X4')[col])
                for y,row in enumerate(img):sheet[y0+18+y][x0:x0+w]=row
    if plate:png(plate,sheet)
    return dict(cases=checks,scope='Real water resolve and final, authored shore and directional light. RGB emission at the water surface; environmental light propagation is outside this pass.')
