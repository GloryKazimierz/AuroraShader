#version 330 compatibility
#include "/lib/settings.glsl"
#include "/lib/color.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/lighting.glsl"
#include "/lib/shadow.glsl"
// Normal mode keeps Milestone 1 grading after deferred lighting/translucency.
// Debug reads raw surface buffers, bypassing grading and later color overlays.
uniform sampler2D colortex0;
uniform sampler2D colortex1;
uniform sampler2D colortex2;
in vec2 texcoord;
layout(location = 0) out vec4 color;
void main() {
#if DEBUG_VIEW == 0
    vec4 scene = texture(colortex0, texcoord);
    color = vec4(gradeColor(scene.rgb), scene.a);
#elif DEBUG_VIEW == 4
    color = vec4(vec3(rawShadowDepth(texcoord)), 1.0);
#else
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 surface = texelFetch(colortex1, pixel, 0);
    vec3 debugColor = vec3(0.0); // Black = no valid recorded surface.
    if (surface.a > 0.5) {
        vec3 normalView = decodeNormal(surface.rgb);
#if DEBUG_VIEW == 1
        debugColor = normalView * 0.5 + 0.5;
#elif DEBUG_VIEW == 2
        debugColor = vec3(texelFetch(colortex2, pixel, 0).rg, 0.0);
#elif DEBUG_VIEW == 3
        debugColor = vec3(diffuseTerm(normalView));
#elif DEBUG_VIEW == 5
        debugColor = vec3(hardShadowVisibility(pixel));
#endif
    }
    color = vec4(debugColor, 1.0);
#endif
}
