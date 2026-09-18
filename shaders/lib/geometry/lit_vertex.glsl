// Shared Base-330 vertex stage. Geometry writes scene color before final.

// Model-space normal -> view space using the inverse-transpose normal matrix.
out vec3 normalView;
out vec2 lmcoord;
out vec2 texcoord;
out vec4 glcolor;

void main() {
	gl_Position = ftransform();
    normalView = gl_NormalMatrix * gl_Normal;
	texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
	lmcoord = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
	glcolor = gl_Color;
}