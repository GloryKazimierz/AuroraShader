#ifndef AURORA_WATER_CAUSTICS_SETTINGS_INCLUDED
#define AURORA_WATER_CAUSTICS_SETTINGS_INCLUDED
#include "/lib/water_optics_settings.glsl"
#include "/lib/shadow_settings.glsl"
#include "/lib/water_wave_settings.glsl"
#include "/lib/water_surface_settings.glsl"
#define WATER_CAUSTICS 0 // [0 1] Experimental shadow-space finite-beam caustics.
#define WATER_CAUSTICS_STRENGTH 0.6 // [0.0 0.3 0.6 1.0]
#ifdef AURORA_WATER_OPTICS_ACTIVE
#ifdef SHADOWS_ENABLED
#if WATER_CAUSTICS == 1
#define AURORA_WATER_CAUSTICS_ACTIVE
#endif
#endif
#endif
#endif
