#ifndef AURORA_WATER_RESOLVE_INCLUDED
#define AURORA_WATER_RESOLVE_INCLUDED
#include "/lib/water_optics_settings.glsl"
#ifdef AURORA_WATER_OPTICS_ACTIVE
#include "/lib/water_settings.glsl"
#include "/lib/lighting_settings.glsl"
#include "/lib/fog.glsl"
#include "/lib/water_transport.glsl"
#include "/lib/water_reflection_filter.glsl"
#include "/lib/water_caustics.glsl"
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
uniform sampler2D colortex1;
#endif
uniform sampler2D colortex7;
uniform sampler2D colortex8;
uniform sampler2D depthtex0;
uniform vec3 shadowLightPosition;
#include "/lib/water_refraction_settings.glsl"
#include "/lib/water_refraction.glsl"
#include "/lib/water_refraction_transport.glsl"

bool waterResolveScalar(float value) {
    return !isnan(value) && !isinf(value);
}
bool waterResolveSnapshot(ivec2 pixel, ivec2 size, out vec3 radiance, out vec3 position) {
    radiance = vec3(0.0);
    position = vec3(0.0);
    vec4 sampleColor = texelFetch(colortex5, pixel, 0);
    float sampleDepth = texelFetch(colortex6, pixel, 0).r;
    float opaqueDepth = texelFetch(depthtex1, pixel, 0).r;
    if (!waterTraceFinite4(sampleColor) || sampleColor.a != 1.0
        || any(lessThan(sampleColor.rgb, vec3(0.0)))
        || any(greaterThan(sampleColor.rgb, vec3(65504.0)))
        || !waterResolveScalar(sampleDepth) || sampleDepth < 0.0 || sampleDepth >= 1.0
        || sampleDepth != opaqueDepth) return false;
    if (!waterTraceUnproject(pixel, sampleDepth, size, position)) return false;
    radiance = sampleColor.rgb;
    return true;
}
vec3 waterReflectedAtmosphere(vec3 radiance, vec3 startView, vec3 endView) {
#if FOG_ENABLED == 0
    return radiance;
#else
    // Integrate the reflected air segment in its own world-height interval.
    // FOG_START is a camera-path artistic exemption, not a second exemption here.
    float distance = length(endView - startView);
    float startY = float(cameraPositionInt.y) + cameraPositionFract.y + viewToPlayerPosition(startView).y;
    float endY = float(cameraPositionInt.y) + cameraPositionFract.y + viewToPlayerPosition(endView).y;
    if (!waterResolveScalar(distance) || !waterResolveScalar(startY) || !waterResolveScalar(endY)) return radiance;
    float density = (fogHeightDensity(startY) + 4.0 * fogHeightDensity((startY + endY) * 0.5)
                   + fogHeightDensity(endY)) / 6.0;
    float eyeSky = smoothstep(0.0, 0.5, clamp(float(eyeBrightnessSmooth.y) / 240.0, 0.0, 1.0));
    float weather = 1.0 + max(FOG_RAIN_BOOST, 0.0) * clamp(rainStrength, 0.0, 1.0);
    float opticalDepth = max(FOG_DENSITY, 0.0) * distance * density * weather
                       * celestialEnvironmentWeight() * eyeSky;
    float transmission = exp(-clamp(opticalDepth, 0.0, 80.0));
    vec3 atmosphere = applyAuroraSky(celestialUnit(endView - startView), fogColor, fogColor);
    return mix(atmosphere, radiance, transmission);
#endif
}
vec3 resolveWaterOptics(vec3 nativeScene, ivec2 pixel, ivec2 size) {
    // Every unsupported case keeps native transparent blending, including overlays,
    // multiple water layers, underwater views and non-water translucent materials.
    if (any(lessThanEqual(size, ivec2(0))) || any(lessThan(pixel, ivec2(0)))
        || any(greaterThanEqual(pixel, size))
        || any(notEqual(size, textureSize(colortex5, 0)))
        || any(notEqual(size, textureSize(colortex6, 0)))
        || any(notEqual(size, textureSize(colortex7, 0)))
        || any(notEqual(size, textureSize(colortex8, 0)))
        || any(notEqual(size, textureSize(colortex9, 0)))
        || any(notEqual(size, textureSize(depthtex0, 0)))
        || any(notEqual(size, textureSize(depthtex1, 0)))) return nativeScene;
    float environment = celestialEnvironmentWeight();
    if (!waterResolveScalar(environment) || environment <= 0.0
        || !waterResolveScalar(rainStrength) || !waterTraceFinite3(upPosition)
        || !waterTraceFinite3(shadowLightPosition) || !waterTraceFinite3(fogColor)) return nativeScene;
    if (max(max(abs(upPosition.x), abs(upPosition.y)), abs(upPosition.z)) <= 1e-6
        || max(max(abs(shadowLightPosition.x), abs(shadowLightPosition.y)), abs(shadowLightPosition.z)) <= 1e-6) return nativeScene;
    vec4 surface = texelFetch(colortex7, pixel, 0);
    vec4 ownership = texelFetch(colortex8, pixel, 0);
    float finalDepth = texelFetch(depthtex0, pixel, 0).r;
    float directShare = texelFetch(colortex9, pixel, 0).r;
    if (!waterTraceFinite4(surface) || !waterTraceFinite4(ownership)
        || abs(ownership.r * 255.0 - 1.0) > 0.002
        || any(lessThan(ownership.gb, vec2(0.0))) || any(greaterThan(ownership.gb, vec2(1.0)))
        || ownership.a != 0.0 || abs(dot(surface.xyz, surface.xyz) - 1.0) > 0.001
        || surface.a < 0.0 || surface.a >= 1.0 || !waterResolveScalar(finalDepth)
        || finalDepth < 0.0 || finalDepth >= 1.0
        || abs(surface.a - finalDepth) > 1.0 / 16777215.0
        || !waterResolveScalar(directShare) || directShare < 0.0 || directShare > 1.0) return nativeScene;
    vec3 surfaceView, bottomView, source;
    if (!waterTraceUnproject(pixel, surface.a, size, surfaceView)
        || !waterResolveSnapshot(pixel, size, source, bottomView)
        || texelFetch(colortex6, pixel, 0).r <= surface.a) return nativeScene;
    WaterParams params = waterParams();
    vec3 up = celestialUnit(upPosition);
    vec3 normal = normalize(surface.xyz);
    vec3 towardEye = celestialUnit(-surfaceView);
    float normalUp = dot(normal, up);
    float eyeUp = dot(towardEye, up);
    // The first owned transport path assumes a locally horizontal top interface.
    // Vertical waterfalls and near-tangent/underside rays remain native rendering.
    if (normalUp <= 0.65 || eyeUp <= 0.03) return nativeScene;
    vec3 worldDelta = mat3(gbufferModelViewInverse) * (surfaceView - bottomView);
    float drop = worldDelta.y * params.worldBlockMeters;
    float viewMeters = length(bottomView - surfaceView) * params.worldBlockMeters;
    if (!waterTraceFinite3(worldDelta) || !waterResolveScalar(viewMeters)
        || drop <= 0.001 || viewMeters <= 0.001 || viewMeters >= 64.0) return nativeScene;
    // Screen-border/depth-discontinuity confidence avoids replacing edge mixtures
    // by a full water solution. This is the same-ray fallback for refraction.
    vec2 edge = min(vec2(pixel) + 0.5, vec2(size - pixel) - 0.5);
    float confidence = smoothstep(0.0, 2.0, min(edge.x, edge.y))
                     * smoothstep(0.65, 0.90, normalUp) * smoothstep(0.03, 0.12, eyeUp)
                     * smoothstep(0.001, 0.03, drop) * (1.0 - smoothstep(48.0, 64.0, viewMeters));
    const ivec2 neighbors[4] = ivec2[4](ivec2(-1,0), ivec2(1,0), ivec2(0,-1), ivec2(0,1));
    for (int index = 0; index < 4; ++index) {
        ivec2 neighbor = pixel + neighbors[index];
        if (any(lessThan(neighbor, ivec2(0))) || any(greaterThanEqual(neighbor, size))) return nativeScene;
        vec3 neighborSource, neighborView;
        if (!waterResolveSnapshot(neighbor, size, neighborSource, neighborView)) return nativeScene;
        float difference = abs(neighborView.z - bottomView.z);
        confidence *= 1.0 - smoothstep(max(0.25, viewMeters * 0.05), max(0.5, viewMeters * 0.15), difference);
    }
    if (confidence <= 0.0) return nativeScene;
    float lightCosine = clamp(dot(celestialUnit(shadowLightPosition), up), 0.0, 1.0);
    float underwaterCosine = sqrt(max(1.0 - (1.0 - lightCosine * lightCosine)
                                      / (params.refractiveIndex * params.refractiveIndex), 0.0));
    float lightMeters = drop / max(underwaterCosine, 0.001);
    // The palette supplies a bounded sky source only where local skylight exists.
    vec3 skySource = vec3(0.0);
#if SKY_STYLE != 0
    skySource = auroraSkyLinear(up, fogColor) * clamp(SKY_BLEND, 0.0, 1.0) * environment;
#endif
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
    vec3 transmitted;
    if (float(WATER_CAUSTICS_STRENGTH)>0.0 && WATER_WAVES==1 && float(WATER_WAVE_STRENGTH)>0.0) {
        float causticGain = 1.0;
        if (directShare>0.0 && all(equal(textureSize(colortex1,0),size))) {
            vec4 receiver = texelFetch(colortex1,pixel,0);
            vec3 n = receiver.xyz*2.0-1.0;
            if (waterTraceFinite4(receiver) && receiver.a==1.0 && dot(n,n)>1e-12) {
                // Iris view transforms are rigid; normalize after world conversion.
                vec3 bedNormal = normalize(mat3(gbufferModelViewInverse)*normalize(n));
                vec3 lightWorld = mat3(gbufferModelViewInverse)*celestialUnit(shadowLightPosition);
                vec2 footprintX,footprintY;
                if(waterCausticPixelFootprint(bottomView,size,gbufferProjection,gbufferProjectionInverse,
                    gbufferModelViewInverse,footprintX,footprintY)) {
                    causticGain = waterShadowCausticGain(viewToPlayerPosition(surfaceView),
                        viewToPlayerPosition(bottomView),bedNormal,lightWorld,directShare,footprintX,footprintY);
                }
            }
        }
        transmitted = waterTransportRadiance(source, directShare, viewMeters, lightMeters,
                                                 ownership.g, ownership.b, skySource, causticGain);
    } else {
        transmitted = waterTransportRadiance(source, directShare, viewMeters, lightMeters,
                                             ownership.g, ownership.b, skySource);
    }
#else
    vec3 transmitted = waterTransportRadiance(source, directShare, viewMeters, lightMeters,
                                             ownership.g, ownership.b, skySource);
#endif
#if WATER_REFRACTION > 0
    transmitted = applyWaterRefractionTransport(transmitted,surfaceView,up,normal,
                                                lightCosine,ownership.gb,skySource);
#endif
    vec3 reflectedDirection = reflect(-towardEye, normal);
    float reflectedAbove = smoothstep(-0.10, 0.0, dot(reflectedDirection, up));
    float reflectionWeight = clamp(WATER_REFLECTION_STRENGTH, 0.0, 1.0)
                           * waterTransportFresnel(dot(normal, towardEye)) * environment;
    vec3 resolved = transmitted;
#if SKY_STYLE != 0
    float skyWeight = reflectionWeight * ownership.b * reflectedAbove * clamp(SKY_BLEND, 0.0, 1.0);
    if (skyWeight > 0.0) resolved = mix(transmitted, auroraSkyLinear(reflectedDirection, fogColor), skyWeight);
#endif
    // A missing sky/scene source releases its energy to transmission. A scene hit
    // needs no skylight, and attenuates its own air path before the camera path.
    if (reflectionWeight > 0.0 && reflectedAbove > 0.0) {
        ivec2 hitPixel;
        vec3 hitView, hitRGB;
        float hitDistance, hitConfidence;
        int steps, outcome;
        bool hit = traceWaterSceneClassified(surfaceView + up * 0.01, reflectedDirection,
                            hitPixel, hitView, hitRGB, hitDistance, hitConfidence, steps, outcome);
        // A known opaque intersection or malformed source cannot reveal sky.
        // Missing off-screen/range information remains an explicitly approximate fallback.
        if (outcome == WATER_TRACE_HIT || outcome == WATER_TRACE_OCCLUDED || outcome == WATER_TRACE_INVALID)
            resolved = transmitted;
        if (hit) {
            // A valid W1 pair can still contain unresolved early transparent color.
            // M1's negative share sentinel rejects that source for reflections too.
            float reflectedShare = texelFetch(colortex9, hitPixel, 0).r;
            if (waterResolveScalar(reflectedShare) && reflectedShare >= 0.0 && reflectedShare <= 1.0) {
                vec3 filteredRadiance = waterFilteredReflectionRadiance(hitPixel, hitView, hitRGB);
                vec3 segmentRadiance = waterReflectedAtmosphere(filteredRadiance, surfaceView, hitView);
                resolved = mix(resolved, mix(transmitted, segmentRadiance, reflectionWeight), hitConfidence);
            }
        }
    }
    // W1 is pre-atmosphere: replace with one fresh surface-to-camera fog evaluation.
    // Native fallback already has its own fog, so only then mix complete solutions.
    resolved = applyAtmosphericFog(resolved, surfaceView);
    if (!waterTraceFinite3(resolved) || any(lessThan(resolved, vec3(0.0)))
        || any(greaterThan(resolved, vec3(65504.0)))) return nativeScene;
    return mix(nativeScene, resolved, clamp(confidence, 0.0, 1.0));
}
#endif
#endif
