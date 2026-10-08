# Milestone 6：阴影 Bias 测试记录

状态：待填写。尚未收集本里程碑的 Minecraft/Iris 运行结果或性能数据。
静态检查不能证明 GPU 编译成功，也不能证明画面中的瑕疵减少或阴影稳定。

## 先确认加载的是哪个项目

测试目录为 `D:\MinecraftShaders\MyShader-pcf-kernels`，分支为
`milestone-6-shadow-bias`。现有 `MyShader` junction 仍指向另一份天空实验，
选择它不会测试本分支。可按 [Milestone 4 测试说明](MILESTONE_4_BENCHMARK.md)
配置独立的 D: 游戏实例；本次没有实际创建该实例或 junction。加载后确认菜单中
有四种过滤方式、Constant/Angle-Aware bias，以及 Debug 6。

## 记录并固定实验条件

- 日期；Minecraft/Fabric/Iris/Sodium 版本；显卡与驱动：
- 世界名称/种子；维度；资源包与其他模组：
- 坐标；相机 yaw/pitch；FOV：
- 渲染/模拟距离；窗口分辨率；全屏状态；垂直同步/FPS 上限：
- 时间与天气；`doDaylightCycle` 和 `doWeatherCycle` 的原值：
- 阴影贴图分辨率：**2048**；阴影距离：**64**；如有改动请记录：
- 开启阴影；Debug **0**；过滤 **3x3 PCF**；softness **1.0**：
- 光照/调色设置；截图文件名；每组观察时长：

同一轮对比只修改 bias 模式与数值。等待区块加载和着色器重载完成后，在同一
视角截图。以下数值只是实验输入，不代表已找到适合所有场景的最佳设置。

## 可复现的测试场景

使用可丢弃的主世界创造模式测试存档，在空旷区域搭建石质平台：
`(0,64,0)` 到 `(24,64,24)`。在平台上布置：

| 几何体 | 建议位置 | 重点观察 |
|---|---|---|
| 竖直墙 | x=4..20，y=65..69，z=4 | 自遮挡、掠射光照下的墙面 |
| 接地立柱 | x=10，y=65..70，z=12 | 柱脚与阴影是否贴合 |
| 楼梯段 | x=16..18，y=65..68，z=14..17 | 台阶、转角、接触阴影 |
| 栅栏与铁栏杆 | x=5..9，y=65，z=18 | 细物体阴影与漏光 |
| 不会消失的树叶 | x=16..18，y=66..68，z=7..9 | 镂空纹理和薄片覆盖 |

记录楼梯的具体摆法和树叶状态。普通 Minecraft 楼梯由轴对齐面组成，并没有连续
倾斜的表面法线；真正的 grazing-angle 测试主要依靠低角度太阳照射平台或墙面。
可从相机位置 `(12,68,28)`、yaw `180`、pitch `25`、FOV `70` 开始，再记录实际
采用的姿态。确保柱脚等接触区域清晰可见；需要近景时，另记一组固定相机坐标。

先查询并记下世界规则原值，再用 `/gamerule doDaylightCycle false`、
`/gamerule doWeatherCycle false`、`/weather clear` 固定环境。第一轮使用
`/time set 1000`，观察晨间长阴影；第二轮单独使用 `/time set 6000` 并重做整组
测试。不要在同一组 bias 对比中改变时间。结束后恢复记录的规则原值，不要默认
原值一定是 `true`。

## Bias 扫描：结果留空，实测后填写

先固定 3x3 PCF、softness 1.0，对比 Constant `0.0002` 与 Angle-Aware
`0.0001`/`0.0005`。随后填写下表。Constant 行的 Min/Max 两列只是重复显示
`SHADOW_BIAS`；该模式不使用可配置的 min/max 控件。

| Bias Mode | Min Bias | Max Bias | Filter | Acne | Peter-Panning | Contact Quality | Grazing Surface | Thin Geometry | Notes |
|---|---:|---:|---|---|---|---|---|---|---|
| Constant | 0 | 0 | 3x3 | | | | | | |
| Constant | 0.00005 | 0.00005 | 3x3 | | | | | | |
| Constant | 0.0001 | 0.0001 | 3x3 | | | | | | |
| Constant | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Constant | 0.0005 | 0.0005 | 3x3 | | | | | | |
| Constant | 0.001 | 0.001 | 3x3 | | | | | | |
| Constant | 0.002 | 0.002 | 3x3 | | | | | | |
| Angle-Aware | 0 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.00005 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 3x3 | | | | | | |
| Angle-Aware | 0.0002 | 0.001 | 3x3 | | | | | | |
| Angle-Aware | 0.0005 | 0.002 | 3x3 | | | | | | |
| Angle-Aware（相等边界） | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware（颠倒边界） | 0.0005 | 0.0001 | 3x3 | | | | | | |

逐项记录阴影痤疮、自遮挡条纹、阴影悬浮、柱脚脱离、漏光、细物体阴影消失，
并写下对应截图编号。相等边界用于检查恒定输出和安全的调试归一化；颠倒边界
用于检查防御性处理。没有测试的格子保留空白，不把预期当成观察结果。

## 过滤方式兼容性矩阵

完成 bias 扫描后，在同一场景中覆盖两种 bias × 四种过滤方式。每一对对比都固定
filter 和 softness。这里记录正确性现象，不据此声称性能有所提升。

| Bias Mode | Min Bias | Max Bias | Filter | Acne | Peter-Panning | Contact Quality | Grazing Surface | Thin Geometry | Notes |
|---|---:|---:|---|---|---|---|---|---|---|
| Constant | 0.0002 | 0.0002 | Hard | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | Hard | | | | | | |
| Constant | 0.0002 | 0.0002 | 3x3 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 3x3 | | | | | | |
| Constant | 0.0002 | 0.0002 | 5x5 | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | 5x5 | | | | | | |
| Constant | 0.0002 | 0.0002 | Poisson | | | | | | |
| Angle-Aware | 0.0001 | 0.0005 | Poisson | | | | | | |

## 调试视图与回归检查

- Debug 5 显示实际阴影可见性。Debug 6 显示**该接收面可能使用的 bias**，不是
  可见性：经安全处理的下限为黑，上限为白，中间线性映射并截断。Constant 也使用
  同一显示范围；上下限之差不大于 1e-8、无效表面标记和天空显示黑色。
  表面标记有效但法线退化时，Angle-Aware 使用最大 bias（上下限不等时为白）。
  调色不应改变此视图。
- 确认 Debug 0–5 正常。Constant 0.0002 下，用四种过滤方式对照 Milestone 5
  截图。两种 bias 模式都测试 softness 0：PCF 应与 Hard 一致；Hard 应忽略
  softness。完成后恢复 softness 1。
- 单独重复一条记录好的缓慢移动/转向路线，观察闪烁、阴影附着和阴影贴图边界。
  越界比较仍按受光处理。运动测试不能替代固定机位对比。
- 单独推进时间，确认阴影随太阳方向变化；继续静态对比前恢复冻结时间。检查
  洞穴与火把区域，环境光和方块光应仍可见。
- 保存 Iris 错误信息、截图与观察记录后，才能确认运行测试结果。边缘更柔和
  不等于自遮挡问题已经解决。
