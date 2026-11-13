// M8 keeps baked Minecraft shading, then converts RGB for scene composition.
#include "/lib/scene_color.glsl"
#ifdef APPLY_LATE_FOG
#include "/lib/fog.glsl"
#endif
#ifdef APPLY_WATER_STYLE
#include "/lib/water.glsl"
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
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;
#endif

void main() {
	color = texture(gtexture, texcoord) * glcolor;
	color *= texture(lightmap, lmcoord);
	if (color.a < alphaTestRef) {
		discard;
	}
    // RGB only: alpha coverage, discard and surface-data attachments stay unchanged.
    color.rgb = sceneFromDisplay(color.rgb);
#ifdef APPLY_LATE_FOG
    // Reconstruct this foreground fragment, not the already composed background.
    vec2 fogUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec3 fogView = reconstructViewPosition(fogUV, gl_FragCoord.z);
#ifdef APPLY_WATER_STYLE
    // Use the water's own position; existing late fog still runs once afterward.
    color.rgb = applyWaterStyle(color.rgb, fogView, normalView, lmcoord, waterSurface, blendFunc, fogColor);
#endif
    color.rgb = applyLateAtmosphericFog(color.rgb, fogView);
#endif
#ifdef WRITE_SURFACE_DATA
    writeSurfaceData(lmcoord);
#endif
}
