#define FOG_ENABLED 1 // [0 1] Atmospheric fog in linear scene mode only.
#define FOG_DENSITY 0.006 // [0.0 0.002 0.004 0.006 0.01 0.02] Extinction per block near/below the reference height.
#define FOG_START 24.0 // [0.0 16.0 24.0 32.0 64.0] Clear distance around the camera in blocks.
#define FOG_BASE_HEIGHT 64.0 // [32.0 64.0 96.0 128.0] World height below which density reaches its maximum.
#define FOG_HEIGHT_FALLOFF 64.0 // [16.0 32.0 64.0 128.0] Height scale for density decay above the reference.
#define FOG_RAIN_BOOST 1.0 // [0.0 0.5 1.0 2.0] Extra density during rain; one means up to twice the clear-weather density.
