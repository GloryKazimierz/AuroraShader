# Milestone 5 学习笔记：真正读懂 Poisson PCF

> 中文学习版。英文原版：[MILESTONE_5_LEARNING_NOTES.md](MILESTONE_5_LEARNING_NOTES.md)

## 1. 先记住一句话

PCF 本质上是在问：

> Shadow map 周围多个位置里，有多少个位置认为当前 receiver 能看到光源？

Hard 只问一次。

3x3 问 9 次。

5x5 问 25 次。

Poisson 问 8 次，但 8 个位置不是整齐网格，而是不规则分布。

## 2. compareShadow()

最关键的底层函数不是 Poisson，而是：

```text
compareShadow()
```

它只负责一件事：

> 这个 sample 位置是 lit 还是 shadowed？

逻辑：

```text
receiverDepth - bias <= storedDepth
```

成立：

```text
1
```

不成立：

```text
0
```

所有 PCF 都只是反复调用这个函数。

## 3. filterShadow()

这个函数解决另一个问题：

> 我要在哪些位置调用 compareShadow()？

Hard：

```text
中心点 1 次
```

3x3：

```text
规则网格 9 次
```

5x5：

```text
规则网格 25 次
```

Poisson：

```text
不规则 disk pattern 8 次
```

然后平均。

## 4. shadowVisibility()

它解决的是：

> 当前屏幕上的 pixel，在光源的 shadow map 里到底对应哪里？

大致数据流：

```text
camera depth
↓
reconstruct view position
↓
player-relative position
↓
light view
↓
light clip
↓
divide by w
↓
shadow UV + shadow depth
↓
filterShadow()
```

所以三个函数可以这样记：

```text
shadowVisibility()
= 我在光源图像里的哪里？

filterShadow()
= 我要在周围检查哪些位置？

compareShadow()
= 某一个位置到底有光还是没光？
```

## 5. PCF 平均的不是 depth

这是面试高频点。

正确：

```text
average(compare(receiverDepth, depth_i))
```

错误理解：

```text
compare(receiverDepth, average(depth_i))
```

PCF 平均的是**比较结果**。

例如 9 个 sample：

```text
1 1 1
1 1 0
0 0 0
```

visibility：

```text
5 / 9 ≈ 0.556
```

这就是灰色过渡的来源。

## 6. Sample Count vs Sample Distribution

这两个概念必须分开。

Sample Count：

> 我做多少次测试？

Sample Distribution：

> 我把这些测试放在哪里？

例如 8 个 sample 可以排成很规则的结构，也可以像 Poisson 一样散开。

即使 count 一样，最终结果也可能不同。

## 7. 为什么规则网格会露馅

因为它有强烈方向性：

```text
x x x
x x x
x x x
```

当阴影边缘和网格方向发生某些关系时，误差可能表现成：

- band；
- repeated steps；
- grid artifact。

Poisson 不一定减少总误差，但可能把误差打散。

## 8. 为什么随机不等于更好

如果每帧 pattern 都乱变：

```text
frame 1: pattern A
frame 2: pattern B
frame 3: pattern C
```

空间结构可能更少，但时间上可能闪。

于是会出现：

```text
spatial artifact ↓
temporal shimmer ↑
```

现代实时渲染经常要靠 temporal accumulation / denoising 去处理这类问题。

## 9. texelFetch 的意义

当前实现使用离散 texel 读取。

优点：

- 行为容易理解；
- 每个 tap 对应清晰的 depth sample；
- 方便教学和 debug。

但浮点 offset 最终会转换为整数 texel。

所以几个 tap 可能撞在同一个 texel。

这解释了为什么：

> logical sample 数量和 unique texel 数量不是一回事。

## 10. Spatial vs Temporal Aliasing

Spatial aliasing：

- 一张截图里就能看到；
- 锯齿；
- blockiness；
- grid。

Temporal aliasing：

- 移动才明显；
- shimmer；
- flicker；
- crawling edge。

所以 Shader 不能只看截图。

## 11. 为什么 Poisson 还是 PCF

不要把 Poisson 当新算法。

底层仍然是：

```text
Shadow Mapping
→ depth compare
→ 多个 sample
→ average visibility
```

唯一变化是 sample pattern。

## 12. 与 PCSS 的区别

Poisson PCF：

```text
固定半径
+
更聪明的 sample distribution
```

PCSS：

```text
先找 blocker
+
估计 blocker distance
+
估计 penumbra
+
再用变化的 filter radius
```

PCSS 解决的是“软阴影半径应该多大”，Poisson 主要解决“固定 sample budget 应该怎么分布”。

## 13. 你现在必须能回答的问题

1. Shadow map 存了什么？
2. 为什么 receiver 必须转到 light space？
3. `compareShadow()` 返回什么？
4. PCF 平均什么？
5. 为什么 PCF 会产生 0 到 1 之间的数？
6. 3x3 为什么比 Hard 贵？
7. 5x5 为什么比 3x3 贵？
8. sample count 和 distribution 的区别？
9. Poisson 为什么可能减少 grid artifact？
10. 为什么 Poisson 仍可能 shimmer？
11. softness 控制什么？
12. 为什么 softness=0 会接近 Hard？
13. 为什么 Poisson PCF 不是 PCSS？
14. 为什么一定要做 motion test？

## 14. 一分钟面试回答

> I first implemented hard shadow mapping, then regular 3x3 and 5x5 PCF. PCF averages multiple binary shadow-map depth comparisons into fractional visibility. After that, I added an eight-tap Poisson-style pattern to study sample distribution rather than just sample count. Irregular samples can reduce visible grid structure with a smaller sample budget, but fixed-radius Poisson PCF can still shimmer and does not provide contact-hardening shadows like PCSS.

如果你能不看文档自然说出这段，你对 M5 的理解已经达到不错的 intern / junior Graphics 面试水平。
