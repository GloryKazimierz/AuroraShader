#version 330 compatibility
uniform sampler2D gtexture;
in vec2 texcoord;
in vec4 glcolor;
void main() {
    // Binary cutout only; leaves can cast holes, never translucent/color shadows.
    if (texture(gtexture, texcoord).a * glcolor.a < 0.1) discard;
    // Depth-only: fixed-function rasterization writes light depth to shadowtex.
    // No colortex render target or shadow-color output is needed.
}
