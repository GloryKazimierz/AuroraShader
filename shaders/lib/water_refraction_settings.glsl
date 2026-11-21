#ifndef AURORA_WATER_REFRACTION_SETTINGS_INCLUDED
#define AURORA_WATER_REFRACTION_SETTINGS_INCLUDED
// Staged defaults only; production adoption waits for M2 validation.
// 0: same-ray; 1: proven planar only; 2: planar + experimental cached128;
// 3: RGB planar only. Unknown ordinary/RGB tiles fall back without marching.
// Cost of the new producer+resolve remains to be measured.
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
