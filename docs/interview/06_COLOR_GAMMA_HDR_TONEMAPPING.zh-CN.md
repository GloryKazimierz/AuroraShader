# 第 6 章：Color Space、Gamma、HDR 与 Tone Mapping

## 1. 为什么 Color Space 重要

RGB 数字不一定和真实光强成正比。

显示器/图片常用类似 sRGB 的非线性编码。

但是 lighting math 通常应该在：

```text
Linear Light
```

里算。

## 2. Linear vs Gamma/Display Encoded

真实光强：

```text
0.25 + 0.25 = 0.5
```

这在 linear space 有物理意义。

如果直接拿 gamma-encoded RGB 相加：

> 结果不代表真实光的叠加。

常见流程：

```text
Encoded Texture
↓
Decode to Linear
↓
Lighting / Blending / Exposure
↓
Tone Mapping
↓
Encode for Display
```

## 3. sRGB Texture

Albedo / color texture 往往是 sRGB。

正确标记后，GPU sampling 可以自动 decode 到 linear。

但这些通常不是 sRGB：

- normal map；
- roughness；
- metallic；
- depth；
- ID；
- mask。

它们是 data，不是 display color。

## 4. Gamma Correction 常见误区

大家经常说：

> Gamma correction = pow(color, 2.2)

这是教学近似。

更准确要区分：

- 输入 transfer function；
- linear rendering；
- 输出 display encoding。

真正 sRGB 还是 piecewise function，不是单纯 2.2 幂。

AuroraShader M1 用的是近似教学实现，所以面试要诚实说：

> approximate gamma handling, not a full color-managed pipeline.

## 5. HDR

HDR 的核心不是“屏幕一定特别亮”。

而是 renderer 中间值可以超过：

```text
[0,1]
```

例如：

```text
太阳高光 = 20
白墙 = 1
暗部 = 0.05
```

如果太早 clamp：

```text
20 → 1
```

信息直接丢了。

所以 HDR 常用 FP16 等 floating-point render target。

## 6. Tone Mapping

HDR scene 可能有 0~几十甚至更大范围。

显示器最终不能直接显示这些 scene-referred 数字。

Tone Mapping 做：

> 把大动态范围压到可显示范围，同时尽量保留对比和 highlight rolloff。

Exposure 和 Tone Mapping 不一样。

Exposure：

> 整体乘一个强度。

Tone Mapping：

> 非线性压缩动态范围。

## 7. Exposure

典型：

```text
linearColor *= 2^stops
```

+1 stop：

> 大约光强翻倍。

Auto Exposure：

> 根据场景亮度自动估计 exposure，并且常常随时间平滑变化。

## 8. Blending 为什么也应该考虑 Linear

如果在 gamma encoded 空间直接 alpha blend：

> 混合结果可能偏暗/偏亮。

更合理通常是：

```text
decode → blend linear → encode
```

## 9. Premultiplied Alpha

Straight alpha：

```text
RGB 与 alpha 分开
```

Premultiplied alpha：

```text
RGB 已经乘 alpha
```

Premultiplied 在 interpolation/filtering/compositing 中常有优势。

面试不一定要求背 blend factor，但要能解释两种 representation 的差异。

## 10. Banding

平滑渐变如果 precision 不够：

> 会一层一层出现色带。

可以通过：

- 更高精度；
- dithering；
- 避免过早量化；
- 合理 tone mapping

改善。

## 11. 面试问题

**Why linear lighting?**

> 因为真实光强的加法和乘法在 linear representation 才有正确意义。

**What is HDR rendering?**

> 中间 scene buffer 能保存超过最终 display range 的亮度信息。

**Exposure vs tone mapping?**

> Exposure 是整体强度 scale；tone mapping 是把 HDR 动态范围压进显示范围。

**Why no sRGB for normal map?**

> 因为 normal map 存的是向量数据，不是显示颜色。

## 12. 和 AuroraShader 的关系

M1 已经碰到：

- approximate gamma conversion；
- exposure；
- artistic color controls；
- clamp。

但仍然没有：

- HDR scene buffer；
- proper tone mapper；
- auto exposure。

这种“知道自己没做什么”在面试里很重要。

比硬说自己做了完整 HDR pipeline 更专业。
