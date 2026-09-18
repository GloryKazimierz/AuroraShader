#include "/lib/shadow_settings.glsl"
#include "/lib/position.glsl"
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform sampler2D shadowtex1; // Opaque/cutout caster depth, no translucency.
uniform sampler2D depthtex1;  // Camera depth snapshot before translucency.

float hardShadowVisibility(ivec2 pixel) {
#ifdef SHADOWS_ENABLED
    float depth = texelFetch(depthtex1, pixel, 0).r;
    if (depth >= 1.0) return 1.0; // Sky has no receiver position.
    vec2 screenUV = (vec2(pixel) + 0.5) / vec2(textureSize(depthtex1, 0));
    vec3 viewPosition = reconstructViewPosition(screenUV, depth);
    vec3 playerPosition = viewToPlayerPosition(viewPosition);
    // Player-relative position -> light VIEW -> light CLIP.
    vec4 lightClip = shadowProjection * shadowModelView * vec4(playerPosition, 1.0);
    if (lightClip.w <= 0.0) return 1.0;
    // Light clip -> light NDC -> shadow UV and depth, all [0,1].
    vec3 shadowCoord = (lightClip.xyz / lightClip.w) * 0.5 + 0.5;
    // Outside this single map: assume lit instead of wrapping/clamping shadows.
    if (any(lessThan(shadowCoord, vec3(0.0))) ||
        any(greaterThanEqual(shadowCoord, vec3(1.0)))) return 1.0;
    ivec2 shadowPixel = ivec2(shadowCoord.xy * vec2(textureSize(shadowtex1, 0)));
    // One exact texel, one comparison. No PCF or hardware comparison sampler.
    float storedDepth = texelFetch(shadowtex1, shadowPixel, 0).r;
    // Constant bias moves the receiver toward the light in normalized depth.
    return shadowCoord.z - SHADOW_BIAS <= storedDepth ? 1.0 : 0.0;
#else
    return 1.0; // Restores Milestone 2 lighting; map remains available for debug.
#endif
}
float rawShadowDepth(vec2 screenUV) {
    // Display the complete light-view map, not projected onto the camera scene.
    ivec2 size = textureSize(shadowtex1, 0);
    ivec2 pixel = clamp(ivec2(screenUV * vec2(size)), ivec2(0), size - ivec2(1));
    return texelFetch(shadowtex1, pixel, 0).r;
}
