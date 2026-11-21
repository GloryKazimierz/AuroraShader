#ifndef AURORA_WATER_REFRACTION_SETTINGS_INCLUDED
#define AURORA_WATER_REFRACTION_SETTINGS_INCLUDED
// 0: same-ray fallback; 1: 64-step; 2: 128-step; 3: three 128-step RGB rays.
// Every step currently validates a 3x3 footprint. No frame-time claim.
#define WATER_REFRACTION 0 // [0 1 2 3]
#if WATER_REFRACTION == 1
#define WATER_REFRACTION_STEPS 64
#else
#define WATER_REFRACTION_STEPS 128
#endif
#if WATER_REFRACTION == 3
#define WATER_DISPERSION 1
#else
#define WATER_DISPERSION 0
#endif
#endif
