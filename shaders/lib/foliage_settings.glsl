#ifndef AURORA_FOLIAGE_SETTINGS_INCLUDED
#define AURORA_FOLIAGE_SETTINGS_INCLUDED
// M18: shared terrain/caster displacement; strengths are fractions of small block amplitudes.
#define FOLIAGE_WIND 1 // [0 1] Gentle leaf and rooted-grass wind.
#define FOLIAGE_WIND_STRENGTH 0.5 // [0.0 0.25 0.5 1.0] Zero preserves the original geometry.
#define FOLIAGE_WIND_SPEED 1 // [0 1 2] Static pattern, normal motion, or double speed.
#endif
