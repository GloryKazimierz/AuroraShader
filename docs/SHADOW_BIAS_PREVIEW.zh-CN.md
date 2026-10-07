# 下一主题预习：Shadow Bias、Acne 与 Peter-Panning

> 中文学习版。英文原版：[SHADOW_BIAS_PREVIEW.md](SHADOW_BIAS_PREVIEW.md)

Milestone 4/5 主要研究：

> 去哪里 sample？

下一阶段研究：

> depth compare 应该容忍多少误差？

## 1. 为什么会有 Shadow Acne

理论上：

```text
receiverDepth <= storedDepth
```

就够了。

但 GPU rasterization、depth quantization、projection、reconstruction 都不是无限精度。

例如：

```text
storedDepth   = 0.50000
receiverDepth = 0.50003
```

实际上是同一个表面，却变成：

```text
0.50003 <= 0.50000
false
```

于是表面把自己判断成“被挡住”。

这就是典型 self-shadowing / shadow acne。

## 2. Bias 为什么有用

加入容差：

```text
receiverDepth - bias <= storedDepth
```

假设 bias = 0.0002：

```text
0.50003 - 0.0002 = 0.49983
```

现在：

```text
0.49983 <= 0.50000
true
```

错误 self-shadow 消失。

所以 bias 本质上是：

> 给不完美的 depth comparison 加一点容错。

## 3. 为什么不能一直加 bias

如果 bias 太大，本来应该被挡住的位置也可能被判成 lit。

结果：

> 阴影和物体接触处出现空隙，看起来物体浮起来了。

这叫：

```text
Peter-Panning
```

因此：

```text
bias 太小 → acne
bias 太大 → peter-panning
```

## 4. 为什么 Constant Bias 不完美

不同情况需要的容差不同：

- 不同 surface angle；
- 不同 light angle；
- 不同 shadow map resolution；
- 不同 scene scale；
- 不同 projection。

所以一个固定值只能是 compromise。

## 5. Grazing Angle 为什么更难

当表面相对光线角度很斜时，shadow map 上稍微移动一点，depth 可能变化很多。

因此同样的 texel offset：

```text
平坦正对光表面 → depth 变化小
斜着的表面 → depth 变化更大
```

这就是为什么 slope-aware bias 有意义。

## 6. Slope-Scaled Bias

直觉：

```text
depth slope 小
→ bias 小

depth slope 大
→ bias 大
```

概念式：

```text
bias =
constantBias
+
slopeFactor * depthSlope
```

不用现在死记 API 公式。

先记原因：

> depth 变化越快，比较时通常需要更大的容错。

## 7. Normal-Based Bias

另一种思路可以看：

```text
N dot L
```

当 N·L 很小：

> surface 相对 light 更 grazing。

于是可以增加 bias。

这仍然是 heuristic，不是万能解。

## 8. Receiver-Plane Bias

更进阶的方案会估计 receiver 在 shadow map 平面上移动时，depth 应该如何变化。

为什么它和 PCF 有关系？

因为 PCF 不只比较中心点，而是比较周围多个 sample。

周围 sample 的“正确 receiver depth”理论上也可能略有不同。

所以专业 shadow implementation 往往会把：

```text
filtering
和
bias
```

一起考虑。

## 9. PCF 不能解决 Bias

必须分清：

```text
soft filtering
!=
robust depth comparison
```

你可以同时拥有：

- PCF + acne；
- PCF + peter-panning；
- Poisson + acne；
- Poisson + peter-panning。

Sampling 和 Bias 是两个不同的问题。

## 10. 下一阶段实验建议

测试 bias：

```text
0
0.00005
0.0001
0.0002
0.0005
0.001
0.002
```

观察：

- flat ground；
- wall；
- grazing surface；
- thin geometry；
- contact shadow；
- distant shadow。

并且一定要移动镜头、改变时间。

## 11. 面试答案

**What causes shadow acne?**

> Small depth mismatches can make a surface incorrectly fail its own shadow test.

**Why does bias help?**

> Bias gives the comparison tolerance against numerical and sampling mismatch.

**What is peter-panning?**

> Excessive bias separates the shadow from its caster.

**Why is constant bias imperfect?**

> Different slopes and scene configurations require different tolerances.

**Does PCF solve acne?**

> No. PCF filters visibility; it does not fundamentally fix depth-comparison error.

## 12. 一句话记忆

> Bias 是给不完美 depth comparison 的容错：太小会 acne，太大会让阴影脱离物体。
