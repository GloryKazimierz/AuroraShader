// Iris provides these inverse matrices; no extra position buffer is needed.
uniform mat4 gbufferProjectionInverse;
uniform mat4 gbufferModelViewInverse;

vec3 reconstructViewPosition(vec2 screenUV, float depth) {
    // Screen UV/depth [0,1] -> camera NDC [-1,1].
    vec4 cameraNDC = vec4(vec3(screenUV, depth) * 2.0 - 1.0, 1.0);
    // Inverse perspective projection -> homogeneous VIEW position.
    vec4 viewH = gbufferProjectionInverse * cameraNDC;
    // Perspective divide recovers the actual view-space position.
    return viewH.xyz / viewH.w;
}
vec3 viewToPlayerPosition(vec3 viewPosition) {
    // VIEW -> Iris player/feet-relative world-oriented space.
    // This is NOT absolute world position. Do not add cameraPosition:
    // shadowModelView expects this same player-relative space.
    return (gbufferModelViewInverse * vec4(viewPosition, 1.0)).xyz;
}
