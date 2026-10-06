// Milestone 4: compare Hard, 3x3 PCF and 5x5 PCF with one shared path.
#define SHADOWS_ENABLED // Apply shadows to directional light.
#define SHADOW_BIAS 0.0002 // [0.0 0.00005 0.0001 0.0002 0.0005 0.001 0.002] Receiver bias in normalized shadow depth.
#define SHADOW_FILTER 1 // [0 1 2] Hard, 3x3 PCF, or 5x5 PCF.
#define SHADOW_SOFTNESS 1.0 // [0.0 0.5 1.0 1.5 2.0] Spacing between PCF taps in shadow-map texels.
