// Input and output are LINEAR RGB. The output is display-referred SDR [0,1].
// A custom analytic shoulder, not ACES, film simulation or physical camera response.
vec3 toneMapScene(vec3 sceneLinear) {
    vec3 rgb = max(sceneLinear, vec3(0.0));
#if TONE_MAPPING == 0
    return clamp(rgb, 0.0, 1.0);
#else
    float peak = max(max(rgb.r, rgb.g), rgb.b);
    float knee = clamp(TONEMAP_KNEE, 0.0, 0.95);
    if (peak <= knee) return rgb; // Identity below the shoulder, including black.
    float span = 1.0 - knee;
    float compressed = knee + span * (1.0 - exp(-(peak - knee) / span));
    // Scale all channels equally: preserve linear RGB ratios, avoid per-channel clipping.
    return rgb * (compressed / peak);
#endif
}
