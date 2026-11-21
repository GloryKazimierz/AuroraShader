#ifndef AURORA_WATER_NEARCLIP_SETTINGS_INCLUDED
#define AURORA_WATER_NEARCLIP_SETTINGS_INCLUDED
#include "/lib/water_caustics_settings.glsl"
// Experimental finite shadow evidence only. Default-off; isolated finite shallow-bed color experiment.
#define WATER_NEARCLIP 0 // [0 1]
#ifdef AURORA_WATER_CAUSTICS_ACTIVE
#if WATER_NEARCLIP == 1
#define AURORA_WATER_NEARCLIP_ACTIVE
#endif
#endif
#endif
