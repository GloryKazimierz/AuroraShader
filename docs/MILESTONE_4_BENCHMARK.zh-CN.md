# Milestone 4 Benchmark：基准测试记录表

> 中文学习版。英文原版：[MILESTONE_4_BENCHMARK.md](MILESTONE_4_BENCHMARK.md)

**状态：** 空白模板。还没有填写 Minecraft/Iris 实机结果。

## 首先确认你加载的是正确 checkout

PCF 实验 checkout：

```text
D:\MinecraftShaders\MyShader-pcf-kernels
```

原来的 `MyShader` junction 仍然指向另一个实验目录，所以不要把“加载错 pack”误认为是 PCF 代码没有生效。

测试时务必确认 Shader Settings 中能看到：

```text
Hard
3x3 PCF
5x5 PCF
```

并且所有对比都在**同一个 Minecraft 世界、同一套环境设置**下完成。

## 环境记录

- 日期 / Minecraft / Fabric / Iris / Sodium 版本：
- GPU / Driver / CPU：
- World / Dimension / Coordinates / Yaw / Pitch / FOV：
- Render Distance / Simulation Distance：
- Window Resolution / Fullscreen：
- Time of Day / Weather：
- Resource Packs / Other Mods：
- VSync / FPS Cap：
- Shadow Map Resolution：2048
- Shadow Distance：64
- Shadow Bias：0.0002（若修改请记录）
- Shadows Enabled：
- Debug View：0
- Softness：1.0
- Warm-up 时间：
- Measurement 时间：
- 测量工具：

## 结果表

| 模式 | Softness | FPS | Frame Time (ms) | 边缘质量 | Shimmer | 备注 |
|---|---:|---:|---:|---|---|---|
| Hard | N/A | | | | | |
| 3x3 PCF | 1.0 | | | | | |
| 5x5 PCF | 1.0 | | | | | |

如果没有直接的 frame-time 工具，可以用：

```text
estimated frame time ≈ 1000 / stable FPS
```

但要标注这是**估算**，不是 GPU profiler 测得的真实 GPU time。

尽量记录稳定范围，而不是某一个瞬间的最高 FPS。

## 控制变量测试流程

1. 三种模式使用完全相同的 Minecraft world 和 dimension。
2. 站在相同 coordinates，最好有柱子/屋檐产生清晰阴影。
3. 保持完全相同的 camera direction、yaw、pitch 和 FOV。
4. 保持相同 render/simulation distance，并等待 chunk 加载完成。
5. 保持相同时间和天气。
6. 保持相同窗口分辨率和 fullscreen 状态。
7. 除 Shadow Filtering 外，其他 shader 设置不变。
8. 每次切换 filter/recompile 后先让场景稳定，再观察至少 10–15 秒。
9. 记录稳定 FPS/frame-time 范围，并可反向再跑一次顺序，避免 warm-up/thermal 偏差。
10. 性能记录结束后再截图；截图动作本身不要混入 timing。
11. 单独做慢速移动镜头测试，用于观察 shimmer，不要和静止 benchmark 混在一起。

如需冻结世界环境，可以使用固定时间和天气，但记得记录并在测试后恢复。

## Runtime Acceptance

完成 Milestone 4 前至少确认：

- Hard / 3x3 / 5x5 都可以编译运行。
- Hard 与 3x3 没有破坏已经通过的 Milestone 3B 行为。
- 5x5 的过渡区域通常比 3x3 更宽。
- softness = 0 时 PCF 接近 Hard。
- Hard 忽略 softness。
- Debug 5 中 Hard 是二值，PCF 可以出现中间灰度。
- Camera movement / world-time change 时阴影仍附着在几何体上。
- 树叶、斜面、map boundary、洞穴、火把附近没有明显 regression。
- ambient/block light 在阴影中仍然存在。

在这些结果真正记录下来之前，不要把 Milestone 4 标记为“runtime tested”。
