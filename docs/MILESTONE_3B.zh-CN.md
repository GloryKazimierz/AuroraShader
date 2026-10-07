# Milestone 3B：3x3 PCF Soft Shadows

> 中文学习版。英文原版：[MILESTONE_3B.md](MILESTONE_3B.md)

**状态：** 已经在 Minecraft/Iris 实机验证通过。

M3A 的 Hard Shadow 只有：

```text
0 或 1
```

M3B 开始做第一层 Shadow Filtering：

> 不只检查中心点，而是检查周围 3x3 共 9 个位置，再平均结果。

这就是 PCF。

---

## 1. PCF 到底做什么

每个 sample 都还是同一个 comparison：

```text
C(uv, z)
=
(z - bias <= storedDepth) ? 1 : 0
```

Hard：

```text
visibility = C(center)
```

3x3 PCF：

```text
visibility =
sum(C(neighbor_i)) / 9
```

重点：

> PCF 平均的是 comparison result，不是 depth。

---

## 2. 为什么会变软

假设阴影边缘处 9 个 sample：

```text
1 1 1
1 1 0
0 0 0
```

结果：

```text
5 / 9 ≈ 0.556
```

于是这个 pixel 不再是纯黑/纯白，而是中间 visibility。

视觉上就形成软过渡。

---

## 3. texelSize

shadow map 当前 2048 x 2048。

```text
texelSize = 1 / mapSize
```

也就是：

> 一个 shadow texel 在 UV 空间有多大。

3x3 sample offset：

```text
(-1,-1) ... (1,1)
×
texelSize
×
softness
```

---

## 4. SHADOW_SOFTNESS

softness 控制：

> sample 之间隔多远。

默认：

```text
1.0
```

softness = 0：

> 所有 sample collapse 到 center。

所以：

```text
PCF softness 0
≈
Hard
```

softness = 2：

> 每个 tap 离中心更远，过渡通常更宽。

注意：

> sample count 仍然是 9。

---

## 5. 为什么 Fractional Softness 可能没有想象中平滑

项目使用：

```text
texelFetch
```

最终读取离散整数 texel。

所以：

```text
softness = 0.5
```

时，不同浮点 offset 可能落到同一个 integer texel。

因此变化可能呈离散 step，而不是无限平滑。

---

## 6. Boundary Policy

每一个 PCF neighbor 如果超出 shadow map：

```text
return lit
```

好处：

- 不会 wrap；
- 不会 invalid read。

副作用：

> shadow coverage 边缘可能被亮化。

这是明确的工程 trade-off。

---

## 7. Lighting 没有被改坏

M3B 只改：

```text
visibility
```

没有改变：

- receiver reconstruction；
- coordinate transforms；
- G-buffer；
- ambient；
- block-light protection；
- direct-light equation；
- caster scope。

这是好的 milestone 设计：

> 一次只动一个主要变量。

---

## 8. Debug 5

Hard：

```text
black / white
```

PCF：

```text
black / gray / white
```

因为 visibility 现在可以是：

```text
0/9
1/9
2/9
...
9/9
```

所以 Debug 5 是理解 PCF 非常直观的工具。

---

## 9. 性能

Hard：

```text
1 depth lookup
```

3x3：

```text
最多 9 depth lookups
```

但这不意味着：

> 整个游戏慢 9 倍。

只是 shadow filtering 这一小块每个 eligible pixel 的 lookup 工作增加。

整帧还包括：

- geometry；
- other shaders；
- CPU；
- texture cache；
- resolution；
- visible coverage。

---

## 10. M3B 仍然不是真实 Soft Shadow

固定 3x3 PCF：

> 不知道 blocker 有多远，也不知道 area light 有多大。

所以它不会自然产生：

```text
contact sharp
far shadow soft
```

它只是 fixed-radius filtering。

---

## 11. 可能 Artifact

- stepped gray bands；
- shimmer；
- repeated taps；
- large-radius light bleeding；
- map-edge brightening；
- grazing-angle acne；
- bias 过大造成 shadow detachment。

所以：

> Filtering 并没有解决 Shadow Mapping 的全部问题。

---

## 12. 实机已经确认的行为

你之前已经确认：

- Hard 和 M3A baseline 一致；
- 3x3 PCF 确实让边缘变软；
- softness 有效果；
- softness = 0 接近 Hard；
- Hard ignores softness；
- Debug 5 出现 gray transition；
- Camera movement 时 shadow 不漂；
- sun/time 改变时 shadow 会跟；
- ambient / block light 保留；
- 没有重大 runtime rendering issue。

这是目前 `main` 的最新稳定 runtime-tested baseline。

---

## 13. 面试回答

**What is PCF?**

> Percentage-Closer Filtering samples multiple nearby shadow-map locations, performs a depth comparison at each one, and averages the binary visibility results.

**Why does PCF create soft edges?**

> Near a shadow boundary, some samples pass and some fail, producing fractional visibility.

**Does PCF blur shadow-map depth?**

> No. The comparisons happen first; PCF averages visibility results.

**Why can softness zero match Hard?**

> Every sampling offset collapses to the same center position, so all comparisons return the same value.

**Is 3x3 PCF physically correct?**

> No. It uses a fixed filter footprint and does not estimate area-light penumbra geometry.

---

## 14. 60 秒项目解释

> M3B 在已经验证过的 Hard Shadow Mapping 上加入 3x3 PCF。我保留原来的 receiver reconstruction、light-space transform、bias 和 lighting equation，只修改 shadow filtering。每个 pixel 在 shadow map 周围做 9 次独立 depth comparison，再平均 0/1 visibility，因此 shadow edge 可以产生 1/9 步进的灰度过渡。SHADOW_SOFTNESS 控制 sample spacing，而不是 sample count；softness=0 时所有 tap collapse 到中心，因此回到 Hard 的结果。这个版本已经通过 Minecraft runtime test，但它仍然是固定半径 PCF，不是物理正确 contact-hardening shadow。
