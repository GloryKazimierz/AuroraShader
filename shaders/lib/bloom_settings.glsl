#ifndef AURORA_BLOOM_SETTINGS_INCLUDED
#define AURORA_BLOOM_SETTINGS_INCLUDED
// M10: scene-linear bright-pixel bloom, independent of material emission.
#define BLOOM_ENABLED 1 // [0 1]
#define BLOOM_STRENGTH 0.08 // [0.0 0.04 0.08 0.12 0.2]
#define BLOOM_THRESHOLD 1.0 // [0.5 1.0 1.5 2.0] Peak scene-linear RGB, before exposure.
#define BLOOM_SOFT_KNEE 0.5 // [0.0 0.25 0.5 1.0] Transition half-width as a fraction of threshold.
#endif
