# Shadow Mapping 学习总纲

> 中文学习版。英文原版：[SHADOW_MAPPING_STUDY_GUIDE.md](SHADOW_MAPPING_STUDY_GUIDE.md)

这份文档用于真正理解 Shadow Mapping、复习代码，以及准备 Graphics / Rendering Engineer 面试。

## 1. Shadow Mapping 到底解决什么问题

Lambert Lighting 只能告诉你：

```text
N dot L
```

也就是：

> 这个表面朝不朝向光？

但它不能回答：

> 光线中间有没有被别的物体挡住？

因此 Shadow Mapping 要解决的是**可见性 / 遮挡问题**。

## 2. 最核心思想

把光源想象成一台相机。

先从光源视角渲染整个场景，只记录 depth：

```text
shadow map
=
光源看到的每个方向上最近表面的深度
```

之后真正渲染屏幕时，把当前 receiver 也转换到光源视角。

比较：

```text
当前 receiver depth
vs
shadow map stored depth
```

如果 receiver 比 stored depth 更远：

> 前面已经有别的东西挡住光了。

所以它在阴影里。

## 3. 两个 Pass

### Pass A：Shadow Pass

从光源角度渲染场景。

最重要的结果：

```text
depth
```

不是最终颜色。

在你的项目里，`shadow.fsh` 基本就是 depth-only caster pass。

树叶这类 cutout texture 可以通过 alpha discard 让洞真正出现在阴影中。

### Pass B：Camera / Deferred Lighting Pass

对于相机当前看到的 pixel：

1. 读取 camera depth。
2. 重建 view-space position。
3. 转换到 player-relative/world-relative 空间。
4. 转到 light view。
5. 转到 light clip。
6. 做 homogeneous divide，也就是除以 w。
7. 把 NDC 从 [-1,1] 映射到 [0,1]。
8. 得到 shadow UV + receiver depth。
9. 与 shadow map 做比较。

这就是 `shadowVisibility()` 的核心职责。

## 4. 为什么 Coordinate Space 特别重要

图形学大量 bug 都来自：

> 两个 vector 看起来都对，但根本不在同一个空间。

例如做：

```text
dot(N, L)
```

时，N 和 L 必须处于兼容空间。

同理，receiver 必须被正确转换到 light-space，才能去查 shadow map。

面试时一个很强的习惯是：

> 每出现一个 position/vector，就说明它现在在哪个 coordinate space。

## 5. Hard Shadow

Hard Shadow 只做一次比较：

```text
visibility = compareShadow(center)
```

因此结果只有：

```text
0 = shadow
1 = lit
```

好处：

- 简单；
- 成本低；
- 很适合验证基础 Shadow Mapping 是否正确。

缺点：

- shadow map resolution 很容易暴露；
- 边缘锯齿、台阶明显。

## 6. PCF：Percentage-Closer Filtering

PCF 不直接模糊 depth。

它是：

> 在多个附近位置分别做 depth comparison，然后平均 0/1 visibility。

例如 3x3：

```text
1 1 1
1 1 0
0 0 0
```

总共 5 个 lit：

```text
visibility = 5 / 9
```

于是边缘出现中间灰度。

必须记住：

正确：

```text
average(compare(receiverDepth, depth_i))
```

不是：

```text
compare(receiverDepth, average(depth_i))
```

这是 PCF 最重要的概念之一。

## 7. 3x3 与 5x5

3x3：

```text
9 samples
```

5x5：

```text
25 samples
```

更大的 kernel：

- 通常过渡更宽；
- 往往更平滑；
- 但采样成本更高。

这就是典型：

```text
quality
vs
GPU cost
```

## 8. Softness 在你的项目里是什么

你的 softness 控制：

> sample spacing / filtering radius

它不改变 sample count。

例如 5x5：

softness = 1：

```text
-2 -1 0 +1 +2 texels
```

softness = 2：

```text
-4 -2 0 +2 +4 texels
```

所以更大 softness 可能：

- 阴影更宽；
- 但 light bleeding 更多；
- shimmer 更明显；
- contact shadow 更假。

## 9. 为什么 PCF 不是真正物理软阴影

真实 area light 的软阴影通常具有：

> 接触处锐利，离 blocker 越远 penumbra 越宽。

固定半径 PCF 不理解：

- blocker distance；
- receiver distance；
- light size。

所以它只是固定范围 blur-like visibility filtering。

PCSS 才开始尝试估计 blocker 与 penumbra。

## 10. Shadow Acne

假设：

```text
storedDepth = 0.50000
receiverDepth = 0.50003
```

虽然来自同一个实际表面，但精度误差导致：

```text
0.50003 <= 0.50000
false
```

于是表面错误地 shadow 自己。

表现：

- 黑色条纹；
- 斑点；
- moire；
- self-shadowing。

## 11. Bias

常见做法：

```text
receiverDepth - bias <= storedDepth
```

bias 是容差。

太小：

```text
acne
```

太大：

```text
peter-panning
```

也就是阴影离开物体，看起来物体“漂起来”。

## 12. 为什么 Grazing Surface 难

当表面相对光方向非常斜时，shadow-map 上移动一点点，depth 可能变化很多。

所以一个固定 bias 很难同时照顾：

- 正对光的面；
- grazing angle 的面。

这就是 slope-scaled bias 的动机。

## 13. Debug Shadow Pipeline

### 完全没有 shadow

检查：

- caster 是否进入 shadow pass；
- shadow map 是否有 depth；
- receiver reconstruction 是否正确；
- light matrices 是否正确；
- SHADOWS_ENABLED；
- receiver 是否落在 shadow map 内。

### Shadow 跟着 Camera 转

通常是：

> coordinate-space / reconstruction bug。

### 满地黑条

通常：

> bias 太小或 depth precision 问题。

### Shadow 离物体太远

通常：

> bias 太大。

### Shadow 边缘闪

可能是：

- shadow map resolution；
- unstable projection；
- discrete taps；
- light/camera motion；
- sampling pattern；
- temporal aliasing。

## 14. 代码阅读顺序

建议：

1. `shaders/shadow.vsh`
2. `shaders/shadow.fsh`
3. `shaders/lib/position.glsl`
4. `shaders/lib/shadow.glsl`
5. `shaders/lib/lighting.glsl`
6. `shaders/deferred.fsh`
7. `shaders/lib/shadow_settings.glsl`
8. `shaders/shaders.properties`

不要死记代码。

追踪数据流：

```text
geometry
↓
light depth

camera depth
↓
receiver position
↓
light coordinates
↓
depth comparison
↓
visibility
↓
direct lighting
```

## 15. 为什么不能一直扩大 Grid Kernel

N x N sample 数：

```text
3x3 = 9
5x5 = 25
7x7 = 49
9x9 = 81
11x11 = 121
```

成本是平方增长。

但更大的 kernel 并没有解决：

- shadow map resolution；
- contact hardening；
- temporal shimmer；
- physically correct penumbra。

所以继续暴力扩大通常不是最佳学习方向。

## 16. Poisson Sampling

规则 grid：

```text
x x x
x x x
x x x
```

Poisson：

```text
   x     x

 x     x

      x      x

   x     x
```

核心思想：

> sample 彼此保持一定分散，又避免明显行列结构。

优点：

- grid artifact 可能更少；
- 有机会用较少 sample 得到不错视觉结果。

缺点：

- 仍然是 approximation；
- 可能 noise；
- 可能 shimmer；
- 固定 pattern 仍然会有重复结构；
- 不会自动产生真实软阴影。

## 17. Randomized / Rotated Kernel

如果不同 pixel/frame 使用不同 rotation：

优点：

> 进一步打破 grid/pattern。

风险：

> spatial structure 变少，但 temporal shimmer 变多。

所以现代实时渲染常见思路：

```text
stochastic sampling
+
temporal accumulation
+
denoising
```

## 18. PCSS

PCSS 大致：

```text
1. blocker search
2. estimate blocker distance
3. estimate penumbra size
4. variable-radius PCF
```

目的：

```text
contact → sharper
farther away → softer
```

它仍然是 approximation，但比固定 radius PCF 更接近 area-light 阴影直觉。

## 19. Cascaded Shadow Maps

一个超大的 directional-light shadow map 很难同时满足：

- 近处高精度；
- 远处大范围。

CSM 把 camera view range 分段：

```text
near cascade
mid cascade
far cascade
```

近处给更多 texel density，远处牺牲分辨率换 coverage。

它解决的是：

> shadow resolution allocation

不是 soft shadow。

## 20. Spatial vs Temporal Quality

Still image 测：

- jagged edge；
- blockiness；
- grid；
- noise。

Motion 测：

- shimmer；
- flicker；
- crawling。

Graphics Engineer 不能只看截图。

## 21. 你这个项目当前真正学到了什么

M1：

> 后处理与 color control。

M2：

> G-buffer + deferred directional lighting。

M3A：

> 从 light POV 生成 depth，再进行 receiver comparison。

M3B：

> 3x3 PCF。

M4：

> kernel size / sample count / GPU cost。

M5：

> sample distribution / Poisson PCF。

下一阶段：

> bias robustness。

再之后：

> contact hardening / PCSS。

## 22. 高频面试题

### What is Shadow Mapping?

> Render depth from the light, transform the receiver into light space, and compare depths to determine visibility.

### What does PCF average?

> Binary depth-comparison visibility results.

### Why does PCF soften shadows?

> Near a boundary, some neighboring samples are lit and some shadowed, producing fractional visibility.

### What causes Shadow Acne?

> Small depth mismatches cause a surface to fail its own shadow comparison.

### What causes Peter-Panning?

> Excessive bias detaches shadows from their casters.

### Why can Poisson sampling help?

> Irregular distribution can make sampling error less visibly structured.

### Why is fixed-radius PCF not physically correct?

> It does not adapt filter width based on blocker distance, receiver distance, or light size.

### What does PCSS add?

> Blocker search and a variable filter radius for approximate contact hardening.

### What do Cascaded Shadow Maps solve?

> They allocate shadow-map resolution across near and far camera ranges.

## 23. 你应该能讲出的 60 秒版本

> I implemented a depth-based shadow mapping pipeline where I reconstruct each receiver, transform it into light space, and compare its depth against the shadow map. I first used a hard single-sample comparison, then implemented 3x3 and 5x5 PCF to study filtering quality versus texture-sampling cost. After that, I added an eight-tap Poisson-style pattern to study sample distribution and structured aliasing. I also studied bias-related artifacts such as shadow acne and peter-panning. The next step is to improve depth-comparison robustness before moving toward variable-penumbra methods such as PCSS.

中文理解：

> 我先做基础 Shadow Mapping：把屏幕上看到的 receiver 重建出来，转换到光源空间，再和 shadow map 深度比较。之后从 Hard Shadow 做到 3x3/5x5 PCF，研究过滤质量和 texture sampling 成本，再加入 8-tap Poisson pattern，学习 sample distribution 和规则采样 artifact。与此同时我开始研究 bias、shadow acne 和 peter-panning。下一步先把 depth comparison 做得更稳健，再进入 PCSS 这种可变 penumbra 方法。

如果这段你能自然说出来，你已经不只是“会调 shader”，而是真的开始理解实时阴影管线了。
