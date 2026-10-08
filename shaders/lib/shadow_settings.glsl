// Milestone 6: receiver bias strategy is independent of filter distribution.
#define SHADOWS_ENABLED // Apply shadows to directional light.
#define SHADOW_BIAS 0.0002 // [0.0 0.00005 0.0001 0.0002 0.0005 0.001 0.002] Receiver bias in normalized shadow depth.
#define SHADOW_BIAS_MODE 0 // [0 1] Constant or angle-aware receiver bias.
#define SHADOW_BIAS_MIN 0.0001 // [0.0 0.00005 0.0001 0.0002 0.0005 0.001 0.002] Angle-aware lower bound in normalized depth.
#define SHADOW_BIAS_MAX 0.0005 // [0.0 0.00005 0.0001 0.0002 0.0005 0.001 0.002] Angle-aware upper bound in normalized depth.
#define SHADOW_FILTER 1 // [0 1 2 3] Hard, 3x3 PCF, 5x5 PCF, or Poisson PCF.
#define SHADOW_SOFTNESS 1.0 // [0.0 0.5 1.0 1.5 2.0] Grid tap spacing or Poisson disk radius multiplier, in shadow-map texels.
