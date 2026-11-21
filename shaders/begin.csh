#version 430
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
#include "/lib/water_fft_compute.glsl"
layout(local_size_x=64,local_size_y=1,local_size_z=1) in;
const ivec3 workGroups=ivec3(2,64,1);
layout(rg32f) readonly uniform image2D waterSpectrumSeed;
layout(rgba32f) writeonly uniform image2D waterFftRows;
layout(rg32f) writeonly uniform image2D waterFftDisplacementRows;
layout(rgba32f) writeonly uniform image2D waterFftMomentAtlas;
uniform float frameTimeCounter;
shared vec4 fftValues[64];
shared vec2 fftDisplacement[64];
void main(){
    if(any(notEqual(imageSize(waterSpectrumSeed),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftRows),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftDisplacementRows),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftMomentAtlas),ivec2(2,66))))return;
    int lane=int(gl_LocalInvocationID.x),cascade=int(gl_WorkGroupID.x),row=int(gl_WorkGroupID.y);
    int source=int(bitfieldReverse(uint(lane))>>26u);ivec2 p=ivec2(source,row);
    ivec2 offset=ivec2(cascade*64,0),opposite=ivec2((-source)&63,(-row)&63);
    vec2 a=imageLoad(waterSpectrumSeed,p+offset).xy;
    vec2 b=imageLoad(waterSpectrumSeed,opposite+offset).xy;b.y=-b.y;
    vec2 wave=fftWaveVector(p,cascade);
    // Quantized deep-water dispersion deliberately closes every600 seconds.
    // Allowed legacy speeds also close at Iris's3600-second time reset.
    float harmonic=floor(sqrt(9.81*length(wave))*600.0/WATER_FFT_TAU+.5);
    float seconds=isnan(frameTimeCounter)||isinf(frameTimeCounter)?0.0:max(frameTimeCounter,0.0);
    float cycle=mod(seconds*float(WATER_WAVE_SPEED),600.0)/600.0;
    float angle=WATER_FFT_TAU*fract(cycle*harmonic);
    vec2 phase=vec2(cos(angle),sin(angle));
    vec2 height=fftComplexMultiply(a,phase)+fftComplexMultiply(b,vec2(phase.x,-phase.y));
    vec2 slopeX=vec2(-wave.x*height.y,wave.x*height.x);
    vec2 slopeZ=vec2(-wave.y*height.y,wave.y*height.x);
    // D(k)=+i*k/|k|*H compresses a sinusoid at its crest. Its actual sampled
    // Jacobian is derived later from the SAME four bilinear displacement taps.
    vec2 displacementX=length(wave)>0.0?slopeX/length(wave):vec2(0);
    vec2 displacementZ=length(wave)>0.0?slopeZ/length(wave):vec2(0);
    fftDisplacement[lane]=displacementX+vec2(-displacementZ.y,displacementZ.x);
    float energy=dot(wave,wave)*dot(height,height)/16777216.0;
    vec2 attenuation=vec2(1)-cos(WATER_FFT_TAU*vec2(p)/64.0);
    vec4 moment=energy*vec4(1,attenuation,attenuation.x*attenuation.y);
    fftValues[lane]=vec4(height,slopeX+vec2(-slopeZ.y,slopeZ.x));barrier();
    for(int span=2;span<=64;span*=2){
        int halfSpan=span/2,index=lane%halfSpan,first=(lane/span)*span+index;
        float theta=WATER_FFT_TAU*float(index)/float(span);
        vec4 left=fftValues[first],right=fftComplexMultiply2(fftValues[first+halfSpan],vec2(cos(theta),sin(theta)));
        vec4 value=lane%span<halfSpan?left+right:left-right;
        vec2 dleft=fftDisplacement[first],dright=fftComplexMultiply(fftDisplacement[first+halfSpan],vec2(cos(theta),sin(theta)));
        vec2 dvalue=lane%span<halfSpan?dleft+dright:dleft-dright;
        barrier();fftValues[lane]=value;fftDisplacement[lane]=dvalue;barrier();
    }
    imageStore(waterFftRows,ivec2(lane+64*cascade,row),fftValues[lane]/64.0);
    imageStore(waterFftDisplacementRows,ivec2(lane+64*cascade,row),vec4(fftDisplacement[lane]/64.0,0,1));
    barrier();fftValues[lane]=moment;barrier();
    for(int offset=32;offset>0;offset/=2){if(lane<offset)fftValues[lane]+=fftValues[lane+offset];barrier();}
    if(lane==0)imageStore(waterFftMomentAtlas,ivec2(cascade,row),fftValues[0]);
}
#else
layout(local_size_x=1) in;
const ivec3 workGroups=ivec3(1);
void main(){}
#endif
