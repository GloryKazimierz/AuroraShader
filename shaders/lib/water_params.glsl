#ifndef AURORA_WATER_PARAMS_INCLUDED
#define AURORA_WATER_PARAMS_INCLUDED
// Live parameters only: a small shared start, not the complete future water model.
struct WaterParams {
    float reflectionF0;          // Unitless artistic water-like normal reflectance.
    float worldBlockMeters;      // Calibration convention: one block equals one meter.
    float debugGapRangeMeters;   // White point of the ray-gap debug view, in meters.
};
WaterParams waterParams() {
    return WaterParams(0.02, 1.0, 16.0);
}
#endif
