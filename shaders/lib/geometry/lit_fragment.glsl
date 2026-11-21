// M8 keeps baked Minecraft shading, then converts RGB for scene composition.
#include "/lib/scene_color.glsl"
#ifdef APPLY_LATE_FOG
#include "/lib/fog.glsl"
#endif
#ifdef APPLY_WATER_STYLE
#include "/lib/water.glsl"
#include "/lib/water_debug_capture.glsl"
flat in int waterSurface;
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
#ifdef AURORA_WATER_DEBUG_CAPTURE
/* RENDERTARGETS: 0,7 */
layout(location = 0) out vec4 color;
layout(location = 1) out vec4 waterDebugSurface;
#else
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
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
    waterWorldDx = (mat3(gbufferModelViewInverse) * dFdx(waterViewPosition)).xz;
    waterWorldDy = (mat3(gbufferModelViewInverse) * dFdy(waterViewPosition)).xz;
#endif
#endif
	color = texture(gtexture, texcoord) * glcolor;
	color *= texture(lightmap, lmcoord);
	if (color.a < alphaTestRef) {
		discard;
	}
    // RGB only: alpha coverage, discard and surface-data attachments stay unchanged.
    color.rgb = sceneFromDisplay(color.rgb);
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
    // Use the water's own position; existing late fog still runs once afterward.
    color.rgb = applyWaterStyle(color.rgb, fogView, normalView, lmcoord, waterSurface, blendFunc, fogColor, waterWorldDx, waterWorldDy);
#endif
    color.rgb = applyLateAtmosphericFog(color.rgb, fogView);
#endif
#ifdef WRITE_SURFACE_DATA
    writeSurfaceData(lmcoord);
#endif
}
