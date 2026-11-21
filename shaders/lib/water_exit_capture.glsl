#ifndef AURORA_WATER_EXIT_CAPTURE_INCLUDED
#define AURORA_WATER_EXIT_CAPTURE_INCLUDED
#include "/lib/water_underwater_settings.glsl"
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
// Reuses 7/8: byte1 in 8.a identifies an EXIT, while 8.r remains the exact
// additive layer/blocker counter. M1/M3A/M5 continue to reject nonzero 8.a.
void captureWaterExitSurface(vec3 viewPosition,vec3 normalView,vec2 lightmapUV,
    vec2 worldDx,vec2 worldDy,int waterSurface,float interfaceHeight,ivec4 blendState,vec4 nativeScene,
    float windowDepth,inout vec4 surface,inout vec4 ownership) {
    if(isnan(blindness)||isinf(blindness)||isnan(darknessFactor)||isinf(darknessFactor)
       ||blindness>0.0||darknessFactor>0.0)return;
    if(isnan(interfaceHeight)||isinf(interfaceHeight)||interfaceHeight<=.0625||interfaceHeight>1.016)return;
    if(isEyeInWater!=1||!hasSkylight||hasCeiling||waterSurface!=1||!waterOpticsSurfaceBlend(blendState))return;
    if(any(isnan(nativeScene))||any(isinf(nativeScene))||any(lessThan(nativeScene.rgb,vec3(0)))
       ||any(greaterThan(nativeScene.rgb,vec3(65504)))||nativeScene.a<=0.0||nativeScene.a>1.0
       ||isnan(windowDepth)||isinf(windowDepth)||windowDepth<0.0||windowDepth>=1.0
       ||any(isnan(viewPosition))||any(isinf(viewPosition))||any(isnan(normalView))||any(isinf(normalView))
       ||any(isnan(upPosition))||any(isinf(upPosition))||any(isnan(lightmapUV))||any(isinf(lightmapUV)))return;
    if(max(max(abs(normalView.x),abs(normalView.y)),abs(normalView.z))<=1e-6
       ||max(max(abs(upPosition.x),abs(upPosition.y)),abs(upPosition.z))<=1e-6
       ||max(max(abs(viewPosition.x),abs(viewPosition.y)),abs(viewPosition.z))<=1e-6)return;
    vec3 normal=celestialUnit(normalView),up=celestialUnit(upPosition);
    // Sodium reverses the top quad for its underside; Iris recomputes that
    // reversed normal. Height evidence above excludes a real bottom face first.
    if(abs(dot(normal,up))<.95)return;
    if(dot(normal,up)<0.0)normal=-normal;
    if(dot(normal,celestialUnit(-viewPosition))>=-.03)return;
    normal=waterFilteredWaveNormal(normal,viewPosition,1.0,worldDx,worldDy);
    if(any(isnan(normal))||any(isinf(normal))||abs(dot(normal,normal)-1.0)>.001)return;
    vec2 levels=clamp((lightmapUV-vec2(.5/16.0))*(16.0/15.0),0.0,1.0);
    surface=vec4(normal,windowDepth);
    ownership=vec4(1.0/255.0,levels,1.0/255.0);
}
#endif
#endif
