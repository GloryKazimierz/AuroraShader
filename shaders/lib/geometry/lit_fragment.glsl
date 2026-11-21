// M8 keeps baked Minecraft shading, then converts RGB for scene composition.
#include "/lib/water_optics_capture.glsl"
#include "/lib/scene_color.glsl"
#ifdef APPLY_LATE_FOG
#include "/lib/fog.glsl"
#endif
#ifdef APPLY_WATER_STYLE
#include "/lib/water.glsl"
#include "/lib/water_debug_capture.glsl"
#include "/lib/water_interaction_settings.glsl"
#ifdef AURORA_WATER_INTERACTIONS
#include "/lib/water_ripples.glsl"
#endif
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_FLOW == 1 && WATER_SURFACE_DETAIL == 1 && WATER_WAVES == 1
#define AURORA_WATER_FLOW_ACTIVE
#include "/lib/water_flow.glsl"
#endif
#endif
flat in int waterSurface;
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
in float waterInterfaceHeight;
#endif
#ifndef WRITE_SURFACE_DATA
in vec3 normalView;
#endif
#endif

uniform sampler2D lightmap;
uniform sampler2D gtexture;

uniform float alphaTestRef = 0.1;

in vec2 lmcoord;
in vec2 texcoord;
in vec4 glcolor;

#ifdef WRITE_SURFACE_DATA
#include "/lib/gbuffer_write.glsl"
#else
#ifdef AURORA_WATER_OPTICS_ACTIVE
#ifdef APPLY_WATER_STYLE
/* RENDERTARGETS: 0,7,8 */
layout(location = 1) out vec4 waterOpticsSurface;
layout(location = 2) out vec4 waterOpticsOwnership;
#else
/* RENDERTARGETS: 0,8 */
layout(location = 1) out vec4 waterOpticsOwnership;
#endif
layout(location = 0) out vec4 color;
#else
#ifdef AURORA_WATER_DEBUG_CAPTURE
/* RENDERTARGETS: 0,7 */
layout(location = 0) out vec4 color;
layout(location = 1) out vec4 waterDebugSurface;
#else
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
#endif
#endif
#endif

void main() {
#ifdef APPLY_WATER_STYLE
    vec2 waterWorldDx = vec2(0.0);
    vec2 waterWorldDy = vec2(0.0);
#if WATER_SURFACE_DETAIL == 1
#define AURORA_WATER_CONTINUOUS_VIEW
    // Derivatives require continuous coordinates and uniform control flow. Do
    // this before alpha discard and every material/environment/reflection gate.
    vec2 waterScreenUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 waterViewPosition = reconstructViewPosition(waterScreenUV, gl_FragCoord.z);
#ifdef AURORA_WATER_FLOW_ACTIVE
    vec3 flowDx = mat3(gbufferModelViewInverse) * dFdx(waterViewPosition);
    vec3 flowDy = mat3(gbufferModelViewInverse) * dFdy(waterViewPosition);
    waterWorldDx = flowDx.xz;
    waterWorldDy = flowDy.xz;
#else
    waterWorldDx = (mat3(gbufferModelViewInverse) * dFdx(waterViewPosition)).xz;
    waterWorldDy = (mat3(gbufferModelViewInverse) * dFdy(waterViewPosition)).xz;
#endif
#endif
#endif
	color = texture(gtexture, texcoord) * glcolor;
	color *= texture(lightmap, lmcoord);
	if (color.a < alphaTestRef) {
		discard;
	}
    // RGB only: alpha coverage, discard and surface-data attachments stay unchanged.
    color.rgb = sceneFromDisplay(color.rgb);
#ifdef AURORA_WATER_OPTICS_ACTIVE
#ifndef WRITE_SURFACE_DATA
    waterOpticsOwnership = vec4(1.0, 0.0, 0.0, 0.0);
#endif
#endif
#ifdef APPLY_LATE_FOG
    // Reconstruct this foreground fragment, not the already composed background.
#ifdef AURORA_WATER_CONTINUOUS_VIEW
    vec3 fogView = waterViewPosition;
#else
    vec2 fogUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 fogView = reconstructViewPosition(fogUV, gl_FragCoord.z);
#endif
#ifdef APPLY_WATER_STYLE
#ifdef AURORA_WATER_DEBUG_CAPTURE
    // Nonwater in this shared translucent program overwrites debug metadata with
    // invalid data conservatively. The final depth check also rejects occluders.
    waterDebugSurface = captureWaterDebugSurface(fogView, normalView, waterWorldDx,
        waterWorldDy, waterSurface, gl_FragCoord.z);
#endif
#ifdef AURORA_WATER_OPTICS_ACTIVE
    captureWaterOpticsSurface(fogView, normalView, lmcoord, waterWorldDx, waterWorldDy,
        waterSurface, blendFunc, color, gl_FragCoord.z, waterOpticsSurface, waterOpticsOwnership);
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
    captureWaterExitSurface(fogView, normalView, lmcoord, waterWorldDx, waterWorldDy,
        waterSurface, waterInterfaceHeight, blendFunc, color, gl_FragCoord.z, waterOpticsSurface, waterOpticsOwnership);
#endif
#endif
    // Use the water's own position; existing late fog still runs once afterward.
    color.rgb = applyWaterStyle(color.rgb, fogView, normalView, lmcoord, waterSurface, blendFunc, fogColor, waterWorldDx, waterWorldDy);
#ifdef AURORA_WATER_FLOW_ACTIVE
    if (waterSurface == 1 && waterOpticsSurfaceBlend(blendFunc) && celestialEnvironmentWeight() > 0.0
        && WATER_WAVE_STRENGTH > 0.0) {
        vec3 ripple;
        float sideWeight;
        if (waterFlowFrame(flowDx,flowDy,normalView,viewToPlayerPosition(fogView),ripple,sideWeight)) {
            if (abs(dot(waterOpticsSurface.xyz,waterOpticsSurface.xyz)-1.0)<0.001) {
                waterOpticsSurface.xyz=celestialUnit(waterOpticsSurface.xyz-ripple);
            }
#if SKY_STYLE != 0
            // Thin vertical sheets keep their native transparency. Their outward
            // face can reflect skylight; backfaces and unlit caves cannot use it.
            vec3 towardEye=celestialUnit(-fogView);
            vec3 baseNormal=celestialUnit(normalView);
            if (sideWeight>0.0 && dot(towardEye,baseNormal)>0.0) {
                vec3 sheetNormal=celestialUnit(baseNormal-ripple);
                vec3 ray=reflect(-towardEye,sheetNormal);
                float skyAccess=clamp((lmcoord.y*16.0-0.5)/15.0,0.0,1.0);
                float skyWeight=skyAccess*celestialEnvironmentWeight()*sideWeight*float(SKY_BLEND)
                             *float(WATER_REFLECTION_STRENGTH)*waterFresnel(dot(sheetNormal,towardEye))
                             *smoothstep(-0.04,0.10,dot(ray,celestialUnit(upPosition)));
                color.rgb=mix(color.rgb,auroraSkyLinear(ray,fogColor),clamp(skyWeight,0.0,1.0));
            }
#endif
        }
    }
#endif
#endif
#ifdef APPLY_WATER_STYLE
#ifdef AURORA_WATER_INTERACTIONS
    if (abs(dot(waterOpticsSurface.xyz,waterOpticsSurface.xyz)-1.0)<0.001) {
        waterOpticsSurface.xyz=waterInteractiveNormal(waterOpticsSurface.xyz,fogView,
            waterWorldDx,waterWorldDy,waterOpticsOwnership.b);
    }
#endif
#endif
    color.rgb = applyLateAtmosphericFog(color.rgb, fogView);
#endif
#ifdef WRITE_SURFACE_DATA
    writeSurfaceData(lmcoord);
#endif
}
