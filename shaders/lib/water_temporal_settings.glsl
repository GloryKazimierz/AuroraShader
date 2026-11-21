#ifndef AURORA_WATER_TEMPORAL_SETTINGS_INCLUDED
#define AURORA_WATER_TEMPORAL_SETTINGS_INCLUDED
#include "/lib/water_optics_settings.glsl"
#define WATER_TEMPORAL 0 // [0 1] Reprojected water history, without camera jitter.
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_TEMPORAL == 1
#define AURORA_WATER_TEMPORAL_ACTIVE
#endif
#endif
#endif
