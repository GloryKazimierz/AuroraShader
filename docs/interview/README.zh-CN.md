# Graphics / Rendering Engineer 面试学习路线

这套资料把 AuroraShader 从“项目文档”扩展成一套系统的 Graphics / Rendering
Engineer 面试学习路线。

目标不是背定义，而是做到：

> 看见一个图形学概念 → 知道它解决什么问题 → 知道数据怎么流 → 知道哪里容易错 → 能用自己的项目解释。

## 推荐顺序

1. [GPU Rendering Pipeline / GPU 渲染管线](01_RENDERING_PIPELINE_GPU.zh-CN.md)
2. [Coordinate Spaces & Matrices / 坐标空间与矩阵](02_COORDINATE_SPACES_MATRICES.zh-CN.md)
3. [Rasterization, Interpolation, Depth / 光栅化、插值与深度](03_RASTERIZATION_DEPTH_INTERPOLATION.zh-CN.md)
4. [Normals & Tangent Space / 法线与切线空间](04_NORMALS_TANGENT_SPACE.zh-CN.md)
5. [Textures, Filtering, Mipmaps / 纹理采样与 Mipmap](05_TEXTURES_FILTERING_MIPMAPS.zh-CN.md)
6. [Color, Gamma, HDR, Tone Mapping / 颜色空间与 HDR](06_COLOR_GAMMA_HDR_TONEMAPPING.zh-CN.md)
7. [Forward vs Deferred, MRT, G-buffer / 前向与延迟渲染](07_FORWARD_DEFERRED_GBUFFER.zh-CN.md)
8. [Lighting, BRDF, PBR / 光照与 PBR 基础](08_LIGHTING_BRDF_PBR.zh-CN.md)
9. [Advanced Shadow Mapping / 阴影进阶](09_SHADOWS_ADVANCED.zh-CN.md)
10. [GPU Performance & Profiling / GPU 性能分析](10_GPU_PERFORMANCE_PROFILING.zh-CN.md)
11. [GLSL & Graphics Debugging / Shader 调试](11_GLSL_DEBUGGING.zh-CN.md)
12. [Graphics Interview Question Bank / 面试题库](12_GRAPHICS_INTERVIEW_QUESTION_BANK.zh-CN.md)

英文总目录：[README.md](README.md)

## 学完以后你应该做到什么

你应该能从一帧开始解释：

```text
CPU 提交 draw
→ vertex processing
→ clip / projection
→ rasterization
→ interpolation
→ fragment shading
→ depth/blending
→ render targets
→ post-process
→ final image
```

同时能解释：

- 一个点为什么要经过 Model / View / Projection；
- 为什么 normal 不能总是直接乘 model matrix；
- perspective-correct interpolation 为什么存在；
- depth buffer 为什么会 Z-fighting；
- mipmap 为什么既是画质问题也是性能问题；
- gamma space 和 linear space 为什么不能混；
- Forward 和 Deferred 为什么各有优缺点；
- Lambert、BRDF、PBR 到底是什么关系；
- Shadow Acne、PCF、Poisson、PCSS、CSM 各解决什么；
- GPU bottleneck 到底怎么判断；
- Shader 黑屏时应该从哪里开始排查。

面试时最重要的不是 API 函数名，而是能稳定回答三个问题：

1. **这个技术解决什么问题？**
2. **数据在 pipeline 里怎么流？**
3. **它带来了什么 trade-off / artifact？**

AuroraShader 现在已经可以给这些问题提供真实项目例子。
