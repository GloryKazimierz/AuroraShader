// Shared Base-330 vertex stage. Geometry writes scene color before final.

out vec4 glcolor;

void main() {
	gl_Position = ftransform();
	glcolor = gl_Color;
}
