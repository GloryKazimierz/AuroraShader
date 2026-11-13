#include "/lib/fog_settings.glsl"
#include "/lib/sky_palette.glsl"
#include "/lib/position.glsl"
uniform vec3 fogColor;
uniform ivec3 cameraPositionInt;
uniform vec3 cameraPositionFract;
uniform ivec2 eyeBrightnessSmooth;
uniform float viewWidth;
uniform float viewHeight;
uniform ivec4 blendFunc;

float fogHeightDensity(float worldY) {
    // Density stays bounded below the reference plane; this is not physical scattering.
    return exp(-max(worldY - FOG_BASE_HEIGHT, 0.0) / max(FOG_HEIGHT_FALLOFF, 1.0));
}
float fogTransmission(vec3 viewPosition) {
    if (any(isnan(viewPosition)) || any(isinf(viewPosition))) return 1.0;
    float rayLength = length(viewPosition);
    if (isnan(rayLength) || isinf(rayLength)) return 1.0;
    float start = max(FOG_START, 0.0);
    if (rayLength <= start || FOG_DENSITY <= 0.0) return 1.0;
    float skyAccess = smoothstep(0.0, 0.5, clamp(float(eyeBrightnessSmooth.y) / 240.0, 0.0, 1.0));
    float environment = celestialEnvironmentWeight() * skyAccess;
    if (environment <= 0.0) return 1.0;
    // Camera anchor + inverse-view translation gives the ray origin; do not
    // confuse player/feet-relative positions with absolute world height.
    float anchorY = float(cameraPositionInt.y) + cameraPositionFract.y;
    float originY = anchorY + gbufferModelViewInverse[3].y;
    float endY = anchorY + viewToPlayerPosition(viewPosition).y;
    if (isnan(originY) || isinf(originY) || isnan(endY) || isinf(endY)) return 1.0;
    float startY = mix(originY, endY, start / rayLength);
    float middleY = 0.5 * (startY + endY);
    // Three-point Simpson approximation of bounded density along the fogged segment.
    float averageDensity = (fogHeightDensity(startY) + 4.0 * fogHeightDensity(middleY)
                          + fogHeightDensity(endY)) / 6.0;
    float weather = 1.0 + max(FOG_RAIN_BOOST, 0.0) * clamp(rainStrength, 0.0, 1.0);
    float opticalDepth = max(FOG_DENSITY, 0.0) * (rayLength - start) * averageDensity * weather * environment;
    return exp(-clamp(opticalDepth, 0.0, 80.0));
}
vec3 applyAtmosphericFog(vec3 scene, vec3 viewPosition) {
#if FOG_ENABLED == 0
    return scene;
#elif SCENE_COLOR_MODE == 0
    return scene; // Legacy display-space composition remains an M8 comparison path.
#else
    float transmission = fogTransmission(viewPosition);
    if (transmission >= 1.0) return scene;
    // Shared day/night/weather palette, already linear in this enabled branch.
    vec3 atmosphere = applyAuroraSky(celestialUnit(viewPosition), fogColor, fogColor);
    return mix(atmosphere, scene, transmission);
#endif
}
vec3 applyLateAtmosphericFog(vec3 scene, vec3 viewPosition) {
#if FOG_ENABLED == 0
    return scene;
#elif SCENE_COLOR_MODE == 0
    return scene;
#else
    // GL_SRC_ALPHA=770, ONE_MINUS_SRC_ALPHA=771, ONE=1, SRC_COLOR=768.
    // Only known late draw paths call this; alpha/coverage is never modified.
    if ((blendFunc.x == 770 && blendFunc.y == 771) || (blendFunc.x == 1 && blendFunc.y == 0)) {
        return applyAtmosphericFog(scene, viewPosition);
    }
    float transmission = fogTransmission(viewPosition);
    if (blendFunc.y == 1 && (blendFunc.x == 1 || blendFunc.x == 770)) {
        // Additive sources attenuate; adding fog color would accumulate it per layer.
        return scene * transmission;
    }
    if (blendFunc.x == 768 && blendFunc.y == 1) {
        // SRC_COLOR squares the source in blending: sqrt(T) yields total attenuation T.
        return scene * sqrt(transmission);
    }
    return scene; // Unknown/color-dependent blend modes await a dedicated contract.
#endif
}
