#version 330 compatibility
// Fullscreen pass between opaque/cutout geometry and most translucency.
out vec2 texcoord;
void main() {
    gl_Position = ftransform();
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
}
