#ifndef AURORA_CLOUD_SETTINGS_INCLUDED
#define AURORA_CLOUD_SETTINGS_INCLUDED
// M12 styles native cloud colors/atmosphere without changing cloud geometry.
#define CLOUD_STYLE 1 // [0 1] Zero restores the entire M11 cloud source.
#define CLOUD_COLOR_STRENGTH 0.6 // [0.0 0.3 0.6 1.0] Tint only; fog has its own switch.
#define CLOUD_FOG 1 // [0 1] Also requires global atmospheric fog.
#endif
