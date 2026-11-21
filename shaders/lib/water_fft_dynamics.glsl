#ifndef AURORA_WATER_FFT_DYNAMICS_INCLUDED
#define AURORA_WATER_FFT_DYNAMICS_INCLUDED
#include "/lib/water_fft_settings.glsl"
#ifdef AURORA_WATER_FFT_ACTIVE
uniform sampler2D waterFftDisplacementSampler;
uniform sampler2D waterFftPreviousDisplacementSampler;
uniform sampler2D waterFftMomentSampler;
// For the fixed seed spectra the exact sampled-column norm bound is <1.25.
// Scale .5, strength<=1 therefore retains sigma_min(I+dD)>0.375 at all times.
// This is an optical foam material map, never a displacement of Minecraft mesh.
const float WATER_FFT_HORIZONTAL_SCALE=0.5;
bool waterFftState(out vec4 state){
    state=vec4(0);
    if(any(notEqual(textureSize(waterFftMomentSampler,0),ivec2(2,66))))return false;
    state=texelFetch(waterFftMomentSampler,ivec2(0,65),0);
    return !any(isnan(state))&&!any(isinf(state))&&state.z==1.0
        &&state.x==frameTimeCounter&&state.x>=0.0;
}
bool waterFftSampleDisplacement(sampler2D field,vec2 materialXZ,vec2 dx,vec2 dy,
                                out vec2 displacement,out mat2 derivative){
    displacement=vec2(0);derivative=mat2(0);
    if(any(notEqual(textureSize(field,0),ivec2(128,64)))
       ||any(isnan(materialXZ))||any(isinf(materialXZ))
       ||!waterWaveFootprintValid(dx,dy))return false;
    float footprint=max(length(dx),length(dy));
    for(int cascade=0;cascade<2;++cascade){
        float period=cascade==0?16.0:64.0,shortest=cascade==0?1.5:8.0;
        float weight=1.0-smoothstep(.25,.5,footprint/shortest);
        if(weight<=0.0)continue;
        vec2 location=fract(materialXZ/period)*64.0;
        ivec2 first=ivec2(floor(location));vec2 fraction=fract(location);
        vec2 value[4];
        for(int y=0;y<2;++y)for(int x=0;x<2;++x){
            ivec2 p=(first+ivec2(x,y))&ivec2(63);p.x+=cascade*64;
            value[y*2+x]=texelFetch(field,p,0).rg;
            if(any(isnan(value[y*2+x]))||any(isinf(value[y*2+x])))return false;
        }
        displacement+=weight*mix(mix(value[0],value[1],fraction.x),mix(value[2],value[3],fraction.x),fraction.y);
        // Exact derivatives of this SAME four-corner bilinear reconstruction.
        // At a grid boundary floor chooses the cell on its positive side.
        derivative[0]+=weight*(64.0/period)*mix(value[1]-value[0],value[3]-value[2],fraction.y);
        derivative[1]+=weight*(64.0/period)*mix(value[2]-value[0],value[3]-value[1],fraction.x);
    }
    return !any(isnan(displacement))&&!any(isinf(displacement))
        &&all(lessThanEqual(abs(displacement),vec2(2.0)))
        &&!any(isnan(derivative[0]))&&!any(isinf(derivative[0]))
        &&!any(isnan(derivative[1]))&&!any(isinf(derivative[1]))
        &&all(lessThanEqual(abs(derivative[0]),vec2(1.5)))
        &&all(lessThanEqual(abs(derivative[1]),vec2(1.5)));
}
bool waterFftMaterialFlow(vec2 materialXZ,float seconds,float strength,vec2 dx,vec2 dy,
                          out vec2 displacement,out vec2 velocity,out mat2 jacobian,out float area){
    displacement=vec2(0);velocity=vec2(0);jacobian=mat2(1);area=1.0;
    vec4 state;
    if(!waterFftState(state)||isnan(seconds)||isinf(seconds)||seconds<0.0||seconds>3600.0
       ||isnan(strength)||isinf(strength))return false;
    bool previous=seconds!=state.x;
    if(previous){
        float tolerance=2.384185791015625e-7*max(1.0,max(abs(state.x),abs(state.y)));
        float difference=abs(seconds-state.y);difference=min(difference,abs(difference-3600.0));
        if(state.w!=1.0||difference>tolerance)return false;
    }
    mat2 derivative;
    bool valid=previous?waterFftSampleDisplacement(waterFftPreviousDisplacementSampler,materialXZ,dx,dy,displacement,derivative)
                       :waterFftSampleDisplacement(waterFftDisplacementSampler,materialXZ,dx,dy,displacement,derivative);
    if(!valid)return false;
    float scale=WATER_FFT_HORIZONTAL_SCALE*clamp(strength,0.0,1.0);
    vec2 selectedRaw=displacement;
    jacobian=mat2(1)+scale*derivative;displacement*=scale;area=determinant(jacobian);
    if(isnan(area)||isinf(area)||area<=.1||area>4.0)return false;
    // Actual interval-mean material velocity from the two stored fields; it is
    // not an invented current or an instantaneous analytic time derivative.
    float elapsed=state.x-state.y;if(elapsed<0.0)elapsed+=3600.0;
    if(state.w==1.0&&elapsed>0.0&&elapsed<=.1){
        vec2 other;mat2 unused;
        bool history=previous?waterFftSampleDisplacement(waterFftDisplacementSampler,materialXZ,dx,dy,other,unused)
                             :waterFftSampleDisplacement(waterFftPreviousDisplacementSampler,materialXZ,dx,dy,other,unused);
        if(history)velocity=scale*(previous?other-selectedRaw:selectedRaw-other)/elapsed;
    }
    return !any(isnan(velocity))&&!any(isinf(velocity));
}
float waterFftMissingSlopeVariance(vec3 playerPosition,vec2 dx,vec2 dy,float strength){
    vec4 state;
    if(!waterFftState(state)||!waterWaveFootprintValid(dx,dy)
       ||any(isnan(playerPosition))||any(isinf(playerPosition))
       ||any(isnan(cameraPositionFract.xz))||any(isinf(cameraPositionFract.xz))
       ||isnan(strength)||isinf(strength))return 0.0;
    vec2 anchor=vec2(uvec2(cameraPositionInt.xz)&uvec2(127u));
    vec2 world=mod(anchor+cameraPositionFract.xz+playerPosition.xz,128.0);
    float footprint=max(length(dx),length(dy)),missing=0.0;
    for(int cascade=0;cascade<2;++cascade){
        vec4 moments=texelFetch(waterFftMomentSampler,ivec2(cascade,64),0);
        if(any(isnan(moments))||any(isinf(moments))||moments.x<=0.0||moments.x>.1
           ||any(lessThan(moments,vec4(0)))||any(greaterThan(moments.yz,vec2(2.0*moments.x)))
           ||moments.w>4.0*moments.x)return 0.0;
        float period=cascade==0?16.0:64.0,shortest=cascade==0?1.5:8.0;
        vec2 fraction=fract(fract(world/period)*64.0);
        vec2 t=2.0*fraction*(1.0-fraction);
        float retained=clamp(moments.x-t.x*moments.y-t.y*moments.z+t.x*t.y*moments.w,0.0,moments.x);
        float weight=1.0-smoothstep(.25,.5,footprint/shortest);
        missing+=moments.x-weight*weight*retained;
    }
    // Measured, untruncated spectrum; the normal's .12 artistic slope cap is
    // nonlinear. This is global missing power, not local/clamp-corrected variance.
    float scale=clamp(strength,0.0,1.0);
    return max(0.0,missing)*scale*scale;
}
#endif
#endif
