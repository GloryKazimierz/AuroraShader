// All normals and celestial light directions in this milestone use VIEW space.
vec3 safeNormal(vec3 value) {
    // Zero-length normals have no direction; callers mark them invalid.
    return value * inversesqrt(max(dot(value, value), 1e-12));
}
vec3 encodeNormal(vec3 normalView) {
    // Renormalize after raster interpolation, then map [-1,1] to [0,1].
    return safeNormal(normalView) * 0.5 + 0.5;
}
vec3 decodeNormal(vec3 encoded) {
    return safeNormal(encoded * 2.0 - 1.0);
}
