#ifndef AURORA_WATER_UNDERWATER_SETTINGS_INCLUDED
#define AURORA_WATER_UNDERWATER_SETTINGS_INCLUDED
#include "/lib/water_optics_settings.glsl"
#define WATER_UNDERWATER 0 // [0 1] Experimental finite visible exit interfaces only.
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_UNDERWATER == 1
#define AURORA_WATER_UNDERWATER_ACTIVE
#endif
#endif
#endif
