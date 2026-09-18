#version 330 compatibility
// Fixed Iris shadow-map configuration, intentionally not user options.
const int shadowMapResolution = 2048;
const float shadowDistance = 64.0;
const bool shadowHardwareFiltering = false;

out vec2 texcoord;
out vec4 glcolor;
void main() {
    // In the shadow pass Iris binds the LIGHT model-view/projection matrices.
    // ftransform transforms model vertices directly to light clip space.
    // No distortion: deferred uses exactly the matching shadow matrices.
    gl_Position = ftransform();
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    glcolor = gl_Color;
}
