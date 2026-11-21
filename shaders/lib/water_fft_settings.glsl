#ifndef AURORA_WATER_FFT_SETTINGS_INCLUDED
#define AURORA_WATER_FFT_SETTINGS_INCLUDED
#include "/lib/water_wave_settings.glsl"
#include "/lib/water_surface_settings.glsl"
#define WATER_FFT 0 // [0 1] Optional two-cascade spectral normal field.
#ifdef IRIS_FEATURE_COMPUTE_SHADERS
#ifdef IRIS_FEATURE_CUSTOM_IMAGES
#if WATER_FFT == 1 && WATER_SURFACE_DETAIL == 1 && WATER_WAVES == 1
#define AURORA_WATER_FFT_ACTIVE
#endif
#endif
#endif
#endif
