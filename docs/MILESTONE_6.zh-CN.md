# Milestone 6：阴影 Bias 的稳健性

状态：`milestone-6-shadow-bias` 基于最新 Milestone 5 实现，仍是实验版本。
**尚未确认 Minecraft/Iris 运行测试通过**，本分支不合并到 `main`。

配套资料：[学习与面试指南](SHADOW_BIAS_STUDY_GUIDE.zh-CN.md)、
[受控测试表](MILESTONE_6_BENCHMARK.zh-CN.md)、[英文技术版](MILESTONE_6.md)。

## 1. 为什么深度比较需要容差

Shadow map 记录光源看到的深度。接收阴影的表面称为 receiver：把它投影到
shadow map 后，如果它不比已记录的表面更远，就认为光能照到它。

问题在于，摄像机像素与阴影纹素并不对应同一个采样位置。再加上有限深度精度、
光栅化以及位置重建误差，同一表面在两次计算中得到的深度也可能略有差别。
结果是表面把自己误判成遮挡物，出现条纹、斑点或重复暗纹，这叫 **shadow acne**。

Bias 给比较增加一点容差，让微小误差不再造成错误遮挡。不过，容差过大也会忽略
真实遮挡：物体与影子之间出现间隙，像悬浮起来，这叫 **peter-panning**；
薄物体的影子还可能消失，或发生漏光。本阶段研究这项取舍，不承诺彻底消除伪影。
[微软的阴影伪影说明](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/common-techniques-to-improve-shadow-depth-maps)。

## 2. 两种策略与默认设置

| 设置 | 默认值 | 含义 |
|---|---:|---|
| `SHADOW_BIAS_MODE` | `0` | `0` Constant；`1` Angle-Aware |
| `SHADOW_BIAS` | `0.0002` | 原有固定深度容差 |
| `SHADOW_BIAS_MIN` | `0.0001` | 角度感知模式的较小端点 |
| `SHADOW_BIAS_MAX` | `0.0005` | 角度感知模式的较大端点 |

三个数值设置都提供 `0、0.00005、0.0001、0.0002、0.0005、0.001、0.002`。
它们的单位是**归一化阴影深度**，不是米或方块。过滤器默认仍为 3x3 PCF，
softness 仍为 `1.0`。

Constant 模式原样返回 `SHADOW_BIAS`，不使用法线、光方向或角度模式的上下限。
选择 `0.0002` 时，应复现 Milestone 5 的深度比较结果。固定值容易理解和复现，
但一个值难以兼顾不同朝向、投影、分辨率与场景。

## 3. 实际公式与数值保护

对有限的配置端点，Angle-Aware 模式使用：

```text
lo = clamp(min(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
hi = clamp(max(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
NdotL = clamp(dot(safeNormalView, safeLightDirectionView), 0, 1)
angleFactor = 1 - NdotL
effectiveBias = clamp(mix(lo, hi, angleFactor), lo, hi)
lit = receiverDepth - effectiveBias <= storedDepth
```

上下限填反时先排序；两个端点相等时，角度模式也退化为固定容差。
法线和光方向在归一化前都检查 NaN、无穷大，以及最大绝对分量是否不大于 `1e-6`。
若任一向量无效或退化，就按 `NdotL = 0` 处理，选择最大容差。
否则先除以各自的最大绝对分量，再归一化，避免大数在长度平方中溢出。
点积与最终 bias 都有明确的 clamp。

默认端点下：

| N dot L | 1.00 | 0.75 | 0.50 | 0.25 | 0.00 |
|---|---:|---:|---:|---:|---:|
| 实际 bias | 0.0001 | 0.0002 | 0.0003 | 0.0004 | 0.0005 |

正对光源时采用较小值；掠射角时趋向较大值。背光面的负点积也被限制到零。
这样做的直觉是：掠射表面在相邻阴影纹素之间可能存在较大的深度变化，微小的
采样位置偏差就足以造成自遮挡。但 N dot L 只是朝向指标，不是实际误差测量。

## 4. 坐标空间必须一致

G-buffer 解码出的法线属于**摄像机视图空间（view space）**。
光方向来自同样处于 view space 的 Iris `shadowLightPosition`，指向当前投影阴影
的天体光源：白天为太阳，夜间为月亮。两者作为方向归一化，不加入相机平移。
[Iris uniform 参考](https://shaders.properties/current/reference/uniforms/overview/)。

真正比较的 receiverDepth 与 storedDepth 则属于**归一化阴影深度空间**。
用 view space 计算角度，并不意味着把这两个深度改成 view-space 深度。
已有的摄像机深度重建、player-relative 变换、`shadowModelView` 与
`shadowProjection` 都保留。本阶段只调整比较容差，不移动接收点或修改投影。

## 5. 为什么它不是硬件 slope-scaled bias

API 的 slope-scaled raster depth bias 通常依赖三角形在光栅坐标中的深度梯度。
例如 Direct3D 把与深度格式相关的常数项，加上最大水平/垂直深度斜率乘以系数，
用于光栅化阶段的深度偏移。[Direct3D 定义](https://learn.microsoft.com/en-us/windows/win32/direct3d11/d3d10-graphics-programming-guide-output-merger-stage-depth-bias)。

本项目没有测量该梯度，也没有开启新的 polygon offset 状态，而是在 receiver
查询 shadow map 时，根据法线与光方向减去一个有界容差。因此准确名称是
**angle-aware receiver bias**，或 **normal-based bias heuristic**。
二者都试图缓解斜面问题，但不是相同算法。着色法线还可能不同于真实几何法线，
进一步说明它只能作为启发式，不能称为物理正确或硬件斜率偏移的等价实现。

## 6. Bias 与过滤解决不同的问题

每个 receiver 只计算一次 effectiveBias，所有 tap 共用它。
Hard、3x3、5x5、Poisson 仍分别执行 **1、9、25、8** 次逻辑比较，
采样分布和 softness 语义不变。PCF 平均的是二值可见性结果，不是原始深度。
越界采样仍按受光处理；softness 为零仍等于中心比较；Hard 仍忽略 softness。

过滤回答“到哪里取样、取多少样”；bias 回答“每次深度比较允许多大误差”。
PCF 可以把错误边缘变柔，却不能纠正错误比较；Poisson 也不能靠改变采样分布
解决 bias。较宽的核会查询离中心更远的位置，在倾斜平面上，共用一个深度与容差
可能更加吃力。

投影物体范围、`shadowtex1`、环境光、方块光保护以及仅遮蔽直接光的规则均保留。
Debug 0–5 的意义不变；显示阴影可见性的画面会随所选 bias 合理变化。
Constant 模式是对照旧版结果的基准。

## 7. Debug 6：Effective Shadow Bias

新增不经过调色的灰度显示：`clamp((effectiveBias - lo) / (hi - lo), 0, 1)`。
上下限之差不大于 `1e-8`（包括相等）时显示黑色，避免除零。天空、背景和无效 receiver 根据摄像机深度及
G-buffer 有效标记显示黑色。若 receiver 标记有效但法线退化，Angle-Aware 模式
仍采用最大 bias。默认上下限下，Constant `0.0002` 显示灰度 `0.25`。

这里显示的是“该 receiver 将采用的 bias”：关闭阴影或超出 shadow map 覆盖范围时
仍可显示。它不代表实际遮挡程度、真实误差大小或最终阴影贡献。

## 8. 验证能说明什么，第一次该怎么测

运行 `python -B tools/validate.py` 并检查空白问题。结构与数值验证覆盖设置路径、
旧过滤器采样数、Constant 等价性、角度单调性与上下限、退化向量、Debug 归一化，
以及变换和光照保留。**这些不是 Minecraft/Iris/GPU 运行验证**，也不能证明
驱动编译成功、画质改善或性能变化。

测试时明确加载 `D:\MinecraftShaders\MyShader-pcf-kernels` 中的版本。
现有 `MyShader` junction 仍指向独立的天空实验，本阶段不会重定向它。
具体加载步骤见配套测试表。

先用 3x3 PCF、softness `1.0`、Constant `0.0002`；然后只切换为
Angle-Aware `0.0001`–`0.0005`。在同一机位比较地面、掠射表面、柱脚接触阴影、
薄物体和树叶，再移动及旋转相机。随后覆盖 Hard、5x5 与 Poisson。
分别记录 acne、接触间隙、漏光及闪烁，不凭一张截图宣布哪种方案全面更好。

## 9. 局限、后续方向与面试表达

最大 bias 仍可能分离接触阴影或抹掉薄物体阴影。本模型不感知几何厚度，不随
阴影分辨率自动调整，也没有每个 tap 的平面修正；它不能解决所有锯齿或时间闪烁。
本阶段不宣称性能提升。

完成运行测试后，可把 **receiver-plane depth bias** 作为聚焦的 Milestone 7：
估计局部深度变化，为每个 tap 修正比较深度。届时要处理平面假设失效、导数不连续
等情况。这只是建议，本阶段未实现该方法、PCSS、级联或时间过滤。
[微软关于逐纹素深度修正的讨论](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/cascaded-shadow-maps)。

面试时可以这样讲：“我保持阴影采样位置不变，只研究比较容差。固定 bias 用来
复现基准，角度感知 bias 用同一 view space 的 N dot L 在上下限之间插值。
它可能缓解掠射面的 acne，但过大仍会造成接触分离。这是 receiver 端启发式，
不是硬件 slope-scaled raster bias。我用数值回归确认兼容性，再在固定场景中
比较具体伪影，尚未验证的运行结果不会当作结论。”

## 本次已执行的开发检查

- `python -B tools/validate.py`：两种 bias、四种过滤器、七种 Debug、五档 softness
  以及已有回归规则的结构与数值检查通过。
- 独立 `glslangValidator`：139 组程序对编译/链接通过，覆盖 deferred/final 的全部
  bias/filter/debug 分支，以及默认配置下全部 19 对程序。测试先展开 include，
  并为 Iris 的星星阶段宏提供仅用于编译的占位值。这不等于 Iris 补丁流程或 GPU 执行。
- Minecraft 截图、伪影观察和性能结果仍待实际测试，未填入任何虚构结果。
