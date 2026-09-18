#include "/lib/normal.glsl"
// Iris supplies the highest celestial body in VIEW space (sun/day, moon/night).
// This uniform does not require a shadow map or a shadow shader.
uniform vec3 shadowLightPosition;

float diffuseTerm(vec3 normalView) {
    vec3 lightDirectionView = safeNormal(shadowLightPosition);
    return max(dot(normalView, lightDirectionView), 0.0);
}
vec3 lightScene(vec3 scene, vec3 normalView, vec2 lightLevels) {
    float ndotl = diffuseTerm(normalView);
    float lambert = AMBIENT_LIGHT + DIRECT_LIGHT * ndotl;
    // An educational modulation of the already lightmapped scene, not albedo
    // relighting: no second multiplication by Minecraft's lightmap.
    // No skylight => factor 1, so block-lit caves keep their baseline brightness.
    // Block light reduces the modulation to preserve nearby torch lighting.
    float skyWeight = lightLevels.y * (1.0 - lightLevels.x);
    float factor = mix(1.0, lambert, LIGHTING_STRENGTH * skyWeight);
    return scene * factor;
}
