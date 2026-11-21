#version 430
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
#include "/lib/water_fft_compute.glsl"
layout(local_size_x=8,local_size_y=8,local_size_z=1) in;
const ivec3 workGroups=ivec3(16,8,1);
layout(rg32f) writeonly uniform image2D waterSpectrumSeed;
layout(rg32f) writeonly uniform image2D waterFftDisplacement;
layout(rg32f) writeonly uniform image2D waterFftPreviousDisplacement;
layout(rgba32f) writeonly uniform image2D waterFftMomentAtlas;
void main(){
    ivec2 atlas=ivec2(gl_GlobalInvocationID.xy);
    if(any(notEqual(imageSize(waterSpectrumSeed),ivec2(128,64)))
       || any(notEqual(imageSize(waterFftDisplacement),ivec2(128,64)))
       || any(notEqual(imageSize(waterFftPreviousDisplacement),ivec2(128,64)))
       || any(notEqual(imageSize(waterFftMomentAtlas),ivec2(2,66)))
       || any(greaterThanEqual(atlas,ivec2(128,64))))return;
    int cascade=atlas.x/64;ivec2 pixel=ivec2(atlas.x&63,atlas.y);
    // Independent CPU normalization targets height RMS .035/.12m before the
    // common artistic strength; one realization need not equal ensemble RMS.
    float scale=cascade==0?25.6407373998:6.3160664518;
    vec2 seed=fftGaussian(pixel,cascade)*scale*sqrt(fftSpectrumShape(pixel,cascade));
    imageStore(waterSpectrumSeed,atlas,vec4(seed,0,1));
    imageStore(waterFftDisplacement,atlas,vec4(0));
    imageStore(waterFftPreviousDisplacement,atlas,vec4(0));
    if(atlas.x<2){
        imageStore(waterFftMomentAtlas,atlas,vec4(0));
        if(atlas.y==0){imageStore(waterFftMomentAtlas,ivec2(atlas.x,64),vec4(0));imageStore(waterFftMomentAtlas,ivec2(atlas.x,65),vec4(0));}
    }
}
#else
layout(local_size_x=1) in;
const ivec3 workGroups=ivec3(1);
void main(){}
#endif
