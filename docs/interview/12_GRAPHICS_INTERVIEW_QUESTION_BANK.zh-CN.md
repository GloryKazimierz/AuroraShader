# 第 12 章：Graphics / Rendering Engineer 面试题库

建议：

> 先自己口头回答，再回前面章节查。

不要只“看懂答案”。

面试需要你把知识从脑子里主动取出来。

## A. Rendering Pipeline

1. 从 CPU 提交 draw 到屏幕 pixel，完整讲一帧 Graphics Pipeline。
2. Vertex 和 Fragment 有什么区别？
3. Rasterization 做什么？
4. Clipping 做什么？
5. 为什么 Clip Space 要除以 w？
6. Graphics Pipeline 和 Compute Pipeline 区别？
7. CPU 和 GPU 通常分别负责什么？

## B. Coordinate Spaces

8. Model / World / View / Clip / NDC / Screen 分别是什么？
9. 为什么需要多个 coordinate space？
10. View Matrix 是什么？
11. Projection Matrix 做什么？
12. Inverse Projection 有什么实际用途？
13. 为什么 transform 错时 Shadow 会跟 Camera 飘？
14. Homogeneous coordinate 中 position w=1、direction w=0 为什么？

## C. Rasterization / Depth

15. Barycentric Coordinates 是什么？
16. 为什么需要 perspective-correct interpolation？
17. Depth Buffer 做什么？
18. Z-fighting 为什么出现？
19. Near Plane 为什么强烈影响 depth precision？
20. Reversed-Z 是什么？
21. Early-Z 是什么？
22. Overdraw 是什么？
23. MSAA 能解决什么，不能解决什么？

## D. Normals

24. 为什么 Normal Matrix 要 inverse-transpose？
25. 为什么 interpolated normal 要重新 normalize？
26. Face Normal 与 Vertex Normal？
27. Tangent Space 是什么？
28. TBN 是什么？
29. Normal Map 为什么通常是蓝色？
30. Normal Map 会不会改变真正 geometry / silhouette？

## E. Textures

31. Nearest vs Bilinear？
32. Minification 是什么？
33. Mipmap 为什么减少 aliasing？
34. Bilinear vs Trilinear？
35. Anisotropic Filtering 解决什么？
36. Texture Derivative 有什么用途？
37. texelFetch 是什么，什么时候用？
38. 为什么 Normal Map 不能当普通 sRGB Color？
39. Texture Atlas 有哪些问题？

## F. Color / HDR

40. 为什么 Lighting 通常在 Linear Space 算？
41. sRGB 是什么？
42. 为什么 pow(2.2) 只是近似？
43. HDR Rendering 是什么？
44. Exposure vs Tone Mapping？
45. Premultiplied Alpha 是什么？
46. Banding 为什么发生？

## G. Forward / Deferred

47. Forward vs Deferred？
48. G-buffer 是什么？
49. MRT 是什么？
50. Deferred 为什么适合 many lights？
51. Deferred 为什么 bandwidth-heavy？
52. Transparency 为什么难？
53. MSAA 为什么在 Deferred 中可能贵？
54. Forward+ 是什么？
55. Clustered Shading 是什么？

## H. Lighting / PBR

56. N dot L 的几何意义？
57. Lambert Diffuse？
58. BRDF 是什么？
59. N/L/V/H 分别是什么？
60. Microfacet 的 D/F/G？
61. Roughness 是什么？
62. Fresnel 是什么？
63. Metallic 材质和 Dielectric 的 shading 有什么区别？
64. Energy Conservation 是什么？
65. Direct vs Indirect Lighting？
66. IBL 是什么？

## I. Shadows

67. 完整解释 Shadow Mapping。
68. Shadow Acne 为什么发生？
69. Peter-Panning 是什么？
70. Shadow Bias 做什么？
71. PCF 平均什么？
72. Larger PCF Kernel 为什么更软？
73. Sample Count vs Distribution？
74. Poisson 为什么可能减少 grid artifact？
75. Stochastic Sampling 为什么可能 shimmer？
76. PCF vs PCSS？
77. Contact Hardening 是什么？
78. CSM 为什么有用？
79. Cascade 为什么 shimmer？
80. Raster Shadow vs Ray-Traced Shadow？

## J. Performance

81. 为什么优化看 Frame Time 而不是只看 FPS？
82. 怎么判断 CPU-bound / GPU-bound？
83. Resolution Scaling 怎么帮助定位瓶颈？
84. Texture Sample 为什么不是简单线性成本？
85. Fill Rate 是什么？
86. Branch Divergence 是什么？
87. GPU Branch 一定坏吗？
88. Memory Bandwidth 是什么？
89. Arithmetic Intensity 是什么？
90. Synchronization Stall 为什么出现？
91. 很多小 Draw Call 为什么贵？

## K. Debugging

92. Black Screen 怎么查？
93. Wrong Normal 怎么查？
94. Shadow 跟 Camera 走怎么查？
95. Shadow Map 全白怎么查？
96. Shader NaN 常见来源？
97. Debug View 为什么重要？
98. RenderDoc 你会看什么？
99. 怎么防止 Renderer Regression？

## L. 你的 AuroraShader

100. 60 秒讲 M1。
101. Exposure 为什么近似做 linearization？
102. 讲 G-buffer layout。
103. 为什么存 View Space Normal？
104. 为什么 G-buffer 用 texelFetch？
105. Cave/Torch Protection 怎么工作？
106. Camera Depth 怎么 reconstruct receiver？
107. Receiver 怎么走到 Shadow UV？
108. 为什么 Shadow 只乘 Direct Light？
109. Constant Bias 是什么？
110. Hard vs 3x3 PCF？
111. Softness=0 为什么接近 Hard？
112. 3x3 vs 5x5 成本？
113. 8-tap Poisson 为什么可能和大 grid 竞争？
114. 现在 Shadow System 最大 limitation？
115. 下一步你会做什么，为什么？

## 推荐回答结构

每道题都尽量按：

```text
1. 定义
2. 为什么需要
3. 怎么工作
4. Trade-off / Artifact
5. 自己项目里的例子
```

例如问 PCF：

> PCF 是 Shadow Map 的 filtering 技术。Hard Shadow 单次 depth comparison 会直接暴露 shadow-map aliasing，所以 PCF 在附近多个位置分别做 depth comparison，再平均 0/1 visibility。Kernel 更大通常让边缘更平滑，但 sample cost 增加，而且固定半径 PCF 仍然不是物理正确 contact-hardening shadow。我在 AuroraShader 里先实现了 Hard、3x3、5x5，再做了 Poisson-style sample distribution 实验。

这种回答会比：

> PCF 就是软阴影。

强很多。
