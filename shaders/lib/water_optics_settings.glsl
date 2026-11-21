#ifndef AURORA_WATER_OPTICS_SETTINGS_INCLUDED
#define AURORA_WATER_OPTICS_SETTINGS_INCLUDED
#include "/lib/water_settings.glsl"
#include "/lib/pipeline_settings.glsl"
#ifndef DEBUG_VIEW
#include "/lib/lighting_settings.glsl"
#endif
#define WATER_OPTICS 0 // [0 1]
#define WATER_TRACE_TILES 1 // [0 1]
#define WATER_FLOW 0 // [0 1]
#define WATER_BODY 0 // [0 1 2 3] Freshwater, glacial, forest or open sea.
#define WATER_CLARITY 1.0 // [0.5 1.0 2.0]
// Iris defines the feature macro only on drivers with independent blending.
#ifdef IRIS_FEATURE_PER_BUFFER_BLENDING
#if WATER_OPTICS == 1
#if WATER_STYLE == 1
#if SCENE_COLOR_MODE == 1
#if DEBUG_VIEW == 0
#define AURORA_WATER_OPTICS_ACTIVE
#endif
#endif
#endif
#endif
#endif
#endif
