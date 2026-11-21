#ifndef AURORA_WATER_FFT_COMPUTE_INCLUDED
#define AURORA_WATER_FFT_COMPUTE_INCLUDED
const float WATER_FFT_TAU=6.283185307179586;
vec2 fftComplexMultiply(vec2 a,vec2 b){return vec2(a.x*b.x-a.y*b.y,a.x*b.y+a.y*b.x);}
vec4 fftComplexMultiply2(vec4 a,vec2 b){return vec4(fftComplexMultiply(a.xy,b),fftComplexMultiply(a.zw,b));}
vec2 fftWaveVector(ivec2 pixel,int cascade){
    ivec2 mode=ivec2(pixel.x<32?pixel.x:pixel.x-64,pixel.y<32?pixel.y:pixel.y-64);
    return vec2(mode)*(WATER_FFT_TAU/(cascade==0?16.0:64.0));
}
uint fftHash(uint v){v^=v>>16u;v*=0x7feb352du;v^=v>>15u;v*=0x846ca68bu;v^=v>>16u;return v;}
vec2 fftGaussian(ivec2 pixel,int cascade){
    uint seed=uint(pixel.x+64*pixel.y+cascade*4096)+0xa511e9b3u;
    float u=max(float(fftHash(seed)>>8u)/16777216.0,1.0/16777216.0);
    float angle=WATER_FFT_TAU*float(fftHash(seed^0x63d83595u)>>8u)/16777216.0;
    return sqrt(-2.0*log(u))*vec2(cos(angle),sin(angle));
}
float fftSpectrumShape(ivec2 pixel,int cascade){
    vec2 wave=fftWaveVector(pixel,cascade);float k=length(wave);
    if(k==0.0 || pixel.x==32 || pixel.y==32)return 0.0;
    float low=WATER_FFT_TAU/(cascade==0?8.0:32.0);
    float high=WATER_FFT_TAU/(cascade==0?1.5:8.0);
    float band=smoothstep(low,low*1.2,k)*(1.0-smoothstep(high*.8,high,k));
    if(band==0.0)return 0.0;
    float alignment=dot(wave/k,vec2(.8,.6));float windLength=64.0/9.81;
    return band*exp(-1.0/(k*k*windLength*windLength))*alignment*alignment
        /(k*k*k*k)*exp(-k*k*.0144)*(alignment>=0.0?1.0:.25);
}
#endif
