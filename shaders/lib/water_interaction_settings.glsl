#ifndef AURORA_WATER_INTERACTION_SETTINGS_INCLUDED
#define AURORA_WATER_INTERACTION_SETTINGS_INCLUDED
#include "/lib/water_optics_settings.glsl"
#include "/lib/water_surface_settings.glsl"
#define WATER_INTERACTIONS 0 // [0 1]
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_INTERACTIONS == 1 && WATER_SURFACE_DETAIL == 1
#define AURORA_WATER_INTERACTIONS
#endif
#endif
#endif
