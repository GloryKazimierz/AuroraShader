// M8 keeps baked Minecraft shading, then converts RGB for scene composition.
#include "/lib/water_optics_capture.glsl"
#include "/lib/scene_color.glsl"

uniform sampler2D lightmap;

uniform float alphaTestRef = 0.1;

in vec2 lmcoord;
in vec4 glcolor;

#ifdef AURORA_WATER_OPTICS_ACTIVE
/* RENDERTARGETS: 0,8 */
layout(location = 1) out vec4 waterOpticsOwnership;
#else
/* RENDERTARGETS: 0 */
#endif
layout(location = 0) out vec4 color;

void main() {
	color = glcolor * texture(lightmap, lmcoord);
	if (color.a < alphaTestRef) {
		discard;
	}
    // RGB only: alpha coverage, discard and surface-data attachments stay unchanged.
    color.rgb = sceneFromDisplay(color.rgb);
#ifdef AURORA_WATER_OPTICS_ACTIVE
    waterOpticsOwnership = vec4(1.0, 0.0, 0.0, 0.0);
#endif
}
