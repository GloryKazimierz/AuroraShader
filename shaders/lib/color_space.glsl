// Exact sRGB transfer functions for NEW palette operations only.
// Existing lightmap, blending and scene storage remain the M6 LDR pipeline.
// Local linear interpolation does not make the entire renderer linear or HDR.
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
