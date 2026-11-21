#ifndef AURORA_WATER_GLINT_MODEL_INCLUDED
#define AURORA_WATER_GLINT_MODEL_INCLUDED
#include "/lib/water_filtered_waves.glsl"

// An isotropic Beckmann slope distribution has E[|slope|^2]=alpha^2.
// Use the missing mean slope variance of the six filtered height modes.
float waterUnresolvedSlopeVariance(vec2 dx,vec2 dy,float strength) {
    const vec2 k[6]=vec2[6](vec2(11,3),vec2(4,-9),vec2(7,13),vec2(49,19),vec2(-83,31),vec2(151,97));
    const float a[6]=float[6](.06,.04,.03,.006,.0035,.0015);
    float variance=0.0;
    for(int i=0;i<6;++i) {
        float weight=waterWavePixelFilter(k[i],dx,dy);
        vec2 rms=a[i]*(6.2831853/128.0)*k[i];
        variance+=0.5*dot(rms,rms)*(1.0-weight*weight);
    }
    return variance*strength*strength;
}
float waterBeckmannMask(float cosine,float roughness) {
    float a=cosine/(roughness*sqrt(max(1.0-cosine*cosine,1e-10)));
    if(a>=1.6) return 1.0;
    return a*(3.535+2.181*a)/(1.0+a*(2.276+2.577*a));
}
float waterGlintBRDF(vec3 n,vec3 v,vec3 l,float alpha2,float ior) {
    float nv=dot(n,v),nl=dot(n,l);
    if(nv<=1e-5 || nl<=1e-5 || !(alpha2>=0.001 && alpha2<=1.0)) return 0.0;
    vec3 h=normalize(v+l);
    float nh=dot(n,h),vh=clamp(dot(v,h),0.0,1.0);
    if(nh<=0.001) return 0.0;
    float nh2=nh*nh;
    float exponent=(1.0-nh2)/(alpha2*nh2);
    if(exponent>22.0) return 0.0;
    float distribution=exp(-max(0.0,exponent))/(3.14159265*alpha2*nh2*nh2);
    float ct=sqrt(max(0.0,1.0-(1.0-vh*vh)/(ior*ior)));
    float rs=(vh-ior*ct)/(vh+ior*ct);
    float rp=(ior*vh-ct)/(ior*vh+ct);
    float fresnel=.5*(rs*rs+rp*rp);
    float roughness=sqrt(alpha2);
    return fresnel*distribution*waterBeckmannMask(nv,roughness)*waterBeckmannMask(nl,roughness)
           /(4.0*nv*nl);
}
#endif
