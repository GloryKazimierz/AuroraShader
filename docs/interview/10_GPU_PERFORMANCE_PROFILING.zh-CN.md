# 第 10 章：GPU Performance & Profiling / 性能分析

## 1. 第一原则：不要靠猜优化

一个 shader 看起来代码多：

> 不代表它就是 bottleneck。

一个 texture sample 看起来简单：

> 也不代表它便宜。

性能必须 measure。

## 2. Frame Time 比 FPS 更重要

```text
frameTime(ms) = 1000 / FPS
```

例如：

- 60 FPS = 16.67 ms
- 120 FPS = 8.33 ms
- 144 FPS = 6.94 ms

FPS 是倒数，不线性。

所以优化比较最好说：

> 减少了多少 ms。

而不是只说：

> 多了 10 FPS。

## 3. CPU-bound vs GPU-bound

CPU-bound：

- GPU 有空闲；
- 降 resolution 改善不大；
- draw submission / scene logic 可能是瓶颈。

GPU-bound：

- 降 resolution 明显变快；
- 改 shader/pass 明显影响 frame time；
- GPU timeline 很满。

一帧不同阶段也可能动态换 bottleneck。

## 4. GPU Bottleneck 类型

可能是：

- vertex；
- raster；
- fragment；
- texture sampling；
- bandwidth；
- fill rate；
- compute；
- synchronization；
- ray traversal。

不要把所有性能问题都说成：

> shader 指令太多。

## 5. Resolution Scaling

如果降低 resolution：

> frame time 明显下降。

说明 screen-space / pixel work 很可疑。

例如：

- heavy fragment shader；
- G-buffer；
- fullscreen pass；
- post-process。

这是很实用的快速诊断。

## 6. Texture Sample 为什么不是简单乘法

M5：

```text
8 taps vs 25 taps
```

不能直接推：

> 25 一定比 8 慢 3.125 倍。

因为真实成本受：

- cache；
- locality；
- format；
- bandwidth；
- latency hiding；
- compiler；
- GPU architecture

影响。

所以你之前文档里“不乱报性能”是正确做法。

## 7. Overdraw

同一个 pixel 被多次 shade：

> 就是 overdraw。

常见：

- foliage；
- particles；
- transparent layers；
- 特效。

如果 fragment 很重：

> overdraw 非常贵。

## 8. Draw Call

很多小 draw：

> 可能 CPU submission overhead 很大。

策略：

- batching；
- instancing；
- indirect draw；
- GPU-driven rendering；
- 减少无意义 state change。

Vulkan 降低/改变 driver overhead，但：

> draw command 依然不是完全免费。

## 9. Synchronization Stall

CPU/GPU 最理想：

> 异步流水工作。

如果你频繁：

- GPU readback；
- 等 fence；
- 过度 barrier；
- queue 等待；

就会让 parallelism 消失。

Vulkan 面试很喜欢 synchronization，就是因为这些责任更显式。

## 10. Divergence

GPU threads 按 warp/wavefront/subgroup 执行。

如果一个 group：

```text
一半走 if
一半走 else
```

可能两个 path 都要跑。

但：

> GPU branch 一定慢

是过度简化。

如果 branch 很 coherent：

> 可能很便宜。

还是那句话：

> measure。

## 11. Arithmetic Intensity

一个 shader 可能：

- ALU-heavy；
- bandwidth-heavy。

Arithmetic intensity：

> 每移动一份 memory 做多少计算。

如果瓶颈是 bandwidth：

> 删几条乘法可能毫无意义，减少 buffer read/write 才有效。

## 12. 正确 Profiling Workflow

```text
1. 固定可重复场景
2. 记录环境
3. 测 frame time
4. 判断 CPU/GPU bound
5. GPU capture/profile
6. 找最贵 pass
7. 一次只改一个变量
8. 重测
9. 检查画质 regression
10. 保存 benchmark
```

这就是工程方法。

## 13. 工具

你以后至少知道：

- RenderDoc：frame capture/debug
- Nsight Graphics：NVIDIA
- Radeon GPU Profiler：AMD
- PIX：Direct3D
- Xcode GPU Tools：Metal

面试不要求全精通，但应该知道它们解决什么。

## 14. 面试问题

**FPS vs frame time?**

> frame time 是线性预算，FPS 是倒数。

**How know GPU-bound?**

> 看 resolution/workload sensitivity，再结合 CPU/GPU profiler timeline。

**Why texture samples expensive?**

> memory/cache/latency/bandwidth + shader work，但真实成本依赖 locality/hardware。

**Are GPU branches always bad?**

> No，主要问题是 divergence，coherent branch 可以很便宜。

**First rule of optimization?**

> Measure before and after.

## 15. 和 AuroraShader 的关系

你 M4/M5 benchmark 应该坚持：

```text
同场景
同 camera
同 settings
只换 filter
记录 frame time
记录 visual quality
```

比“25 sample 所以肯定慢很多”这种猜测专业得多。

面试官真正喜欢的是这种 performance methodology。
