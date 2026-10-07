# 第 3 章：Rasterization、Interpolation、Depth 与精度

## 1. Rasterization 到底是什么

投影以后，GPU 已经知道 triangle 在屏幕上的位置。

Rasterization 接下来解决：

> 这个 triangle 覆盖哪些 screen sample？

大致：

```text
Triangle
↓
Coverage Test
↓
生成 Fragment
↓
Interpolation
↓
Fragment Shader
```

它是：

> 连续几何体 → 离散像素/sample

之间的桥梁。

## 2. Barycentric Coordinates / 重心坐标

Triangle 内一点可以表示成：

```text
P = aA + bB + cC
a + b + c = 1
```

a、b、c 就是 barycentric weights。

同一组权重可以用来 interpolate：

- color；
- UV；
- normal；
- 其他 varying。

这是 triangle interpolation 的数学基础。

## 3. 为什么不能直接线性插值 UV

透视投影以后：

> 远处的部分在 screen space 被压缩。

如果直接在屏幕上对 UV 做普通 linear interpolation，texture 会扭曲。

所以需要：

> perspective-correct interpolation。

概念上：

```text
先 interpolate(attribute / w)
和 1/w

最后：
attribute =
interpolated(attribute/w)
/
interpolated(1/w)
```

现代 GPU 对默认 varying 一般自动处理。

面试重点不是背公式，而是理解：

> Perspective projection 让 screen-space linear interpolation 不再等价于 3D 中正确插值。

## 4. Smooth vs Flat

不是所有数据都应该 interpolate。

适合 smooth：

- UV；
- vertex color；
- normal（但之后要 normalize）。

适合 flat：

- object ID；
- material ID；
- triangle ID。

如果 material ID 被 smooth interpolate：

> 就会出现 3.2、4.7 这种毫无意义的值。

## 5. Depth Buffer

Depth buffer 保存每个 pixel/sample 的深度。

常见 LESS test：

```text
newDepth < storedDepth
→ pass
```

通过后，如果 depth write 开启：

> 新 depth 写回 buffer。

## 6. 为什么 Opaque Draw Order 不一定影响最终结果

有 depth test 后：

> 后画的东西如果在后面，会被 depth reject。

所以 opaque geometry 通常不要求严格 back-to-front 才“正确”。

但是 draw order 仍影响性能。

Front-to-back 往往：

> 更早填入近处 depth，让后面的 hidden fragment 更容易被 early reject。

## 7. Early-Z

GPU 可能在 fragment shader 真正执行前，就做 depth rejection。

如果发现：

> 这个 fragment 肯定被挡住。

就没必要跑昂贵 shader。

但某些 shader 行为会让 early-Z 变复杂，比如：

- 修改 fragment depth；
- 某些 discard；
- 某些 side effect。

面试可以这样理解：

> Early-Z 主要省 fragment work，不代表前面的 vertex/rasterization 成本完全不存在。

## 8. Z-fighting

两个表面非常接近：

```text
Surface A depth ≈ Surface B depth
```

depth buffer 精度有限。

于是有时 A 赢，有时 B 赢。

视觉：

- 闪烁；
- 条纹；
- 花屏式叠加。

这叫：

```text
Z-fighting
```

## 9. 为什么 Near Plane 很重要

Perspective depth precision 不是均匀分布。

通常 near 附近精度更多。

如果 near plane 设置成极小：

```text
near = 0.0001
far = 10000
```

会浪费很多有效 depth precision。

所以实际 renderer 不应该无脑把 near 往 0 推。

## 10. Reversed-Z

现代 renderer 常见：

```text
Reversed-Z
```

思路：

- near/far depth 方向反过来；
- 常搭配 floating-point depth；
- depth test 可能从 LESS 变 GREATER。

它可以显著改善远距离 depth precision。

具体实现受 API NDC convention 影响，不要背一个固定 OpenGL/DX 公式套所有系统。

## 11. MSAA

MSAA 一个 pixel 里有多个 coverage/depth sample。

它主要改善：

> triangle edge aliasing。

但不会自动解决：

- texture minification aliasing；
- specular aliasing；
- shader aliasing；
- temporal shimmer。

所以：

> Anti-aliasing 不是只有一个问题。

## 12. Overdraw

同一个 screen region 被多次 fragment 覆盖：

```text
back wall
+ particle
+ leaves
+ glass
+ effect
```

但最终只显示某个组合结果。

这些重复 fragment work 就是 overdraw。

如果 fragment shader 很贵：

> overdraw 会非常伤性能。

## 13. 和 AuroraShader 的关系

你已经碰到了：

- Shadow Map 的 depth precision；
- Shadow Acne 的 depth compare；
- Cutout leaves 的 discard；
- G-buffer exact texel read；
- 多个 fullscreen pass。

所以这一章不是“理论和项目无关”，而是你现在 renderer 的底层原因。

## 14. 面试问题

**What are barycentric coordinates?**

> Triangle 内 relative vertex weights，用来描述位置并 interpolate attributes。

**Why perspective-correct interpolation?**

> 因为 projection 对 depth 是非线性的，普通 screen-linear interpolation 会让 UV 等属性失真。

**What causes z-fighting?**

> 两个 surface 的深度差小到 depth buffer 无法稳定区分。

**How improve depth precision?**

> 合理 near plane、合适 depth format、必要时 reversed-Z，避免极端 near/far ratio。

**What is overdraw?**

> 同一 screen region 被多个 fragment 重复处理，而其中很多工作对最终可见结果没有贡献。

## 15. 你必须自己讲出来

```text
Triangle
→ Coverage
→ Barycentric / Perspective-correct Interpolation
→ Fragment
→ Depth Test
```

然后分别说明：

- interpolation 是 attribute 问题；
- depth precision 是 visibility 数值精度问题；
- overdraw 是性能问题。

这三件事不能混在一起。
