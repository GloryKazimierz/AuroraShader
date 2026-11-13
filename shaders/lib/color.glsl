// Color grading only: no changes to scene geometry, lightmaps or depth.
// Explicit branches keep neutral settings an exact RGB bypass.
vec3 gradeColor(vec3 color) {
#if SCENE_COLOR_MODE == 0
    // Legacy M1-M7 exposure. HDR exposure is applied once in final before tone mapping.
    if (EXPOSURE != 0.0) {
        // Approximate display gamma -> linear, exposure in stops -> display.
        color = pow(max(color, vec3(0.0)), vec3(2.2));
        color *= exp2(EXPOSURE);
        color = pow(color, vec3(1.0 / 2.2));
    }
#endif
    if (TEMPERATURE != 0.0 || TINT != 0.0) {
        // Artistic channel balance, not a calibrated Kelvin white balance.
        color *= vec3(1.0 + 0.15 * TEMPERATURE + 0.075 * TINT,
                      1.0 - 0.15 * TINT,
                      1.0 - 0.15 * TEMPERATURE + 0.075 * TINT);
    }
    if (SATURATION != 1.0) {
        float gray = dot(color, vec3(0.2126, 0.7152, 0.0722));
        color = mix(vec3(gray), color, SATURATION);
    }
    if (CONTRAST != 1.0) {
        color = (color - 0.5) * CONTRAST + 0.5;
    }
#ifdef GRAYSCALE
    color = vec3(dot(color, vec3(0.2126, 0.7152, 0.0722)));
#endif
    // Display-space artistic grading may still clip at extreme settings.
    return clamp(color, 0.0, 1.0);
}
