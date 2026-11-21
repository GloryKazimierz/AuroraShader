#ifndef AURORA_WATER_FFT_SAMPLE_INCLUDED
#define AURORA_WATER_FFT_SAMPLE_INCLUDED
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
uniform sampler2D waterFftOutputSampler;
bool waterFftGradient(vec2 tile,vec2 worldDx,vec2 worldDy,out vec2 gradient){
    gradient=vec2(0.0);
    if(any(isnan(tile))||any(isinf(tile))||!waterWaveFootprintValid(worldDx,worldDy))return false;
    if(any(notEqual(textureSize(waterFftOutputSampler,0),ivec2(128,64))))return false;
    float footprint=max(length(worldDx),length(worldDy));
    for(int cascade=0;cascade<2;++cascade){
        float period=cascade==0?16.0:64.0,shortest=cascade==0?1.5:8.0;
        float weight=1.0-smoothstep(.25,.5,footprint/shortest);
        if(weight<=0.0)continue;
        // Both periods divide the existing integer-anchored128-block tile.
        // Wrap each cascade manually: sampler filtering must not cross its atlas seam.
        vec2 location=fract(tile*(128.0/period))*64.0;
        ivec2 first=ivec2(floor(location));vec2 fraction=fract(location);
        vec2 slope=vec2(0.0);
        for(int y=0;y<2;++y)for(int x=0;x<2;++x){
            ivec2 pixel=(first+ivec2(x,y))&ivec2(63);pixel.x+=cascade*64;
            vec4 value=texelFetch(waterFftOutputSampler,pixel,0);
            if(any(isnan(value))||any(isinf(value))||value.a!=1.0)return false;
            vec2 factors=mix(vec2(1.0)-fraction,fraction,vec2(x,y));
            slope+=value.gb*factors.x*factors.y;
        }
        gradient+=slope*weight;
    }
    // Bounded artistic normal amplitude preserves the existing top-water and
    // compact shadow-slope eligibility. This is not vertex displacement/flow.
    float magnitude=length(gradient);
    if(isnan(magnitude)||isinf(magnitude))return false;
    if(magnitude>.12)gradient*=.12/magnitude;
    return true;
}
#endif
#endif
