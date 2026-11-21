#version 330 compatibility
#include "/lib/water_caustics_capture.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
/*
const int shadowcolor0Format = RGBA16;
*/
const bool shadowcolor0Clear = true;
const vec4 shadowcolor0ClearColor = vec4(0.0);
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 causticRecord;
in vec3 causticPlayerPosition;
in vec3 causticNormalWorld;
flat in int causticWaterMaterial;
#endif
uniform sampler2D gtexture;
in vec2 texcoord;
in vec4 glcolor;
void main() {
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
    // Continuous world derivatives precede texture-alpha discard and all gates.
    vec2 dx = dFdx(causticPlayerPosition.xz);
    vec2 dy = dFdy(causticPlayerPosition.xz);
#endif
    // Binary cutout only; leaves can cast holes, never translucent/color shadows.
    if (texture(gtexture, texcoord).a * glcolor.a < 0.1) discard;
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
    causticRecord = waterCausticSurface(causticPlayerPosition, causticNormalWorld,
        dx, dy, causticWaterMaterial, gl_FragCoord.z);
#endif
    // Rasterization also writes the matching light depth.
}
