// VIEW-space directions: the dot product is invariant under camera rotation.
// sunPosition always describes the SUN; shadowLightPosition switches to the moon.
uniform vec3 sunPosition;
uniform vec3 upPosition;
uniform float rainStrength;
uniform bool hasSkylight;
uniform bool hasCeiling;
uniform int isEyeInWater;
uniform float blindness;
uniform float darknessFactor;

vec3 celestialUnit(vec3 direction) {
    if (any(isnan(direction)) || any(isinf(direction))) return vec3(0.0, 1.0, 0.0);
    float scale = max(max(abs(direction.x), abs(direction.y)), abs(direction.z));
    if (scale <= 1e-6) return vec3(0.0, 1.0, 0.0);
    return normalize(direction / scale);
}
float celestialEnvironmentWeight() {
    // Iris dimension properties also opt in open, skylit MODDED dimensions.
    // Fade the new styling out for vision effects; keep M6 as the fallback.
    if (!hasSkylight || hasCeiling || isEyeInWater != 0) return 0.0;
    return 1.0 - clamp(max(blindness, darknessFactor), 0.0, 1.0);
}
vec2 celestialPhases() {
    float elevation = clamp(dot(celestialUnit(sunPosition), celestialUnit(upPosition)), -1.0, 1.0);
    float day = smoothstep(-0.10, 0.16, elevation);
    float twilight = smoothstep(-0.18, -0.04, elevation)
                   * (1.0 - smoothstep(0.08, 0.35, elevation));
    // Smooth geometric weights at both sunrise/sunset; no ticking time switch.
    return vec2(day, twilight);
}
