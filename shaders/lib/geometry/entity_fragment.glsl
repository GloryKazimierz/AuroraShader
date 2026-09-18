// Shared Base-330 fragment stage. Geometry writes scene color before final.

uniform sampler2D lightmap;
uniform sampler2D gtexture;
uniform vec4 entityColor;

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
	color.rgb = mix(color.rgb, entityColor.rgb, entityColor.a);
	color *= texture(lightmap, lmcoord);
	if (color.a < alphaTestRef) {
		discard;
	}
#ifdef WRITE_SURFACE_DATA
    writeSurfaceData(lmcoord);
#endif
}