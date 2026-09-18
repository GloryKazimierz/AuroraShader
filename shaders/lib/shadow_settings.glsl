// Milestone 3B: preserve enable/bias controls; add only filter and radius.
#define SHADOWS_ENABLED // Apply shadows to directional light.
#define SHADOW_BIAS 0.0002 // [0.0 0.00005 0.0001 0.0002 0.0005 0.001 0.002] Receiver bias in normalized shadow depth.
#define SHADOW_FILTER 1 // [0 1] Hard or 3x3 PCF.
#define SHADOW_SOFTNESS 1.0 // [0.0 0.5 1.0 1.5 2.0] PCF spacing/radius in shadow-map texels.
