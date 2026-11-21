#version 330 compatibility
#include "/lib/water_interaction_settings.glsl"
#ifdef AURORA_WATER_INTERACTIONS
/* RENDERTARGETS: 15 */
/*
const int colortex15Format = RGBA32F;
*/
const bool colortex15Clear = false;
uniform sampler2D colortex15;
uniform vec3 relativeEyePosition;
uniform vec3 relativeVehiclePosition;
uniform bool isSpectator;
uniform bool feetInWater;
uniform bool isRiding;
uniform bool vehicleInWater;
uniform ivec3 cameraPositionInt,previousCameraPositionInt;
uniform vec3 cameraPositionFract,previousCameraPositionFract;
uniform float frameTime;
uniform int frameCounter;
#else
/* RENDERTARGETS: 0 */
#endif
layout(location=0) out vec4 state;
void main() {
    state=vec4(0.0);
#ifdef AURORA_WATER_INTERACTIONS
    ivec2 p=ivec2(gl_FragCoord.xy);
    if (any(notEqual(textureSize(colortex15,0),ivec2(16,2)))) return;
    int kind=isSpectator ? 0 : (isRiding ? (vehicleInWater ? 2 : 0) : (feetInWater ? 1 : 0));
    // Installed Iris returns camera minus vehicle/head; convert to camera-relative.
    vec3 center=kind==2 ? -relativeVehiclePosition : -relativeEyePosition;
    if (any(isnan(center)) || any(isinf(center)) || dot(center,center)>1600.0) kind=0;
    if (kind==0) center=vec3(0.0);
    vec4 old=texelFetch(colortex15,ivec2(0,0),0);
    vec4 clock=texelFetch(colortex15,ivec2(0,1),0);
    // Bounds check integer motion before rebuilding the small fractional delta.
    ivec3 cells=cameraPositionInt-previousCameraPositionInt;
    vec3 delta=vec3(cells)+cameraPositionFract-previousCameraPositionFract;
    bool consecutive=frameCounter>0 && clock.x==float(frameCounter) && frameTime>0.0 && frameTime<=0.125
        && all(lessThanEqual(abs(cells),ivec3(16))) && dot(delta,delta)<256.0
        && clock.y>=0.0 && clock.y<0.10001;
    float accumulated=consecutive ? clock.y+frameTime : 0.0;
    vec2 velocity=vec2(0.0);
    if (consecutive && old.w==float(kind) && kind>0)
        velocity=(center.xz-old.xz+delta.xz)/frameTime;
    float speed=length(velocity);
    bool tick=accumulated>=0.1;
    bool emit=tick && speed>0.20 && speed<=18.0;
    if (p.x==0) {
        state=p.y==0 ? vec4(center,float(kind))
            : vec4(float(frameCounter+1),mod(accumulated,0.1),0.0,0.0);
        return;
    }
    if (!consecutive) return;
    if (tick && p.x==1) {
        if (emit) state=p.y==0 ? vec4(center,0.0)
            : vec4(velocity,float(kind),smoothstep(0.20,kind==2 ? 4.0 : 1.8,speed));
        return;
    }
    ivec2 previous=ivec2(p.x-(tick?1:0),0);
    vec4 world=texelFetch(colortex15,previous,0);
    vec4 motion=texelFetch(colortex15,previous+ivec2(0,1),0);
    if (motion.z<1.0 || motion.w<=0.0 || world.w+frameTime>=1.5) return;
    state=p.y==0 ? vec4(world.xyz-delta,world.w+frameTime) : motion;
#endif
}
