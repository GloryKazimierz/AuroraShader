# Milestone 16：由背景深度间距驱动的水面颜色

日期：2026-11-13。分支：`codex/milestone-16-water-depth-color`。
基线：M15 提交 `bc811801441709143cbb2ef33a2db3dadc597ee7`。
[English version](MILESTONE_16.md)。

M16 为已分类水面的**源 RGB**加入轻柔的、与深度有关的青绿色变化。
原生 alpha、几何体、深度、混合状态和已有雾顺序保留。
Minecraft/Iris 实际观感仍未观察；执行过的检查另行记录。

## 1. 深度快照只提供背景线索

新增输入为 `depthtex2`，采样位置就是当前水面片元自己的屏幕像素。
所检查的 Iris 源码在 `beginHand` 中、实心手部绘制前复制该深度；
后续主透明阶段入口复制 `depthtex1` 并执行 deferred。
世界采样器配置会向 gbuffer 程序提供 `depthtex2`。
[复制时机](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java)，
[采样器绑定](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/samplers/IrisSamplers.java)。

准确称呼是**手部/主透明阶段之前的背景快照**，不能一概称为“只有不透明物体的深度”。
旧程序类别中的透明实体/粒子可能更早绘制，快照保存的是那个时刻实际存在的深度。
它没有水体出口表面，也没有哪些区间被水填满的信息。
[Iris 深度缓冲](https://shaders.properties/current/reference/buffers/depthtex/)，
[透明绘制顺序](https://shaders.properties/current/reference/programs/gbuffers/#translucent-gbuffers-and-deferred)。

源码依据固定为 Iris `99d855970316329f2e0e42ac2b79ef763cb77cc3`；
当前安装的游戏/模组版本没有重新核实。

## 2. 重建竖直间距，不直接相减原始深度

屏幕深度是非线性的，两个深度值之差不等于方块距离。
用已有逆投影分别重建当前水面和背景位置，再变换两者的差；差向量不加相机平移：

```text
deltaView = backgroundView - waterView
要求 dot(deltaView,unit(waterView)) > 0
deltaWorld = mat3(gbufferModelViewInverse) * deltaView
drop = clamp(max(-deltaWorld.y,0),0,32)
q = 1 - exp(-drop / max(WATER_DEPTH_SCALE,0.0001))
face = smoothstep(0.5,0.95,dot(originalNormal,worldUpInView))
w = clamp(WATER_DEPTH_STRENGTH,0,0.35) * q * face
    * clamp(environment * sky * (1-block),0,1)
```

使用整数像素上的 `texelFetch`，不做过滤，也没有折射采样偏移；
重建使用该像素中心与深度纹理尺寸。
像素越界、天空/清除深度 1、非有限数据、背景与水面等深或在前方、
视线间距非正、竖直落差非正时，都保留原源颜色。
适用范围来自原始表面法线，动态反射波浪不会切换这个颜色遮罩。
无效或接近零的位置、法线、向上向量也会回退。

使用竖直落差，可以减轻水平池底上掠射视线长度对颜色的影响。
但它仍是同像素几何启发式：多层水、含水方块、空气间隙、斜坡或远处岸边，
都可能让“整个区间都是水”的假设失效。
32 格上限只限制响应，不代表物理最大水深。
默认尺度 8 下，8 格落差的 `q≈0.632`，之后还需乘其他条件。

## 3. 改变色度，同时保留源亮度

令 `S` 为 M13 原色调处理后的源颜色，`L=(0.2126,0.7152,0.0722)`：

```text
Y = dot(S,L)
candidate = S * (0.25,0.85,1.05)
target = candidate * (Y / dot(candidate,L))
result = mix(S,target,w)
```

候选颜色乘在原有颜色上，不会把所有群系/来源替换为同一种固定色相。
重新归一化在浮点误差内保留线性 Rec.709 亮度。
本深度混合本身不增加亮度衰减或发光。
这是后续反射、雾和显示转换之前的源颜色性质，不保证显示器上的主观明亮程度完全一致。

代码先用 RGB 峰值归一化，在较小数值上计算亮度和混合，再恢复峰值，避免 HDR 点积中间溢出。
黑色、负值或非有限输入原样返回。
计算结果若无效、为负或大于 65504，也返回原源颜色，不用裁剪破坏亮度；
这并不是对已有无效输入的修复。

最大可选权重为 0.35，因此本步骤至少保留 65% 原源颜色，其他遮罩还会进一步减弱效果。
满方块光会抑制这个新颜色项，原有天空反射仍可独立工作。

## 4. 为什么它没有吸收背景光

```text
M13 色调 → M16 深度色度 → M13/M14 天空反射 → M9 雾一次 → 原生混合
Cout = alpha * source + (1-alpha) * background
```

只改变 `source`，无法正确地给独立的 `background` 项施加随水深变化的吸收。
所以 M16 不声称实现物理透射、Beer–Lambert 水体吸收、折射或 SSR。
它不采样/重复加雾背景颜色、不除以 alpha、不移动几何体，也不改变不透明度。
原有 alpha 仍然削弱新源颜色的贡献。物理透射需要单独设计合成方式。

已有水 ID、场景/调试、混合与环境条件保留。
新项独立于 M13 色调/反射强度和 `SKY_STYLE`：关闭那些旧效果，不会关闭深度颜色。
`WATER_STYLE=0` 仍会跳过整个水面风格。

## 5. 选项与成本

| 选项 | 默认值 | 可选值 |
|---|---:|---|
| `WATER_DEPTH_TINT` | 1 | 0、1 |
| `WATER_DEPTH_STRENGTH` | 0.35 | 0、0.15、0.25、0.35 |
| `WATER_DEPTH_SCALE` | 8 格 | 4、8、16、32 |

尺度越大，同样竖直间距产生的颜色变化越小。

`water_depth_settings.glsl` 定义选项；`water_depth.glsl` 负责受保护的采样、重建和色度混合。
`water.glsl` 在原色调与反射之间调用它，并在只有旧效果关闭时继续保留该功能。
`shaders.properties` 和语言文件扩展已有水面菜单。
旧提示中的“没有波浪”明确为“没有顶点位移”，与 M14 仅改变法线的波浪一致。

符合条件的水面片元至多增加一次同像素背景深度采样和算术。
没有新增渲染目标、全屏 pass 或程序对；实际 GPU 耗时未测量。
关闭深度颜色、强度零，或无效/零间距时，返回之前的源颜色。

## 6. 运行观察表

| 场景 | 需要确认的问题 | 实际结果 |
|---|---|---|
| 平底浅池/深池 | 青绿色是否逐渐增强，且没有新增源亮度降低？ | |
| 俯视、掠射与相机运动 | 竖直间距颜色是否稳定，有无可见边缘伪影？ | |
| 手持实心/透明物品 | 排除手部深度后，是否没有手形颜色中断？ | |
| 斜坡、瀑布、岸边和天空背景 | 原表面适用范围与无效背景回退是否正常？ | |
| 多层水、空气间隙和含水方块 | 几何启发式会在哪些场景明显失效？ | |
| 水面前后的玻璃、实体与粒子 | 记录原生排序/叠加限制 | |
| 洞穴/方块光、流体相机和其他维度 | 继承的光照/环境条件是否保持有效？ | |
| 旧色调/反射关、天空关、深度关/零 | 独立控制与精确基线是否正确？ | |
| 不同资源包 alpha 与群系颜色 | 原覆盖率和源颜色特征是否仍然可辨？ | |

## 7. 六个实用问题

1. **为什么用 `depthtex2`？** 手部之前的快照避免把手部深度误当成背景。
2. **为什么重建位置？** 透视原始深度之差不是世界距离。
3. **差向量为什么不加平移？** 位移只改变方向/尺度，不需要再改变原点。
4. **为什么保留亮度？** 本阶段改变与深度有关的色度，同时保留源光照等级。
5. **为什么不是水体厚度？** 深度快照提供一个可见表面，不提供哪些区间被水填满。
6. **为什么 alpha 不变？** 保留原生合成；物理透射等输入和混合设计完成后再做。

## 8. 已执行检查

完整 M1–M16 CPU/结构验证器通过。M16 检查了 91 项历史文件校验、
540 组水池投影和 19,440 个颜色案例。
float32 深度案例的最大重建误差为 0.00615097 格；
这只是对应案例的结果，不是普遍的深度精度保证。
1,352 个离线 GLSL 配置全部通过。

[本机编译报告](validation/M16_GPU_compile.json)也已通过：覆盖 24 对程序的
1,352 个配置在 Intel 驱动上编译和链接成功，于 2026-11-13 08:21:21 UTC 完成，
C++ 构建没有诊断输出。

[扩展本机深度报告](validation/M16_GPU_depth_extended.json)在 Intel Iris Xe、
OpenGL 3.3 compatibility / 驱动 31.0.101.3962 上通过：
**40 个案例、840 个颜色样本、767 个完全保留的回退像素**。
它扩展了保留的[初始 34 案例报告](validation/M16_GPU_depth.json)，
不能把两次运行相加作为独立覆盖数量。

案例调用实际深度函数与选定的完整水面风格 wrapper，
覆盖斜面、有效 1x1 深度及越界像素、无效/零投影、负视线间距、
无效光照/向上向量等条件。
深度来自合成 RGBA32F 纹理的红通道，并配合透视推导的位置；
它不是 Minecraft 实际光栅化的深度，也不检查原生水面混合或真实 Iris 资源绑定。

启用时 RGB 容差为 `0.000003 + 0.00003*abs(expected)`；
明确的回退像素和 wrapper alpha 要求完全一致。
最大 RGB 差异约为 0.004872 线性 HDR 单位，出现在包含约 60,000 数值的案例中，
不能理解为归一化显示图像误差。允许容差被使用的最大比例为 0.00318603。
当前着色器内容与报告具有相同摘要：

```text
df486ceed290338e3df31bc42c087db32fd21eb3e2dd194a5cc3549e3552df54
```

使用新的报告路径重复深度套件：

```powershell
python -B tools/validate_gpu.py --cxx C:\msys64\ucrt64\bin\g++.exe --suite depth --report docs/validation/M16_GPU_depth_repeat.json
```

`all` 和 `render` 套件现在也包含深度案例；已有报告不会被覆盖。
这些检查增加本机驱动证据，上面的运行观察表继续留空，也没有耗时/FPS 结论。

相关说明：[M13 水面](MILESTONE_13.zh-CN.md)、[M14 法线](MILESTONE_14.zh-CN.md)、
[M15 本机验证](MILESTONE_15.zh-CN.md)、[路线图](AURORA_ROADMAP.zh-CN.md)。
