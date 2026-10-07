# Chapter 12: Graphics / Rendering Interview Question Bank

Use this as a recall checklist. Try answering aloud before reading notes.

## A. Rendering pipeline

1. Walk through the graphics pipeline from CPU draw submission to a displayed pixel.
2. What is the difference between a vertex and a fragment?
3. What does rasterization do?
4. What is clipping?
5. Why do we divide clip-space coordinates by w?
6. Graphics pipeline versus compute pipeline?
7. What work normally happens on CPU versus GPU?

## B. Coordinate spaces

8. Explain model, world, view, clip, NDC and screen space.
9. Why are multiple coordinate spaces useful?
10. What does the view matrix represent?
11. What does the projection matrix do?
12. What is an inverse projection matrix useful for?
13. Why can a shadow move with the camera when coordinate transforms are wrong?
14. Position w=1 versus direction w=0?

## C. Rasterization and depth

15. What are barycentric coordinates?
16. Why is perspective-correct interpolation needed?
17. What is the depth buffer?
18. What causes z-fighting?
19. Why does moving the near plane affect depth precision?
20. What is reversed-Z?
21. What is early-Z?
22. What is overdraw?
23. What does MSAA solve, and what does it not solve?

## D. Normals

24. Why use an inverse-transpose normal matrix?
25. Why renormalize normals after interpolation?
26. Face normal versus vertex normal?
27. What is tangent space?
28. What is a TBN matrix?
29. Why are tangent-space normal maps usually blue?
30. Does a normal map change geometry or silhouette?

## E. Textures

31. Nearest versus bilinear filtering?
32. What is minification?
33. Why do mipmaps reduce aliasing?
34. Bilinear versus trilinear?
35. What does anisotropic filtering solve?
36. What are texture derivatives used for?
37. What is texelFetch and when is it useful?
38. Why should normal maps not be sampled as sRGB color?
39. What problems can texture atlases create?

## F. Color and HDR

40. Why should lighting usually be done in linear space?
41. What is sRGB?
42. Why is pow(2.2) only an approximation?
43. What is HDR rendering?
44. Exposure versus tone mapping?
45. What is premultiplied alpha?
46. Why can low-precision gradients band?

## G. Forward and deferred rendering

47. Forward versus deferred rendering?
48. What is a G-buffer?
49. What is MRT?
50. Why can deferred rendering help with many lights?
51. Why is deferred rendering bandwidth-heavy?
52. Why is transparency difficult in classic deferred rendering?
53. Why can MSAA be expensive with deferred shading?
54. What is Forward+?
55. What is clustered shading?

## H. Lighting and PBR

56. Explain N dot L.
57. What is Lambert diffuse?
58. What is a BRDF?
59. What are N, L, V and H?
60. What do D, F and G mean in a microfacet BRDF?
61. What does roughness represent?
62. What is Fresnel reflectance?
63. What changes when a material is metallic?
64. What is energy conservation?
65. Direct versus indirect lighting?
66. What is image-based lighting?

## I. Shadows

67. Explain shadow mapping.
68. Why does shadow acne happen?
69. What is peter-panning?
70. What does shadow bias do?
71. What does PCF average?
72. Why does a larger PCF kernel soften edges?
73. Sample count versus sample distribution?
74. Why can Poisson sampling reduce grid artifacts?
75. Why can stochastic sampling shimmer?
76. PCF versus PCSS?
77. What is contact hardening?
78. Why use cascaded shadow maps?
79. Why can cascades shimmer?
80. Raster shadow maps versus ray-traced shadows?

## J. Performance

81. Why use frame time instead of FPS for optimization?
82. How would you determine whether a scene is CPU- or GPU-bound?
83. How can resolution scaling help diagnose bottlenecks?
84. Why are texture samples not a simple linear cost?
85. What is fill rate?
86. What is GPU branch divergence?
87. Are branches always bad?
88. What is memory bandwidth?
89. What is arithmetic intensity?
90. What causes synchronization stalls?
91. Why can many small draw calls be expensive?

## K. Debugging

92. How would you debug a black screen?
93. How would you debug a wrong normal?
94. How would you debug a shadow that follows the camera?
95. How would you debug an all-white shadow map?
96. What can cause NaNs in shaders?
97. Why are debug views valuable?
98. What would you inspect in RenderDoc?
99. How do you prevent renderer regressions?

## L. Your AuroraShader project

100. Explain AuroraShader Milestone 1 in 60 seconds.
101. Why did you use approximate linearization for exposure?
102. Explain your G-buffer layout.
103. Why store view-space normals?
104. Why use texelFetch for G-buffer metadata?
105. Explain your cave/torch lighting protection.
106. Explain receiver reconstruction from camera depth.
107. Walk through the receiver transform into shadow-map coordinates.
108. Why does shadow visibility only affect direct light?
109. Explain your constant shadow bias.
110. Explain Hard versus 3x3 PCF.
111. Why does softness zero approach Hard?
112. Explain 3x3 versus 5x5 cost.
113. Explain why 8-tap Poisson can look competitive with a larger grid.
114. What limitations remain in your shadow system?
115. What would you implement next and why?

## How to answer well

For each technical question, use this structure:

```text
1. Definition
2. Why it exists
3. How it works
4. Trade-off / failure mode
5. Example from your project
```

Example:

> PCF is a shadow-map filtering technique. It exists because a single depth
> comparison exposes shadow-map aliasing. It samples neighboring positions,
> performs the depth comparison independently for each sample, and averages the
> binary visibility values. A larger or wider kernel can smooth edges but increases
> sampling cost and is still not physically correct contact-hardening. In
> AuroraShader I implemented Hard, 3x3, 5x5 and Poisson-style PCF modes.

That answer is stronger than giving a one-line definition.
