# 第 9 章：Advanced Shadow Mapping / 阴影进阶

## 1. 先统一基础

Shadow Mapping：

```text
receiverDepth
vs
shadow map storedDepth
```

AuroraShader 已经做过：

- Hard Shadow；
- 3x3 PCF；
- 5x5 PCF；
- Poisson PCF；
- Bias 基础。

这一章把面试常见的进阶方向串起来。

## 2. Resolution 与 Coverage

Shadow map texel 数固定。

如果：

```text
覆盖范围变大
分辨率不变
```

那么：

> 每平方米/每个 block 分到的 texel 变少。

结果：

- shadow 更粗；
- jagged 更明显。

反过来缩小 coverage：

> 近处清楚，但远处可能没 shadow。

这是 shadow map 最基本的 allocation trade-off。

## 3. Perspective Aliasing

Directional light 常用 orthographic shadow projection。

但 Camera 是 perspective。

于是：

> Camera 近处屏幕占很多 pixel，却可能只分到少量 shadow texel；远处反而浪费大量 shadow texel。

这叫一种 perspective aliasing。

CSM 就是针对这个问题。

## 4. Cascaded Shadow Maps

把 camera frustum 按 depth 分段：

```text
Near Cascade
Mid Cascade
Far Cascade
```

每段用不同 shadow map/projection。

Near：

> texel density 高。

Far：

> resolution 低一点，但 coverage 大。

难点：

- cascade split；
- transition seam；
- shimmering；
- stabilization；
- 多 pass 成本；
- memory。

## 5. Stable Cascades

Camera 稍微移动：

> light projection 也跟着微动。

shadow texel alignment 改变：

> shadow edge 会 shimmer。

常见方法：

> 把 projection/snapping 对齐 shadow texel grid。

牺牲一点自由度换 temporal stability。

## 6. Bias Family

常见：

- constant bias；
- slope-scaled bias；
- normal offset；
- receiver-plane bias。

注意：

> Bias 解决的是 self-shadow robustness，不是 soft filtering quality。

## 7. PCF

仍然记：

```text
先 comparison
再 average visibility
```

Kernel：

> 控制 footprint/sample count。

Pattern：

> 控制 sample distribution。

## 8. Poisson / Stochastic

不规则 pattern：

> 减少明显 grid structure。

但每 frame 随机：

> spatial artifact 可能少，temporal noise 可能多。

所以现代方法常搭：

```text
stochastic sampling
+
temporal accumulation
+
denoising
```

## 9. PCSS

流程：

```text
1. Blocker Search
2. Estimate Blocker Depth
3. Estimate Penumbra Width
4. Variable-radius PCF
```

目标：

```text
接触 caster → sharp
离 caster 更远 → soft
```

这就是 contact hardening。

PCSS 不是免费：

> blocker search + 大 filter 会更贵。

## 10. Variance Shadow Maps

VSM 不直接存普通 depth compare。

它保存 depth statistical moments，用概率 bound 估 visibility。

好处：

> 可以更自然地用普通 filtering，适合大 kernel。

问题：

> light bleeding。

面试一般知道思想即可，除非岗位专门做 shadow。

## 11. EVSM / Exponential

通过 exponential transform / additional moments 等方式改善某些 VSM 问题。

但会带来：

- precision；
- tuning；
- overflow/range 等新问题。

## 12. Ray-Traced Shadow

Ray Tracing：

> 直接从 shading point 朝 light 发 ray，看几何体是否挡住。

好处：

- 几何可见性直接；
- area light soft shadow 更自然。

问题：

- traversal cost；
- sample noise；
- denoising；
- temporal stability；
- acceleration structure。

所以 Raster Shadow Map 现在仍然非常重要。

## 13. Contact Shadow

低分辨率 shadow map 很容易丢掉脚底/接触处小阴影。

可以用：

- screen-space contact shadow；
- short ray；

补细节。

通常是 complement，不是完全替代大尺度 shadow map。

## 14. 面试问题

**Why CSM?**

> 把 shadow resolution 更合理分配给 camera near/far range。

**Why cascade shimmer?**

> Camera/light projection 微动导致 shadow texel alignment 变化。

**PCF vs PCSS?**

> PCF 固定 footprint；PCSS blocker search 后根据距离变化 filter radius。

**Why VSM light bleeding?**

> Statistical bound 对多层 separated depth distribution 可能高估 visibility。

**Raster vs Ray-Traced Shadow?**

> Raster 用 projected depth map；ray tracing 直接做 geometric visibility，但成本/噪声模型不同。

## 15. 你的项目路线

```text
Hard
→ 3x3
→ 5x5
→ Poisson
→ Better Bias
→ PCSS
→ CSM / Temporal Stability
```

这条路线非常合理，因为它是：

> correctness → filtering → sampling → robustness → physical-looking softness → large-scene scalability。
