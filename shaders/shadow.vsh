#version 330 compatibility
// Fixed Iris shadow-map configuration, intentionally not user options.
const int shadowMapResolution = 2048;
const float shadowDistance = 64.0;
const bool shadowHardwareFiltering = false;

#include "/lib/foliage.glsl"
#include "/lib/water_caustics_settings.glsl"
in vec2 mc_Entity;
in vec4 at_midBlock;
uniform mat4 shadowModelView;
uniform mat4 shadowModelViewInverse;

#ifdef AURORA_WATER_CAUSTICS_ACTIVE
out vec3 causticPlayerPosition;
out vec3 causticNormalWorld;
flat out int causticWaterMaterial;
#endif
out vec2 texcoord;
out vec4 glcolor;
void main() {
    // In the shadow pass Iris binds the LIGHT model-view/projection matrices.
    // ftransform transforms model vertices directly to light clip space.
    // No distortion: deferred uses exactly the matching shadow matrices.
    gl_Position = ftransform();
    // Match terrain displacement; caster alpha/UV and shadow-map configuration stay unchanged.
    gl_Position = foliageWindClip(gl_Position, gl_ModelViewMatrix * gl_Vertex,
        shadowModelViewInverse, shadowModelView, gl_ProjectionMatrix, mc_Entity, at_midBlock);
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
    causticPlayerPosition = (shadowModelViewInverse * gl_ModelViewMatrix * gl_Vertex).xyz;
    causticNormalWorld = transpose(mat3(shadowModelView)) * gl_NormalMatrix * gl_Normal;
    causticWaterMaterial = mc_Entity.x == 10001.0 && mc_Entity.y == 1.0 ? 1 : 0;
#endif
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    glcolor = gl_Color;
}
