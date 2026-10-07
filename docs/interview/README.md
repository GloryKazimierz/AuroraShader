# Graphics / Rendering Interview Study Roadmap

This folder expands AuroraShader into a structured interview-preparation curriculum.

The goal is not to memorize isolated definitions. Each chapter connects a core
graphics concept to code you have already written, common rendering bugs, and the
kind of explanation expected in a Graphics / Rendering Engineer interview.

## Recommended order

1. [GPU Rendering Pipeline](01_RENDERING_PIPELINE_GPU.md)
2. [Coordinate Spaces and Matrices](02_COORDINATE_SPACES_MATRICES.md)
3. [Rasterization, Interpolation, Depth and Precision](03_RASTERIZATION_DEPTH_INTERPOLATION.md)
4. [Normals, Normal Matrix and Tangent Space](04_NORMALS_TANGENT_SPACE.md)
5. [Textures, Filtering, Mipmaps and Anisotropy](05_TEXTURES_FILTERING_MIPMAPS.md)
6. [Color Spaces, Gamma, HDR and Tone Mapping](06_COLOR_GAMMA_HDR_TONEMAPPING.md)
7. [Forward vs Deferred Rendering, MRT and G-buffer](07_FORWARD_DEFERRED_GBUFFER.md)
8. [Lighting, BRDF and PBR Fundamentals](08_LIGHTING_BRDF_PBR.md)
9. [Advanced Shadow Mapping](09_SHADOWS_ADVANCED.md)
10. [GPU Performance and Profiling](10_GPU_PERFORMANCE_PROFILING.md)
11. [GLSL and Graphics Debugging](11_GLSL_DEBUGGING.md)
12. [Interview Question Bank](12_GRAPHICS_INTERVIEW_QUESTION_BANK.md)

Chinese index: [README.zh-CN.md](README.zh-CN.md)

## What you should be able to do after this series

You should be able to explain a frame from vertex submission to final pixels,
trace a point through model/view/projection/light spaces, explain why normals need
special treatment, reason about interpolation and depth precision, choose texture
filtering and mipmapping strategies, distinguish gamma/display space from linear
light, compare forward and deferred rendering, explain Lambert/BRDF/PBR concepts,
debug shadow artifacts, and discuss GPU bottlenecks without making unsupported
performance claims.

For interviews, the most important skill is not remembering every API call. It is
being able to answer three questions clearly:

1. What problem is this technique solving?
2. What data flows through the pipeline?
3. What trade-off or failure mode does the technique introduce?

The AuroraShader milestones give you concrete examples for all three.
