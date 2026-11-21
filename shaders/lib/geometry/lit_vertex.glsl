// Shared Base-330 vertex stage. Geometry writes scene color before final.

// Model-space normal -> view space using the inverse-transpose normal matrix.
out vec3 normalView;
out vec2 lmcoord;
out vec2 texcoord;
out vec4 glcolor;
#if defined(APPLY_WATER_STYLE) || defined(APPLY_FOLIAGE_WIND)
in vec2 mc_Entity;
#endif
#ifdef APPLY_WATER_STYLE
flat out int waterSurface;
#include "/lib/water_underwater_settings.glsl"
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
in vec4 at_midBlock;
out float waterInterfaceHeight;
#endif
#endif
#ifdef APPLY_FOLIAGE_WIND
#include "/lib/foliage.glsl"
in vec4 at_midBlock;
uniform mat4 gbufferModelView;
uniform mat4 gbufferModelViewInverse;
#endif

void main() {
	gl_Position = ftransform();
#ifdef APPLY_FOLIAGE_WIND
    // The shadow vertex stage applies this same world-space wind before projection.
    gl_Position = foliageWindClip(gl_Position, gl_ModelViewMatrix * gl_Vertex,
        gbufferModelViewInverse, gbufferModelView, gl_ProjectionMatrix, mc_Entity, at_midBlock);
#endif
    normalView = gl_NormalMatrix * gl_Normal;
	texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
	lmcoord = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
	glcolor = gl_Color;
#ifdef APPLY_WATER_STYLE
    // Block ID alone is insufficient: y==1 marks a fluid draw, not its host block.
    waterSurface = (mc_Entity.x == 10001.0 && mc_Entity.y == 1.0) ? 1 : 0;
#ifdef AURORA_WATER_UNDERWATER_ACTIVE
    // Signed 1/64-block vertex->center offset: a real bottom is near height0.
    // This distinguishes Sodium's reversed top quad from a downward bottom face.
    waterInterfaceHeight = 0.5 - at_midBlock.y / 64.0;
#endif
#endif
}