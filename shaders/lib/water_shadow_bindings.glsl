#ifndef AURORA_WATER_SHADOW_BINDINGS_INCLUDED
#define AURORA_WATER_SHADOW_BINDINGS_INCLUDED
#include "/lib/shadow_settings.glsl"
#include "/lib/shadow_bias.glsl"
// Shared by optional water receivers (M4 caustics and M5 foam). Include only
// inside each feature's active path so default/legacy shader tokens stay intact.
uniform sampler2D shadowcolor0;
uniform sampler2D shadowtex0;
uniform sampler2D shadowtex1;
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform mat4 shadowModelViewInverse;
uniform mat4 shadowProjectionInverse;
#endif
