// Shared Base-330 vertex stage. Geometry writes scene color before final.

// Model-space normal -> view space using the inverse-transpose normal matrix.
out vec3 normalView;
out vec2 lmcoord;
out vec2 texcoord;
out vec4 glcolor;
#ifdef APPLY_WATER_STYLE
in vec2 mc_Entity;
flat out int waterSurface;
#endif

void main() {
	gl_Position = ftransform();
    normalView = gl_NormalMatrix * gl_Normal;
	texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
	lmcoord = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
	glcolor = gl_Color;
#ifdef APPLY_WATER_STYLE
    // Block ID alone is insufficient: y==1 marks a fluid draw, not its host block.
    waterSurface = (mc_Entity.x == 10001.0 && mc_Entity.y == 1.0) ? 1 : 0;
#endif
}