#include "/lib/pipeline_settings.glsl"
#include "/lib/color_space.glsl"

vec3 sceneFromDisplay(vec3 displayColor) {
#if SCENE_COLOR_MODE == 0
    return displayColor;
#else
    return srgbToLinear(displayColor);
#endif
}
vec3 sceneFromLinear(vec3 linearColor) {
#if SCENE_COLOR_MODE == 0
    return clamp(linearToSrgb(linearColor), 0.0, 1.0);
#else
    return max(linearColor, vec3(0.0));
#endif
}
