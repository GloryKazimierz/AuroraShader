// Shared Base-330 vertex stage. Geometry writes scene color before final.

out vec2 lmcoord;
out vec4 glcolor;

void main() {
	gl_Position = ftransform();
	lmcoord = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
	glcolor = gl_Color;
}