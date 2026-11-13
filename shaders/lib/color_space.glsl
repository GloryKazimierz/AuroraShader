#ifndef AURORA_COLOR_SPACE_INCLUDED
#define AURORA_COLOR_SPACE_INCLUDED
// Exact sRGB transfer functions shared by palette and scene-color contracts.
// M8 uses linear/HDR scene storage and compositing; legacy mode retains M7 LDR.
// Minecraft's baked input shading remains an artistic display-like source.
vec3 srgbToLinear(vec3 value) {
    vec3 c = max(value, vec3(0.0));
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
               step(vec3(0.04045), c));
}
vec3 linearToSrgb(vec3 value) {
    vec3 c = max(value, vec3(0.0));
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055,
               step(vec3(0.0031308), c));
}
#endif
