#version 430
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
layout(local_size_x=64,local_size_y=1,local_size_z=1) in;
const ivec3 workGroups=ivec3(2,1,1);
layout(rgba32f) uniform image2D waterFftMomentAtlas;
uniform float frameTimeCounter;
shared vec4 rowMoments[64];
void main(){
    if(any(notEqual(imageSize(waterFftMomentAtlas),ivec2(2,66))))return;
    int lane=int(gl_LocalInvocationID.x),cascade=int(gl_WorkGroupID.x);
    rowMoments[lane]=imageLoad(waterFftMomentAtlas,ivec2(cascade,lane));barrier();
    for(int offset=32;offset>0;offset/=2){if(lane<offset)rowMoments[lane]+=rowMoments[lane+offset];barrier();}
    if(lane==0){
        imageStore(waterFftMomentAtlas,ivec2(cascade,64),rowMoments[0]);
        if(cascade==0){
            vec4 old=imageLoad(waterFftMomentAtlas,ivec2(0,65));
            bool valid=!isnan(frameTimeCounter)&&!isinf(frameTimeCounter)&&frameTimeCounter>=0.0;
            imageStore(waterFftMomentAtlas,ivec2(0,65),vec4(valid?frameTimeCounter:0.0,old.x,valid?1.0:0.0,old.z));
        }
    }
}
#else
layout(local_size_x=1) in;
const ivec3 workGroups=ivec3(1);
void main(){}
#endif
