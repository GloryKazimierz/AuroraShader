# Milestone 5 Benchmark：Grid PCF vs Poisson PCF

> 中文学习版。英文原版：[MILESTONE_5_BENCHMARK.md](MILESTONE_5_BENCHMARK.md)

**状态：** 空白实测表。不要根据 validator 推断真实性能。

## 必须确认正确实验分支

目标分支：

```text
milestone-5-poisson-pcf
```

测试 pack 中应该看到：

- Hard
- 3x3 PCF
- 5x5 PCF
- Poisson PCF

## 环境

- 日期 / branch / commit：
- Minecraft / Fabric / Iris / Sodium：
- GPU / Driver / CPU：
- 其他 Mods / Resource Packs：
- World / Dimension：
- Coordinates / Yaw / Pitch：
- FOV：
- Resolution / Fullscreen：
- Render Distance / Simulation Distance：
- Time / Weather：
- VSync / FPS cap：
- measurement tool：
- warm-up time：
- observation time：
- shadow resolution：2048
- shadow distance：64
- bias：0.0002
- softness：1.0
- Debug：0

## 结果

| 模式 | Sample 数 | Softness | FPS | Frame Time | Edge Quality | Grid Artifact | Shimmer | 备注 |
|---|---:|---:|---:|---:|---|---|---|---|
| Hard | 1 | N/A | | | | | | |
| 3x3 PCF | 9 | 1.0 | | | | | | |
| 5x5 PCF | 25 | 1.0 | | | | | | |
| Poisson PCF | 8 | 1.0 | | | | | | |

## 控制变量

四种模式必须保持：

- 同一个 world；
- 同一个坐标；
- 同一个镜头方向；
- 同一个 FOV；
- 同一个时间和天气；
- 同一个 resolution；
- 同一个 render distance；
- 同一个 bias；
- 同一个 softness；
- 其他 shader 设置完全相同。

## 重点观察

不要只看“软不软”。

观察：

- straight edge；
- diagonal edge；
- 树叶；
- thin geometry；
- grazing surface；
- distant shadow；
- camera movement；
- sun movement。

特别记录：

```text
grid structure
jagged edge
noise
shimmer
light leak
shadow acne
peter-panning
```

## 测试思想

静态截图主要观察 spatial quality。

移动镜头主要观察 temporal stability。

性能测试与截图分开做，避免 screenshot/menu/recompile 干扰结果。

最后不要问“哪个数字最大”，而要回答：

> 在相同 visual quality 目标下，哪个 sampling strategy 更值得它的 GPU 成本？
