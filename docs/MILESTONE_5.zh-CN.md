# Milestone 5：Poisson Disk PCF

> 中文学习版。英文原版：[MILESTONE_5.md](MILESTONE_5.md)

**状态：** 实现在 `milestone-5-poisson-pcf` 分支上。Minecraft/Iris 实机测试与性能测量仍待完成；静态验证不能证明运行时正确。

## 发生了什么变化

Milestone 5 在现有 Shadow Mapping 管线中新增第四种过滤方式：

- 0 = Hard
- 1 = 3x3 PCF
- 2 = 5x5 PCF
- 3 = Poisson PCF

Poisson 版本使用 **8 个固定、不规则分布的 sample**，仍然调用同一个 `compareShadow()`。

| 模式 | 每次过滤的逻辑比较数 |
|---|---:|
| Hard | 1 |
| 3x3 PCF | 9 |
| 5x5 PCF | 25 |
| Poisson PCF | 8 |

默认仍是 3x3 PCF，softness = 1.0，bias = 0.0002。

## 为什么做 Poisson

规则网格像：

```text
x x x
x x x
x x x
```

它简单、稳定，但容易留下明显的行列结构。

Poisson 风格更像：

```text
   x      x

 x    x

      x      x

   x     x
```

关键不是“sample 变多了”，而是：

```text
sample count
和
sample distribution
是两个不同的问题
```

同样数量的 sample，仅仅因为位置不同，可能产生不同视觉结果。

## 固定 8-tap pattern

当前 offset：

```text
(-0.6314, -0.5843)   ( 0.9208,  0.3354)
(-0.4122,  0.8516)   ( 0.5840, -0.7758)
( 0.0908,  0.0974)   (-0.8603,  0.1847)
( 0.4062,  0.8639)   (-0.0979, -0.9729)
```

它们是不规则、分散在单位圆内部的教学用 pattern，不是“最优蓝噪声”，也不是 GPU 实时生成的 Poisson Disk。

每个 sample：

```text
texelSize = 1 / shadowMapDimensions
offsetUV = poissonOffset * texelSize * SHADOW_SOFTNESS
visibility += compareShadow(centerUV + offsetUV)
```

最后：

```text
visibility = sum / 8
```

仍然是先做 8 次独立的 0/1 深度比较，再平均 visibility。

## Softness 的含义

在这里 softness 是**采样半径倍率**。

它不会改变：

- sample 数量；
- shadow map 分辨率；
- blocker 距离；
- light size。

softness = 0 时，所有 offset 都乘以 0，因此 8 个 sample 全部落在中心点。

所以理论上会退化成 Hard 的结果。

## 为什么 Poisson 可能更好看

不是因为“8 > 25”，而可能因为：

- 分布更均匀；
- 没有明显的行列；
- 结构化误差被打散；
- 人眼通常更容易看到规则 band/grid artifact。

因此一个重要图形学思想是：

> 有时并不是减少误差，而是把误差变成不那么显眼的形式。

## 但 Poisson 并不自动更好

它仍然可能有：

- shimmer；
- noise；
- light leak；
- discrete stepping；
- repeated texel；
- temporal instability。

尤其当前使用 `texelFetch` + 整数 texel 定位，多个浮点 offset 最终可能落到同一个 texel。

所以：

```text
8 logical taps
不一定等于
8 unique depth texels
```

## 与 3x3 / 5x5 的公平比较问题

相同 softness 不代表相同 footprint。

- 3x3：最远约 sqrt(2) * S
- 5x5：最远约 sqrt(8) * S
- Poisson：半径不超过 S

因此默认 softness = 1 的对比并不是严格“同半径”实验。

Poisson 看起来更窄，不一定代表效果更差，它可能只是 footprint 更小。

## 性能

理论局部 lookup：

- Hard：1
- 3x3：9
- 5x5：25
- Poisson：8

但不要直接说：

> Poisson 比 5x5 快 3 倍。

因为整帧性能还取决于 cache、GPU occupancy、其他 pass、CPU bottleneck、分辨率和 screen coverage。

正确说法：

> Poisson 在这个实现里减少了 shadow filtering 的逻辑采样数，但整帧收益必须实测。

## 为什么这不是 PCSS

Poisson PCF：

```text
固定半径
+
不规则 sample 位置
```

PCSS：

```text
blocker search
+
估计 blocker distance
+
可变 penumbra radius
```

PCSS 想实现：

```text
接触处更锐利
远离 blocker 后更柔和
```

Poisson PCF 做不到 contact hardening。

## 验证

`tools/validate.py` 检查：

- SHADOW_FILTER=3；
- 8 个 Poisson comparison；
- visibility 范围；
- 全亮 / 全暗；
- softness=0；
- Hard/3x3/5x5 保持；
- transform / lighting 保持；
- UI option 有效。

它不是 GPU runtime test。

## 面试应该怎么解释

> I added an eight-tap Poisson-style PCF mode after implementing regular 3x3 and 5x5 grid PCF. The underlying shadow algorithm did not change: each tap performs a binary shadow-map depth comparison and I average the visibility results. The difference is sample distribution. Irregular samples can reduce visible grid structure with a smaller sample budget, although temporal stability and actual performance still need runtime measurement.

中文理解：

> 我先实现了规则的 3x3 和 5x5 PCF，然后加入 8-tap Poisson PCF。底层 Shadow Mapping 并没有改变，每个 sample 依然做深度比较，最后平均 visibility。变化的是采样点分布。不规则分布可能用更少 sample 减弱明显的网格结构，但真实画质、时间稳定性和性能仍然要实机测试。
