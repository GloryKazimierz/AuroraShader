#ifndef AURORA_WATER_FOAM_SETTINGS_INCLUDED
#define AURORA_WATER_FOAM_SETTINGS_INCLUDED
#include "/lib/water_optics_settings.glsl"
#define WATER_FOAM 0 // [0 1 2] Off, local evidence, persistent high quality.
#ifdef AURORA_WATER_OPTICS_ACTIVE
#if WATER_FOAM > 0
#define AURORA_WATER_FOAM_ACTIVE
#if WATER_FOAM == 2
#define AURORA_WATER_FOAM_HISTORY
#endif
#endif
#endif
#endif
