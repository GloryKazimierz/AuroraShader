#ifndef AURORA_WATER_CAUSTICS_INCLUDED
#define AURORA_WATER_CAUSTICS_INCLUDED
#include "/lib/water_caustics_settings.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
#include "/lib/water_params.glsl"
#include "/lib/water_caustics_packing.glsl"
#include "/lib/position.glsl"
#include "/lib/water_shadow_bindings.glsl"

bool causticFinite(float v) { return !isnan(v) && !isinf(v); }
bool causticFinite3(vec3 v) { return !any(isnan(v)) && !any(isinf(v)); }
bool causticProject(vec3 player, out vec3 coord) {
    coord = vec3(0.0);
    if (!causticFinite3(player)) return false;
    vec4 clip = shadowProjection * shadowModelView * vec4(player, 1.0);
    if (any(isnan(clip)) || any(isinf(clip)) || clip.w <= 1e-6) return false;
    coord = clip.xyz / clip.w * 0.5 + 0.5;
    return causticFinite3(coord) && all(greaterThanEqual(coord, vec3(0.0)))
        && all(lessThan(coord, vec3(1.0)));
}
bool causticUnproject(vec2 uv, float depth, out vec3 player) {
    player = vec3(0.0);
    if (!causticFinite(depth) || depth < 0.0 || depth >= 1.0) return false;
    vec4 light = shadowProjectionInverse * vec4(vec3(uv, depth) * 2.0 - 1.0, 1.0);
    vec4 point = shadowModelViewInverse * light;
    if (any(isnan(point)) || any(isinf(point)) || abs(point.w) <= 1e-6) return false;
    player = point.xyz / point.w;
    return causticFinite3(player);
}
bool causticRay(vec3 incident, vec3 normal, float waterIOR, out vec3 refracted) {
    refracted = vec3(0.0);
    if (!causticFinite3(incident) || !causticFinite3(normal)
        || abs(dot(incident,incident)-1.0) > 0.001
        || abs(dot(normal,normal)-1.0) > 0.001 || normal.y < 0.65) return false;
    float cosine = -dot(incident,normal);
    if (cosine <= 0.03) return false;
    if (!causticFinite(waterIOR) || waterIOR < 1.0 || waterIOR > 2.0) return false;
    float eta = 1.0 / waterIOR;
    float k = 1.0 - eta*eta*(1.0-cosine*cosine);
    if (!causticFinite(k) || k <= 0.0) return false;
    refracted = eta*incident + (eta*cosine-sqrt(k))*normal;
    return causticFinite3(refracted) && refracted.y < -0.03;
}
// Every corner of a filtered lookup must identify the SAME horizontal top
// interface. Unknown translucent layers, clear sky and opaque overwrites fail.
bool causticSurface(vec2 xz, float waterY, float bedY, ivec2 size, out vec3 normal) {
    normal = vec3(0.0);
    vec3 projected;
    if (!causticProject(vec3(xz.x,waterY,xz.y),projected)) return false;
    vec2 pixel = projected.xy*vec2(size)-0.5;
    ivec2 first = ivec2(floor(pixel));
    if (any(lessThan(first,ivec2(1))) || any(greaterThanEqual(first+ivec2(1),size-ivec2(1)))) return false;
    vec2 fraction = fract(pixel);
    for (int y=0;y<2;++y) for (int x=0;x<2;++x) {
        ivec2 p=first+ivec2(x,y);
        vec4 record=texelFetch(shadowcolor0,p,0);
        float front=texelFetch(shadowtex0,p,0).r;
        float opaque=texelFetch(shadowtex1,p,0).r;
        vec3 sampleNormal;
        if (!decodeWaterCaustic(record,front,sampleNormal)
            || !causticFinite(opaque) || opaque<=front+1.0/16777215.0 || opaque>=1.0) return false;
        vec3 actual;
        // Reconstruct from real shadow depth, never the compact identity code.
        if (!causticUnproject((vec2(p)+0.5)/vec2(size),front,actual)
            || abs(actual.y-waterY)>0.025) return false;
        vec3 sourceBed;
        if (!causticUnproject((vec2(p)+0.5)/vec2(size),opaque,sourceBed)
            || abs(sourceBed.y-bedY)>0.025) return false;
        vec2 weight=mix(vec2(1.0)-fraction,fraction,vec2(x,y));
        normal += sampleNormal*weight.x*weight.y;
    }
    if (!causticFinite3(normal) || dot(normal,normal)<0.9) return false;
    normal=normalize(normal);
    return true;
}
bool causticMap(vec2 xz, float waterY, float bedY, vec3 incident, float waterIOR, ivec2 size,
                 out vec2 landing) {
    landing=vec2(0.0);
    vec3 normal,ray;
    if (!causticSurface(xz,waterY,bedY,size,normal) || !causticRay(incident,normal,waterIOR,ray)) return false;
    float travel=(bedY-waterY)/ray.y;
    if (!causticFinite(travel) || travel<=0.0 || travel>64.0) return false;
    landing=xz+travel*ray.xz;
    return !any(isnan(landing)) && !any(isinf(landing));
}
// Local finite-area flux relative to a FLAT horizontal interface. It is not a
// globally normalized multi-path photon solve: folds/unknown ownership reject.
float causticAreaGain(vec2 columnX, vec2 columnZ) {
    float area=columnX.x*columnZ.y-columnX.y*columnZ.x;
    if (!causticFinite(area) || area<=0.05) return 1.0;
    return min(4.0,1.0/area);
}
// Analytic pixel-corner ray/plane intersections avoid dFdx/dFdy inside
// divergent material/trace branches. This is the camera footprint of the
// horizontal receiver, not a Jacobian of a refracted multi-interface ray bundle.
bool waterCausticPixelFootprint(vec3 pointView, ivec2 size, mat4 projection,
    mat4 inverseProjection, mat4 inverseView, out vec2 dx, out vec2 dy) {
    dx=vec2(0.0);dy=vec2(0.0);
    if (!causticFinite3(pointView) || any(lessThanEqual(size,ivec2(0)))
        || abs(projection[3][3])>1e-6 || projection[2][3]>=-1e-6) return false;
    vec4 clip=projection*vec4(pointView,1.0);
    vec4 originH=inverseView*vec4(0.0,0.0,0.0,1.0);
    vec4 receiverH=inverseView*vec4(pointView,1.0);
    if (any(isnan(clip)) || any(isinf(clip)) || clip.w<=1e-6
        || any(isnan(originH)) || any(isinf(originH)) || abs(originH.w)<=1e-6
        || any(isnan(receiverH)) || any(isinf(receiverH)) || abs(receiverH.w)<=1e-6) return false;
    vec3 origin=originH.xyz/originH.w;
    float bedY=receiverH.y/receiverH.w;
    vec2 uv=clip.xy/clip.w*.5+.5;
    const vec2 offsets[4]=vec2[4](vec2(-.5,0),vec2(.5,0),vec2(0,-.5),vec2(0,.5));
    vec2 points[4];
    for(int i=0;i<4;++i) {
        vec2 sampleUV=uv+offsets[i]/vec2(size);
        vec4 view=inverseProjection*vec4(sampleUV*2.0-1.0,0.0,1.0);
        if(any(isnan(view)) || any(isinf(view)) || abs(view.w)<=1e-6) return false;
        vec3 ray=mat3(inverseView)*(view.xyz/view.w);
        if(!causticFinite3(ray) || abs(ray.y)<=1e-8) return false;
        float travel=(bedY-origin.y)/ray.y;
        if(!causticFinite(travel) || travel<=0.0) return false;
        points[i]=(origin+ray*travel).xz;
        if(any(isnan(points[i])) || any(isinf(points[i]))) return false;
    }
    dx=points[1]-points[0];dy=points[3]-points[2];
    return true;
}
float causticResolutionWeight(vec2 footprintX,vec2 footprintY) {
    if(any(isnan(footprintX)) || any(isinf(footprintX))
        || any(isnan(footprintY)) || any(isinf(footprintY))) return 0.0;
    float span=max(length(footprintX),length(footprintY));
#if WATER_SURFACE_DETAIL == 1
    float shortest=128.0/length(vec2(151.0,97.0));
#else
    float shortest=128.0/length(vec2(7.0,13.0));
#endif
    // Conservative whole-field Nyquist fade based on the shortest admitted
    // shared wave. Far/grazing pixels can lose resolved broad detail safely.
    float frequency=span/shortest;
    if(!causticFinite(frequency)) return 0.0;
    return 1.0-smoothstep(.25,.5,frequency);
}
float waterShadowCausticGain(vec3 waterPlayer, vec3 bedPlayer, vec3 bedNormalWorld,
                             vec3 towardLightWorld, float directShare,
                             vec2 footprintX, vec2 footprintY, float waterIOR) {
#if WATER_WAVES == 0
    return 1.0; // The actual wave-off surface has no focusing; exact baseline.
#else
    if (float(WATER_WAVE_STRENGTH) <= 0.0) return 1.0;
    float resolutionWeight=causticResolutionWeight(footprintX,footprintY);
    if(resolutionWeight<=0.0) return 1.0;
    if (!causticFinite3(waterPlayer) || !causticFinite3(bedPlayer)
        || !causticFinite3(bedNormalWorld) || !causticFinite3(towardLightWorld)
        || !causticFinite(directShare) || directShare<=0.0 || directShare>1.0
        || float(WATER_CAUSTICS_STRENGTH)<=0.0) return 1.0;
    float depth=waterPlayer.y-bedPlayer.y;
    if (depth<=0.03 || depth>=24.0 || abs(dot(bedNormalWorld,bedNormalWorld)-1.0)>0.001
        || bedNormalWorld.y<0.95 || dot(towardLightWorld,towardLightWorld)<=1e-12) return 1.0;
    vec3 incident=-normalize(towardLightWorld);
    if (incident.y>=-0.08) return 1.0;
    ivec2 size=textureSize(shadowcolor0,0);
    if (any(lessThan(size,ivec2(8))) || any(notEqual(size,textureSize(shadowtex0,0)))
        || any(notEqual(size,textureSize(shadowtex1,0)))) return 1.0;
    // Prove the receiver belongs to the front opaque horizontal bed in light
    // space. Compare reconstructed height, not a wide normalized-depth epsilon.
    vec3 receiverUV;
    if (!causticProject(bedPlayer,receiverUV)) return 1.0;
    ivec2 receiverPixel=ivec2(receiverUV.xy*vec2(size));
    vec3 opaque;
    if (!causticUnproject((vec2(receiverPixel)+0.5)/vec2(size),
        texelFetch(shadowtex1,receiverPixel,0).r,opaque) || abs(opaque.y-bedPlayer.y)>0.025) return 1.0;
    vec3 flatRay;
    if (!causticRay(incident,vec3(0.0,1.0,0.0),waterIOR,flatRay)) return 1.0;
    vec2 entry=bedPlayer.xz-flatRay.xz*(-depth/flatRay.y);
    // Four bounded fixed-point refinements; un-converged/folded maps retain the
    // unmodified direct light instead of claiming a ray hit on another surface.
    vec2 landing;
    for (int iteration=0;iteration<4;++iteration) {
        if (!causticMap(entry,waterPlayer.y,bedPlayer.y,incident,waterIOR,size,landing)) return 1.0;
        vec2 correction=landing-bedPlayer.xz;
        if (length(correction)>2.0) return 1.0;
        entry-=correction;
    }
    if (!causticMap(entry,waterPlayer.y,bedPlayer.y,incident,waterIOR,size,landing)
        || length(landing-bedPlayer.xz)>0.015) return 1.0;
    // A finite beam footprint broadens with depth, suppressing small-scale
    // curvature rather than applying an unbounded point-Jacobian singularity.
    // This is an artistic diffusion approximation, not measured water scattering.
    float radius=max(0.04+0.03*depth,.5*max(length(footprintX),length(footprintY)));
    vec2 left,right,back,front;
    if (!causticMap(entry-vec2(radius,0.0),waterPlayer.y,bedPlayer.y,incident,waterIOR,size,left)
        || !causticMap(entry+vec2(radius,0.0),waterPlayer.y,bedPlayer.y,incident,waterIOR,size,right)
        || !causticMap(entry-vec2(0.0,radius),waterPlayer.y,bedPlayer.y,incident,waterIOR,size,back)
        || !causticMap(entry+vec2(0.0,radius),waterPlayer.y,bedPlayer.y,incident,waterIOR,size,front)) return 1.0;
    vec2 columnX=(right-left)/(2.0*radius);
    vec2 columnZ=(front-back)/(2.0*radius);
    float gain=causticAreaGain(columnX,columnZ);
    float deepFade=1.0-smoothstep(8.0,24.0,depth);
    return mix(1.0,gain,clamp(float(WATER_CAUSTICS_STRENGTH),0.0,1.0)*deepFade*resolutionWeight);
#endif
}
// Achromatic callers use the shared water IOR. Dispersive refraction passes
// its own channel's IOR to the full overload, for both light and eye paths.
float waterShadowCausticGain(vec3 waterPlayer, vec3 bedPlayer, vec3 bedNormalWorld,
    vec3 towardLightWorld, float directShare, vec2 footprintX, vec2 footprintY) {
    return waterShadowCausticGain(waterPlayer,bedPlayer,bedNormalWorld,towardLightWorld,
        directShare,footprintX,footprintY,waterParams().refractiveIndex);
}
// Zero-footprint overload is only for the isolated field/transport oracle.
// The production call below passes its explicit analytic camera footprint.
float waterShadowCausticGain(vec3 waterPlayer,vec3 bedPlayer,vec3 bedNormalWorld,
    vec3 towardLightWorld,float directShare) {
    return waterShadowCausticGain(waterPlayer,bedPlayer,bedNormalWorld,towardLightWorld,directShare,vec2(0),vec2(0));
}
#endif
#endif
