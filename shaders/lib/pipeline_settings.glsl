#ifndef AURORA_PIPELINE_SETTINGS_INCLUDED
#define AURORA_PIPELINE_SETTINGS_INCLUDED
// Scene storage/compositing contract, independent from artistic sky settings.
#define SCENE_COLOR_MODE 1 // [0 1] M7 display/LDR or linear/HDR scene composition.
#define TONE_MAPPING 1 // [0 1] Linear clip or peak-based exponential shoulder.
#define TONEMAP_KNEE 0.6 // [0.4 0.6 0.8] Linear intensity at which highlight compression begins.
#endif
