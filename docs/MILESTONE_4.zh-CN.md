# Milestone 4：PCF 核大小实验

> 中文学习版。英文原版：[MILESTONE_4.md](MILESTONE_4.md)

**状态：** 实现已经完成代码审查，并扩展了结构/数值验证；Minecraft/Iris 实机测试与真实性能数据仍待完成。

这个里程碑建立在已经通过实机验证的 Milestone 3B 阴影管线之上，只改变一个变量：**PCF kernel 的大小**。我们保持 receiver 重建、shadow map、depth comparison、bias、caster scope 和 lighting equation 不变，对比 Hard、3x3 PCF 与 5x5 PCF。

## 目标

理解实时阴影里最基本的质量/成本权衡：

- Hard：每个有效 receiver 做 1 次比较。
- 3x3 PCF：最多 9 次比较。
- 5x5 PCF：最多 25 次比较。

更大的 kernel 并不会自动产生“物理正确”的软阴影。它只是对更多邻近的二值阴影判断取平均，因此边缘通常会更宽、更平滑，同时增加纹理读取和比较工作。

## 实现

`SHADOW_FILTER` 支持：

- 0 = Hard
- 1 = 3x3 PCF
- 2 = 5x5 PCF

核心循环：

```glsl
#if SHADOW_FILTER == 1
    const int kernelRadius = 1;
#else
    const int kernelRadius = 2;
#endif
```

每个 tap：

```text
offset = (x, y) * texelSize * SHADOW_SOFTNESS
visibility += compareShadow(center + offset)
```

最后：

```text
finalVisibility = visibleTapCount / totalTapCount
```

3x3 的 x/y 范围是 -1..1，共 9 个 sample；5x5 是 -2..2，共 25 个 sample。

## 哪些东西保持不变

- 2048 x 2048 shadow map。
- shadow coordinate reconstruction。
- 常量 normalized-depth bias。
- shadow caster 范围。
- ambient / block-light 保留逻辑。
- shadow visibility debug view。
- 超出 shadow map 的 sample 仍然按“有光”处理。

这样我们就能把实验变量尽量限制在 **PCF kernel size** 本身。

## 预期视觉结果

在完全相同的视角下：

1. Hard 应该有明显、锐利且可能带台阶的边缘。
2. 3x3 应出现较窄的灰度过渡。
3. 5x5 应出现更宽、更平滑的过渡。
4. 增大 softness 改变的是 sample 间距，而不是 sample 数量。
5. softness = 0 时所有 tap 都回到中心点，因此过滤结果应接近 Hard。

## 性能学习

| 模式 | 逻辑 tap 数 | 所有 tap 都在 map 内时的 shadow-depth lookup |
|---|---:|---:|
| Hard | 1 | 1 |
| 3x3 PCF | 9 | 9 |
| 5x5 PCF | 25 | 25 |

这些数字描述的是**一个有效像素的一次过滤计算**，不等于整个游戏一帧的总成本。

5x5 相比 3x3 的 lookup 数是：

```text
25 / 9 ≈ 2.78
```

但这不代表整个游戏会慢 2.78 倍，更不代表 25 tap 会让游戏慢 25 倍。真实 frame time 还取决于：

- 分辨率与实际被阴影影响的像素数；
- GPU texture cache；
- memory bandwidth / latency；
- 其他渲染 pass；
- CPU 是否已经成为瓶颈；
- VSync / FPS cap；
- driver / compiler 优化。

一个很重要的 Graphics Engineer 思维是：

> 局部 shader 成本 ≠ 整帧性能。

60 FPS 一帧约 16.7 ms，144 FPS 一帧约 6.9 ms。因此做实时图形时，哪怕每个像素只多几次操作，乘上几百万像素以后也可能变成值得关注的 GPU 成本。

真实性能请填写：[Milestone 4 Benchmark](MILESTONE_4_BENCHMARK.zh-CN.md)。

## GLSL / Iris 检查

当前实现保持 GLSL 330 compatibility：

- loop 使用整数变量；
- kernel radius 由编译期 `#if SHADOW_FILTER` 选择；
- Hard path 只有一次 comparison；
- 没有动态 kernel 数组；
- `textureSize(..., 0)` 获取真实 shadow map 大小；
- `texelFetch` 从 mip 0 读取离散 depth texel；
- 每个 sample 先独立比较，再平均 visibility。

验证脚本会检查 1/9/25 tap、不同 softness、全亮/全暗区域、边缘部分覆盖、map boundary、历史 transform 与 lighting 行为是否保持。

注意：`tools/validate.py` 是**结构和数值验证**，不是 GLSL 编译器，也不等于 Iris/GPU 实机成功。

## Minecraft 实机测试清单

1. 加载正确的 PCF 实验分支/pack，reload shader，并查看 Iris compile/link error。
2. 使用正常渲染，bias = 0.0002。
3. 找一个白天能看到明显柱子/屋檐阴影的位置。
4. 相同位置、相同镜头截图 Hard / 3x3 / 5x5。
5. 检查 5x5 边缘是否比 3x3 更宽。
6. 测试 softness = 0、0.5、1、1.5、2。
7. 确认 Hard 模式下改 softness 没有视觉影响。
8. 移动并旋转镜头，确认阴影仍附着在几何体上。
9. 改变时间，确认阴影跟随太阳/月亮。
10. 检查树叶、斜面、shadow map 边缘、洞穴和火把区域。
11. 同场景比较 Hard / 3x3 / 5x5 的 FPS 与 frame time。
12. 保存截图和真实性能数据。

## 面试应该怎么解释

你可以这样回答：

> Shadow map stores depth from the light's point of view. During shading, I transform the receiver into light space and compare its depth with the stored depth. A hard shadow uses one comparison, while PCF performs multiple nearby comparisons and averages the binary visibility results. Increasing the kernel size usually improves filtering quality, but also increases texture-sampling cost.

中文理解：

> Shadow Mapping 先从光源视角记录最近表面的深度。真正 shading 时，把当前像素对应的 receiver 转换到光源空间，与 shadow map 中记录的深度比较。Hard Shadow 只比较一次；PCF 会在周围比较多次，然后平均这些 0/1 的 visibility。kernel 越大通常越平滑，但采样成本也越高。

## 下一步

做完 kernel-size 对比后，不应该无脑继续扩大到 7x7、9x9。

更值得学习的方向是：

- Poisson / rotated sampling：减少规则网格感。
- Slope-scaled bias：减少 acne，同时避免过度 peter-panning。
- PCSS / contact hardening：让 softness 随 blocker/receiver 关系变化。
- Cascaded Shadow Maps：解决大范围室外方向光的 shadow resolution 分配问题。
