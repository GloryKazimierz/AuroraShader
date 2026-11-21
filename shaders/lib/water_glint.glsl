#ifndef AURORA_WATER_GLINT_INCLUDED
#define AURORA_WATER_GLINT_INCLUDED
#include "/lib/water_optics_settings.glsl"
#define WATER_CELESTIAL_GLINT 0 // [0 1]
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_CELESTIAL_GLINT == 1
#define AURORA_WATER_GLINT_ACTIVE
#include "/lib/water_glint_model.glsl"
#include "/lib/water_interface_lighting.glsl"
uniform int moonPhase;
vec3 applyWaterGlint(vec3 scene,ivec2 pixel,ivec2 size) {
    if(any(notEqual(textureSize(colortex7,0),size)) || any(notEqual(textureSize(colortex8,0),size))
       || any(notEqual(textureSize(depthtex0,0),size))) return scene;
    vec4 surface=texelFetch(colortex7,pixel,0),owner=texelFetch(colortex8,pixel,0);
    float z=texelFetch(depthtex0,pixel,0).r;
    if(!waterTraceFinite4(surface) || !waterTraceFinite4(owner) || !(z>=0.0 && z<1.0)
        || !(surface.a>=0.0 && surface.a<1.0) || abs(z-surface.a)>1.0/16777215.0
        || abs(dot(surface.xyz,surface.xyz)-1.0)>.001 || abs(owner.r*255.0-1.0)>.002
        || owner.a!=0.0 || owner.b<.05 || owner.b>1.0 || !waterResolveScalar(rainStrength)) return scene;
    vec3 point;
    if(!waterTraceUnproject(pixel,surface.a,size,point))return scene;
    vec3 n=surface.xyz,v=celestialUnit(-point),up=celestialUnit(upPosition);
    if(!waterTraceFinite3(shadowLightPosition) || dot(shadowLightPosition,shadowLightPosition)<1e-8) return scene;
    vec3 l=celestialUnit(shadowLightPosition);
    float env=celestialEnvironmentWeight(), nl=dot(n,l),nv=dot(n,v),alt=dot(up,l);
    if(env<=0.0 || nl<=0.0 || nv<=0.0 || alt<=.01) return scene;
    float nh=dot(n,celestialUnit(v+l));
    // Even the widest calibrated lobe is negligible outside this range.
    if(nh<=.70) return scene;
    vec2 dx,dy;
    if(!waterInterfaceFootprint(pixel,size,viewToPlayerPosition(point),dx,dy)) return scene;
    float roughness=mix(.060,.135,clamp(rainStrength,0.0,1.0));
    float alpha2=roughness*roughness;
#if WATER_WAVES == 1 && WATER_SURFACE_DETAIL == 1
    alpha2+=waterUnresolvedSlopeVariance(dx,dy,float(WATER_WAVE_STRENGTH));
#endif
    float brdf=waterGlintBRDF(n,v,l,alpha2,waterParams().refractiveIndex);
    if(brdf<=0.0)return scene;
    float visible=waterInterfaceVisibility(point,n,l);
    if(visible<=0.0)return scene;
    bool moon=dot(l,celestialUnit(sunPosition))<0.0;
    float lunar=.5+.5*cos(6.2831853*float(clamp(moonPhase,0,7))/8.0);
    vec3 light=moon?vec3(.045,.064,.105)*lunar
                   :mix(vec3(1.50,.57,.20),vec3(1.10,1.04,.92),smoothstep(.04,.50,alt));
    float exposure=nl*brdf*visible*smoothstep(.05,.8,owner.b)*env*smoothstep(.01,.12,alt)
                  *(1.0-.92*clamp(rainStrength,0.0,1.0));
#if FOG_ENABLED != 0
    exposure*=fogTransmission(point);
#endif
    vec3 color=scene+exposure*light;
    return waterTraceFinite3(color) && all(lessThanEqual(color,vec3(65504.0))) ? color : scene;
}
#endif
#endif
#endif
