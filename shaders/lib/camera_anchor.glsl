#ifndef AURORA_CAMERA_ANCHOR_INCLUDED
#define AURORA_CAMERA_ANCHOR_INCLUDED
// Iris splits the unshifted camera position into floor(integer) and fraction.
// Share this anchor without assembling a large, low-precision world-space float.
uniform ivec3 cameraPositionInt;
uniform vec3 cameraPositionFract;
#endif
