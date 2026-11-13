// M8 keeps baked Minecraft shading, then converts RGB for scene composition.
#include "/lib/scene_color.glsl"
#ifdef APPLY_CLOUD_ATMOSPHERE
#include "/lib/clouds.glsl"
#endif

uniform sampler2D gtexture;

uniform float alphaTestRef = 0.1;

in vec2 texcoord;
in vec4 glcolor;

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;

void main() {
	color = texture(gtexture, texcoord) * glcolor;
	if (color.a < alphaTestRef) {
		discard;
	}
    // RGB only: alpha coverage, discard and surface-data attachments stay unchanged.
    color.rgb = sceneFromDisplay(color.rgb);
#ifdef APPLY_CLOUD_ATMOSPHERE
    // Cloud source color changes only after its original coverage/discard decision.
    color.rgb = applyCloudAtmosphere(color.rgb);
#endif
}
