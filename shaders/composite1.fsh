#version 330 compatibility
#include "/lib/bloom.glsl"
uniform sampler2D colortex0;
uniform sampler2D colortex3;
in vec2 texcoord;

// Iris parses buffer enums from comments; these are not active GLSL variables.
/*
const int colortex3Format = RGBA16F;
const int colortex4Format = RGBA16F;
*/
const vec4 colortex3ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const vec4 colortex4ClearColor = vec4(0.0, 0.0, 0.0, 0.0);

/* RENDERTARGETS: 3 */
layout(location = 0) out vec4 color;
void main() {
    color = vec4(0.0);
    if (!bloomActive()) return;
    ivec2 sourceSize = textureSize(colortex0, 0);
    // Query the allocated output extent (no feedback sample); rounding may be odd.
    ivec2 outputSize = textureSize(colortex3, 0);
    vec2 ratio = vec2(sourceSize) / vec2(outputSize);
    vec2 first = floor(gl_FragCoord.xy) * ratio;
    vec2 last = min((floor(gl_FragCoord.xy) + 1.0) * ratio, vec2(sourceSize));
    ivec2 base = ivec2(floor(first));
    vec3 sum = vec3(0.0);
    // At half scale an output footprint intersects at most 3x3 source pixels.
    // Area weights include the last odd row/column; extraction precedes averaging.
    for (int y = 0; y < 3; ++y) {
        for (int x = 0; x < 3; ++x) {
            ivec2 pixel = base + ivec2(x, y);
            if (any(greaterThanEqual(pixel, sourceSize))) continue;
            vec2 overlap = max(min(last, vec2(pixel + 1)) - max(first, vec2(pixel)), vec2(0.0));
            float area = overlap.x * overlap.y;
            if (area > 0.0) sum += extractBloom(texelFetch(colortex0, pixel, 0).rgb) * area;
        }
    }
    float totalArea = max((last.x - first.x) * (last.y - first.y), 0.000001);
    color = vec4(bloomSafe(sum / totalArea), 0.0);
}
