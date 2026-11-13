// M7 styles only the sky background; stars and textured celestial bodies remain vanilla.
#include "/lib/sky_palette.glsl"
#include "/lib/aurora.glsl"
#include "/lib/celestial_glow.glsl"

uniform int renderStage;
uniform float viewHeight;
uniform float viewWidth;
uniform mat4 gbufferModelView;
uniform mat4 gbufferProjectionInverse;
uniform vec3 fogColor;
uniform vec3 skyColor;

in vec4 glcolor;

float fogify(float x, float w) {
	return w / (x * x + w);
}

vec3 calcSkyColor(vec3 pos) {
	float upDot = dot(pos, gbufferModelView[1].xyz); //not much, what's up with you?
	return mix(skyColor, fogColor, fogify(max(upDot, 0.0), 0.25));
}

vec3 screenToView(vec3 screenPos) {
	vec4 ndcPos = vec4(screenPos, 1.0) * 2.0 - 1.0;
	vec4 tmp = gbufferProjectionInverse * ndcPos;
	return tmp.xyz / tmp.w;
}

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 color;

void main() {
	if (renderStage == MC_RENDER_STAGE_STARS) {
		color = vec4(sceneFromDisplay(glcolor.rgb), glcolor.a);
	} else {
		vec3 pos = screenToView(vec3(gl_FragCoord.xy / vec2(viewWidth, viewHeight), 1.0));
#if SKY_STYLE == 1
        // Blend to the native void silhouette with the SAME continuous style weight.
        float voidWeight = clamp(SKY_BLEND, 0.0, 1.0) * celestialEnvironmentWeight();
        if (renderStage == MC_RENDER_STAGE_VOID && voidWeight > 0.0) {
#if SCENE_COLOR_MODE == 0
            color = mix(vec4(calcSkyColor(normalize(pos)), 1.0), glcolor, voidWeight);
#else
            color = mix(vec4(sceneFromDisplay(calcSkyColor(normalize(pos))), 1.0),
                        vec4(sceneFromDisplay(glcolor.rgb), glcolor.a), voidWeight);
#endif
            return;
        }
#endif
		color = vec4(applyAuroraSky(normalize(pos), calcSkyColor(normalize(pos)), fogColor), 1.0);
        // Only the upper background receives ribbons: never stars, void or sunset draws.
        // Keep the shared sky palette unchanged so terrain fog cannot contain aurora.
        if (renderStage == MC_RENDER_STAGE_SKY) {
            // M19 changes only background light; native sun/moon texture draws stay separate.
            color.rgb = applyCelestialGlow(pos, color.rgb);
            color.rgb = applyNightAurora(pos, color.rgb);
        }
	}
}
