#include "/lib/normal.glsl"
in vec3 normalView;
/* RENDERTARGETS: 0,1,2 */
layout(location = 0) out vec4 color;
layout(location = 1) out vec4 normalData;
layout(location = 2) out vec4 lightmapData;

void writeSurfaceData(vec2 lightmapUV) {
    // colortex1: encoded view normal RGB; A=1 for a valid surface.
    float valid = dot(normalView, normalView) > 1e-12 ? 1.0 : 0.0;
    normalData = vec4(encodeNormal(normalView), valid);
    // Minecraft lightmap centers range from 0.5/16 to 15.5/16.
    // Store normalized block level in R and sky level in G; B/A unused.
    // The sampled lightmap RGB is STILL multiplied into colortex0 as before.
    vec2 levels = clamp((lightmapUV - vec2(0.5 / 16.0)) * (16.0 / 15.0), 0.0, 1.0);
    lightmapData = vec4(levels, 0.0, 1.0);
}
