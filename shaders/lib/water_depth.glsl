#ifndef AURORA_WATER_DEPTH_INCLUDED
#define AURORA_WATER_DEPTH_INCLUDED
#include "/lib/water_depth_settings.glsl"
#include "/lib/position.glsl"
#include "/lib/celestial.glsl"

// Iris copies this before opaque hands and the main translucent phase.
// Earlier translucent categories may already be present: this is not a water
// exit surface or a universally opaque-only buffer. No scene-color copy is read.
uniform sampler2D depthtex2;

vec3 applyWaterDepthTint(vec3 scene, vec3 surfaceView, vec3 normalView, float lightingWeight) {
#if WATER_DEPTH_TINT == 0
    return scene;
#else
    if (isnan(lightingWeight) || isinf(lightingWeight)) return scene;
    float weight = clamp(WATER_DEPTH_STRENGTH, 0.0, 0.35) * clamp(lightingWeight, 0.0, 1.0);
    if (weight <= 0.0) return scene;
    if (any(isnan(scene)) || any(isinf(scene)) || any(lessThan(scene, vec3(0.0)))) return scene;
    float peak = max(max(scene.r, scene.g), scene.b);
    if (peak <= 0.0) return scene;
    if (any(isnan(surfaceView)) || any(isinf(surfaceView))
        || any(isnan(normalView)) || any(isinf(normalView))
        || any(isnan(upPosition)) || any(isinf(upPosition))) return scene;
    float viewScale = max(max(abs(surfaceView.x), abs(surfaceView.y)), abs(surfaceView.z));
    float normalScale = max(max(abs(normalView.x), abs(normalView.y)), abs(normalView.z));
    float upScale = max(max(abs(upPosition.x), abs(upPosition.y)), abs(upPosition.z));
    if (viewScale <= 1e-6 || normalScale <= 1e-6 || upScale <= 1e-6) return scene;
    // Always use the original face normal, never the animated reflection normal.
    float upwardSurface = smoothstep(0.5, 0.95, dot(celestialUnit(normalView), celestialUnit(upPosition)));
    weight *= upwardSurface;
    if (weight <= 0.0) return scene;

    if (any(isnan(gl_FragCoord.xyz)) || any(isinf(gl_FragCoord.xyz))) return scene;
    ivec2 depthSize = textureSize(depthtex2, 0);
    if (any(lessThanEqual(depthSize, ivec2(0)))
        || any(lessThan(gl_FragCoord.xy, vec2(0.0)))
        || any(greaterThanEqual(gl_FragCoord.xy, vec2(depthSize)))) return scene;
    float surfaceDepth = gl_FragCoord.z;
    if (surfaceDepth < 0.0 || surfaceDepth >= 1.0) return scene;
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    float backgroundDepth = texelFetch(depthtex2, pixel, 0).r;
    if (isnan(backgroundDepth) || isinf(backgroundDepth)
        || backgroundDepth < 0.0 || backgroundDepth >= 1.0
        || backgroundDepth <= surfaceDepth) return scene;
    vec2 pixelCenterUV = (vec2(pixel) + 0.5) / vec2(depthSize);
    vec3 backgroundView = reconstructViewPosition(pixelCenterUV, backgroundDepth);
    if (any(isnan(backgroundView)) || any(isinf(backgroundView))) return scene;
    vec3 deltaView = backgroundView - surfaceView;
    if (any(isnan(deltaView)) || any(isinf(deltaView))) return scene;
    float rayGap = dot(deltaView, celestialUnit(surfaceView));
    if (isnan(rayGap) || isinf(rayGap) || rayGap <= 0.0) return scene;
    // A direction difference needs rotation/scale only; translation cancels.
    vec3 worldGap = mat3(gbufferModelViewInverse) * deltaView;
    if (any(isnan(worldGap)) || any(isinf(worldGap))) return scene;
    float drop = clamp(-worldGap.y, 0.0, 32.0);
    if (drop <= 0.0) return scene;
    // Vertical background separation gives consistent color on a flat pool floor
    // across view angles. It is a bounded artistic cue, not volume thickness.
    weight *= 1.0 - exp(-drop / max(WATER_DEPTH_SCALE, 1e-4));
    if (isnan(weight) || isinf(weight) || weight <= 0.0) return scene;

    // Multiplicative chroma retains the existing biome/source color. Normalize
    // PER PIXEL to preserve arbitrary input Rec.709 luminance, not just gray.
    // Peak normalization avoids overflowing the luminance calculation on HDR.
    const vec3 luminanceWeights = vec3(0.2126, 0.7152, 0.0722);
    vec3 normalizedScene = scene / peak;
    vec3 chroma = normalizedScene * vec3(0.25, 0.85, 1.05);
    float sourceLuma = dot(normalizedScene, luminanceWeights);
    float chromaLuma = dot(chroma, luminanceWeights);
    if (chromaLuma <= 0.0 || isnan(chromaLuma) || isinf(chromaLuma)) return scene;
    vec3 target = chroma * (sourceLuma / chromaLuma);
    vec3 result = mix(normalizedScene, target, weight) * peak;
    // Never introduce invalid/negative values or overflow the RGBA16F scene
    // attachment. Unusually high input radiance retains its original value.
    if (any(isnan(result)) || any(isinf(result)) || any(lessThan(result, vec3(0.0)))
        || any(greaterThan(result, vec3(65504.0)))) return scene;
    return result;
#endif
}
#endif
