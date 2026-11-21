#version 430
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
#include "/lib/water_fft_compute.glsl"
layout(local_size_x=64,local_size_y=1,local_size_z=1) in;
const ivec3 workGroups=ivec3(2,64,1);
layout(rgba32f) readonly uniform image2D waterFftRows;
layout(rgba32f) writeonly uniform image2D waterFftOutput;
layout(rg32f) readonly uniform image2D waterFftDisplacementRows;
layout(rg32f) uniform image2D waterFftDisplacement;
layout(rg32f) writeonly uniform image2D waterFftPreviousDisplacement;
shared vec4 fftValues[64];
shared vec2 fftDisplacement[64];
void main(){
    if(any(notEqual(imageSize(waterFftRows),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftOutput),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftDisplacementRows),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftDisplacement),ivec2(128,64)))
        || any(notEqual(imageSize(waterFftPreviousDisplacement),ivec2(128,64))))return;
    int lane=int(gl_LocalInvocationID.x),cascade=int(gl_WorkGroupID.x),column=int(gl_WorkGroupID.y);
    int source=int(bitfieldReverse(uint(lane))>>26u);
    fftValues[lane]=imageLoad(waterFftRows,ivec2(column+64*cascade,source));
    fftDisplacement[lane]=imageLoad(waterFftDisplacementRows,ivec2(column+64*cascade,source)).xy;barrier();
    for(int span=2;span<=64;span*=2){
        int halfSpan=span/2,index=lane%halfSpan,first=(lane/span)*span+index;
        float theta=WATER_FFT_TAU*float(index)/float(span);
        vec4 left=fftValues[first],right=fftComplexMultiply2(fftValues[first+halfSpan],vec2(cos(theta),sin(theta)));
        vec4 value=lane%span<halfSpan?left+right:left-right;
        vec2 dleft=fftDisplacement[first],dright=fftComplexMultiply(fftDisplacement[first+halfSpan],vec2(cos(theta),sin(theta)));
        vec2 dvalue=lane%span<halfSpan?dleft+dright:dleft-dright;
        barrier();fftValues[lane]=value;fftDisplacement[lane]=dvalue;barrier();
    }
    vec4 spatial=fftValues[lane]/64.0;
    // Height plus analytic horizontal derivatives; height is NOT displaced yet.
    imageStore(waterFftOutput,ivec2(column+64*cascade,lane),vec4(spatial.x,spatial.zw,1.0));
    // Each texel has one writer. Preserve that texel's previous displacement
    // before overwriting it; no invocation ever reads a neighbor's changing data.
    ivec2 target=ivec2(column+64*cascade,lane);
    vec2 previous=imageLoad(waterFftDisplacement,target).xy;
    imageStore(waterFftPreviousDisplacement,target,vec4(previous,0,1));
    imageStore(waterFftDisplacement,target,vec4(fftDisplacement[lane]/64.0,0,1));
}
#else
layout(local_size_x=1) in;
const ivec3 workGroups=ivec3(1);
void main(){}
#endif
