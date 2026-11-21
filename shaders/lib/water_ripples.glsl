#ifndef AURORA_WATER_RIPPLES_INCLUDED
#define AURORA_WATER_RIPPLES_INCLUDED
uniform sampler2D colortex15;
uniform int biome_precipitation;

// Bounded, deterministic radial wave train, with analytic d(height)/dr.
// A finite packet has a smooth leading/trailing edge and no singular center.
vec2 waterRipplePacket(vec2 offset, float radius, float width, float amplitude, float wavelength) {
    float r=length(offset);
    float u=(r-radius)/width;
    if(abs(u)>=1.0 || r<0.002) return vec2(0.0);
    float phase=6.2831853*(r-radius)/wavelength;
    float a=1.0-u*u;
    float dr=amplitude*(a*a*(6.2831853/wavelength)*cos(phase)
                      -4.0*a*u/width*sin(phase));
    return offset/r*dr*smoothstep(0.002,0.035,r);
}
uint waterDropHash(uvec2 p,uint epoch) {
    uint h=p.x*0x8da6b343u ^ p.y*0xd8163841u ^ epoch*0xcb1ab31fu;
    h^=h>>16u;
    h*=0x7feb352du;
    h^=h>>15u;
    return h;
}
float waterDropRandom(uint h) {return float(h>>8u)*(1.0/16777216.0);}
vec2 waterRainSlope(vec3 player, vec2 dx, vec2 dy, float skyLevel) {
    if(biome_precipitation!=1 || !(rainStrength>0.0) || skyLevel<0.98) return vec2(0.0);
    float detailWeight=1.0-smoothstep(0.0225,0.045,max(length(dx),length(dy)));
    if(detailWeight<=0.0) return vec2(0.0);
    // Compute the cell in integer world space, and its fraction in local space.
    // Wrapping the epoch after 3600 seconds matches Iris's clock.
    vec2 local=cameraPositionFract.xz+player.xz;
    ivec2 base=cameraPositionInt.xz+ivec2(floor(local));
    vec2 frac=fract(local);
    vec2 gradient=vec2(0.0);
    for(int y=-1;y<=1;++y) for(int x=-1;x<=1;++x) {
        ivec2 d=ivec2(x,y);
        uvec2 cell=uvec2(base+d);
        float offset=waterDropRandom(waterDropHash(cell,3u));
        float time=mod(frameTimeCounter,3600.0)+offset;
        uint epoch=uint(floor(time))%3600u;
        float age=fract(time);
        if(age>=0.78) continue;
        uint h=waterDropHash(cell,epoch);
        if(waterDropRandom(h)>clamp(rainStrength,0.0,1.0)) continue;
        vec2 center=vec2(waterDropRandom(waterDropHash(cell,epoch+4213u)),
                         waterDropRandom(waterDropHash(cell,epoch+6299u)));
        float fade=smoothstep(0.0,0.10,age)*(1.0-smoothstep(0.35,0.78,age));
        gradient+=waterRipplePacket(frac-vec2(d)-center,0.05+0.65*age,
                                    0.095,0.0032*fade,0.09);
    }
    return gradient*detailWeight*smoothstep(0.98,1.0,skyLevel)*sqrt(clamp(rainStrength,0.0,1.0));
}
vec2 waterContactSlope(vec3 player,vec2 dx,vec2 dy) {
    if(any(notEqual(textureSize(colortex15,0),ivec2(16,2)))) return vec2(0.0);
    float detailWeight=1.0-smoothstep(.065,.13,max(length(dx),length(dy)));
    if(detailWeight<=0.0) return vec2(0.0);
    vec2 gradient=vec2(0.0);
    for(int i=1;i<16;++i) {
        vec4 p=texelFetch(colortex15,ivec2(i,0),0);
        vec4 motion=texelFetch(colortex15,ivec2(i,1),0);
        if(!(motion.z==1.0 || motion.z==2.0) || !(motion.w>0.0 && motion.w<=1.0)
           || !(p.w>=0.0 && p.w<1.5)) continue;
        vec3 d=player-p.xyz;
        bool boat=motion.z==2.0;
        if(boat ? abs(d.y)>0.85 : (d.y< -2.15 || d.y>0.12)) continue;
        float radius=(boat?0.48:0.16)+p.w*(boat?1.25:0.9);
        float fade=smoothstep(0.0,0.10,p.w)*(1.0-smoothstep(.3,1.5,p.w));
        float amp=(boat?.0045:.0032)*motion.w*fade;
        gradient+=waterRipplePacket(d.xz,radius,boat?.35:.21,amp,boat?.43:.26);
    }
    return gradient*detailWeight;
}
vec3 waterInteractiveNormal(vec3 base,vec3 view,vec2 dx,vec2 dy,float sky) {
    vec3 player=viewToPlayerPosition(view);
    if(any(isnan(player)) || any(isinf(player)) || !waterWaveFootprintValid(dx,dy)
       || isnan(frameTimeCounter) || isinf(frameTimeCounter)) return base;
    vec2 slope=waterRainSlope(player,dx,dy,sky)+waterContactSlope(player,dx,dy);
    if(all(equal(slope,vec2(0.0)))) return base;
    mat3 transform=transpose(mat3(gbufferModelViewInverse));
    float scale=length(transform*vec3(0,1,0));
    return scale>1e-6 ? celestialUnit(base-transform*vec3(slope.x,0,slope.y)/scale) : base;
}
#endif
