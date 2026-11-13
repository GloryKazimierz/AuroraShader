# Milestone 7：Aurora 昼夜天空与天体光配色

日期：2026-11-13。开发分支：`codex/milestone-7-fantasy-sky`。
基于 M6 提交 `5479a1c3b2b579e965cdb43681422abcb45b6b79`。
**尚未确认 Minecraft／Iris 运行成功。** 这个状态可以继续保留，同时推进后续开发，
具体工作方式见[路线图](AURORA_ROADMAP.zh-CN.md)。[English](MILESTONE_7.md)。

## 1. 这一步让画面发生什么变化

M7 开始建立 Aurora 的统一配色：白天偏蓝青，晨昏朝向太阳的一侧出现绯红与金橙，
暮色偏紫，夜空偏靛蓝。地表还可以独立启用与天空协调的天体光色。
目标是在增加情绪和色彩的同时，保留方块材质与夜间地形的辨识度。
这是设计目标，不是已经测得的画质结论。

天空背景在 `gbuffers_skybasic` 中处理；星星分支仍直接输出原来的顶点颜色。
太阳、月亮纹理仍由未改动的 `gbuffers_skytextured` 负责。
记录了表面数据的不透明／镂空物体，在 `deferred` 中先完成原有 Lambert／lightmap
调制，再叠加新的光色。之后绘制的透明物体、水面和原版云仍沿用原来的着色方式。
`final` 保留现有调色和 Debug 0–6。

阴影投影、投射者范围、深度比较、bias 模式、过滤采样分布和 G-buffer 数据布局
都没有因本次配色而改变。本阶段尚未加入极光、bloom、自定义云、体积光或地形雾。

## 2. 代码如何分工

| `shaders/` 下的文件 | 职责 |
|---|---|
| `lib/atmosphere_settings.glsl` | 六个用户设置 |
| `lib/color_space.glsl` | 新配色运算使用的 sRGB 解码／编码 |
| `lib/celestial.glsl` | 安全方向向量、维度与状态保护、太阳阶段权重 |
| `lib/sky_palette.glsl` | 有界天空配色、地平线衔接、雨天变化 |
| `lib/celestial_lighting.glsl` | 环境光／直射光配色，以及方块光保护 |
| `lib/geometry/sky_fragment.glsl` | 把天空配色接入实际背景绘制 |
| `deferred.fsh` | 对有效记录表面应用天体光色 |

天空和地表共用同一组白天／晨昏权重，避免各自计算而不同步。
新增配色不需要重写已建立的阴影坐标重建。

## 3. 昼夜由太阳的位置驱动

这里的方向全部使用 **VIEW space（观察空间）**。
将 `sunPosition` 归一化得到 `S`，将 `upPosition` 归一化得到 `U`，
将当前视线方向归一化得到 `R`。代码使用：

```text
e = clamp(dot(S, U), -1, 1)
day = smoothstep(-0.10, 0.16, e)
twilight = smoothstep(-0.18, -0.04, e)
         * (1 - smoothstep(0.08, 0.35, e))
height = clamp(dot(R, U), 0, 1)
horizon = (1 - height)^3
towardSun = max(dot(R, S), 0)
warmth = clamp(horizon * towardSun^4 * SUNSET_GLOW, 0, 1)
```

`e` 可以理解为太阳相对世界向上的高度指标。相机旋转时，参与点积的两个方向
一起旋转，点积不会因此变化。于是低角度太阳仍对应晨昏，抬头或转身不会把
整个世界突然切换成白天。方向计算中也没有加入相机平移。

安全归一化先除以分量绝对值的最大值，再计算单位向量，减少长度计算溢出的风险。
遇到非有限值或接近零的方向，回退为固定向上向量。这是防止未定义数值的措施，
不意味着错误的 Iris 输入也能恢复出正确天象。

判断昼夜必须使用 `sunPosition`。夜间的 `shadowLightPosition` 会换成月亮，
其高度不能代表太阳是否已经落下。本阶段晨曦与黄昏共用同一套太阳高度曲线，
还没有分开设计两种配色。
[Iris 天体与天气输入](https://shaders.properties/current/reference/uniforms/world/)、
[观察空间向上方向](https://shaders.properties/current/reference/uniforms/camera/)。

## 4. 颜色为什么要先解码再混合

天空颜色常量按 sRGB 色值编写。处理时先解码到 linear light，再插值，最后编码回
显示用的 sRGB。新辅助函数使用分段转换，而不是旧调色中近似的 `pow(color, 2.2)`：

```text
decode(c): c < 0.04045 时为 c/12.92；
           其余为 ((c + 0.055)/1.055)^2.4
encode(l): l < 0.0031308 时为 12.92*l；
           其余为 1.055*l^(1/2.4) - 0.055
```

函数先把输入限制为非负。代码在阈值处选择幂函数分支；标准使用的舍入常量在
分界处存在极小的数值差异。[sRGB 转换参考](https://www.w3.org/TR/css-color-4/#color-conversion-code)。

白天、夜晚和晨昏各有天顶色与地平线色。`NIGHT_BRIGHTNESS` 在 linear space
调整夜空强度。晨昏再按视线朝向太阳的程度混入金色，因此温暖区域会跟随太阳。
这里的 glow 指宽范围天空渐变，不是 bloom，也没有替换太阳圆盘。
最终配色顺序为：

```text
sky = mix(mix(night, day, dayWeight), twilight, twilightWeight)
sky = mix(sky, linearVanillaFog, 0.22 * horizon^2)
overcast = linearVanillaFog * mix(0.4, 1.0, dayWeight)
sky = clamp(mix(sky, overcast, 0.85 * clamp(rainStrength, 0, 1)), 0, 1)
```

地平线处保留少量原版雾色，可以继承一部分生物群系与天气影响。
但它**没有计算地形上的雾**，也没有解决透明物体与距离雾如何混合。
真正的几何体雾属于后续独立系统。

局部使用 linear light，仍不等于整个项目已经变成 linear／HDR 渲染器。
场景存储、原版 lightmap 相乘和混合仍沿用 M6 的 LDR 路径，最终调色仍可能截断
较强高光。以后迁移 HDR 时，需要一起检查所有颜色写入、混合和显示转换阶段。

## 5. 地表光色为什么不会统一染遍洞穴

先保留原有结果 `litScene = lightScene(...)`，然后用同一组昼夜权重组合颜色乘数。
原来的标量 Lambert 模型继续存在；输入已经乘过原版 lightmap，并不是纯 albedo。

```text
directAmount = DIRECT_LIGHT * diffuseTerm(normalView) * visibility
total = max(AMBIENT_LIGHT + directAmount, 0.000001)
tint = (AMBIENT_LIGHT * ambientTint + directAmount * directTint) / total
skyWeight = clamp(skyLight, 0, 1) * (1 - clamp(blockLight, 0, 1))
weight = clamp(LIGHT_PALETTE_STRENGTH * LIGHTING_STRENGTH * skyWeight, 0, 1)
       * environmentWeight
result = encode(decode(litScene) * mix(vec3(1), tint, weight))
```

完全被遮挡时，直射光的**颜色贡献**归零，但环境光贡献仍保留。
没有天空光、方块光达到最大、强度为零，或环境不适用时，会提前返回原结果，
连解码／编码往返也不做。方块光介于两端时，新配色会逐渐减弱。
这是一层艺术化光色调制，不是重新构建的物理光照，也不是彩色阴影。

## 6. 设置与回退方式

在 **Aurora Sky and Light** 设置页中调整（内部页面键为 `ATMOSPHERE`）：

| 选项 | 默认值 | 可选值 | 含义 |
|---|---:|---|---|
| `SKY_STYLE` | 1 | 0、1 | Base-330／Aurora 天空 |
| `SKY_BLEND` | 1.0 | 0、.25、.5、.75、1 | Aurora 天空混合比例 |
| `SUNSET_GLOW` | 1.0 | 0、.5、1、1.5 | 朝向太阳的晨昏暖色强度 |
| `NIGHT_BRIGHTNESS` | 1.0 | .5、.75、1、1.5、2 | 只调整夜空，不是全场景曝光 |
| `LIGHT_PALETTE` | 1 | 0、1 | M6 中性光色／天体光配色 |
| `LIGHT_PALETTE_STRENGTH` | .6 | 0、.25、.5、.6、.75、1 | 地表光色强度 |

与 M6 对照时，设置 **SKY_STYLE = 0、LIGHT_PALETTE = 0**，其余旧选项保持一致。
两个系统各自的零强度路径也会直接返回基线结果。

适用条件是 `hasSkylight && !hasCeiling`：既包括主世界，也包括具备这两个属性的
模组维度。下界／末地类型的维度回退到基线。相机进入水、岩浆或细雪时，新配色
也停止应用。失明与黑暗效果通过
`1 - clamp(max(blindness, darknessFactor), 0, 1)` 淡出新样式。
这些保护仅负责不额外叠加新配色，不能说本阶段已经实现了完整的流体雾或状态效果。
虚空天空使用相同且连续的天空／环境权重，在基线与原生顶点颜色之间混合，
应独立观察。相关维度 uniform 为 Iris 专属，当前不承诺
OptiFine 兼容。[Iris 维度属性](https://shaders.properties/current/reference/uniforms/biome/)。

## 7. 自动检查与可选运行观察

在项目根目录运行：

```text
python -B tools/validate.py
python -B tools/compile_glsl.py
```

第二项为可选检查，需要 PATH 中已经有 `glslangValidator`，或用 `--compiler PATH`
指定位置；脚本不会下载编译器。展开后的源代码使用仅供编译的 render-stage 占位值，
没有运行 Iris patcher。实际执行结果以本次提交报告为准。
结构与数值检查不能证明 Iris 的 shader patcher、显卡驱动、画面质量、性能
或完整游戏兼容性。

可以准备一个可丢弃的主世界测试场景，包含石头、木材、树叶、洞口、水面和火把。
固定坐标、相机 yaw／pitch、FOV、分辨率、渲染距离、资源包与原有阴影／调色设置。
记录 Minecraft、Iris、Sodium 和显卡驱动版本。对比设置时冻结时间和天气，
结束后恢复原先的游戏规则。

建议分别观察时间 6000、12000、18000、23000，再让时间正常流动经过日出与日落。
实际配色依据太阳高度，不是按这些 tick 数值直接切换。

| 对照项目 | 观察重点 | 实际结果 |
|---|---|---|
| 关闭两个新系统，与 M6 对比 | 基线天空、地表光照和 Debug 0–6 | |
| 默认 M7 的四个时间点 | 配色连续、地形可读、材质仍有辨识度 | |
| 转动与移动相机 | 地平线稳定，暖色区域随太阳而非镜头移动 | |
| 晴天、雨天、雷雨及过渡 | 平滑变化，不突然跳回晴天配色 | |
| 星星、太阳、月亮和云 | 原有对象仍可见，没有意外改动其绘制路径 | |
| 洞穴、火把、混合天空光／方块光 | 保护局部光源，过渡自然 | |
| 天空混合 0／1，光色强度 0／1 | 两个系统可独立控制，端点行为正确 | |
| 夜空亮度 .5／2，晨昏强度 0／1.5 | 无非有限输出，观察截断和色带 | |
| 流体中的相机、失明、黑暗 | 回退到基线，不额外透出奇幻天空 | |
| 下界、末地、开放模组维度和虚空 | 维度门控与特殊天空处理 | |
| 两种 bias、四种过滤方式 | 新配色没有改变阴影算法行为 | |

没有观察过的格子保留空白。这份表供后续补充现象使用，不是重新设置每阶段人工
验收门槛。若之后观察到 Iris 错误或画面回归，再记录真实信息并安排修复。

## 已执行的离线检查 — 2026-11-13

- 完整 `python -B tools/validate.py` 通过，保留 M1–M6 的回归矩阵。
- M7 的 20,160 组天空边界检查、20,001 个昼夜权重采样、sRGB 往返、
  相机旋转不变性、光照保护端点和虚空连续混合检查通过。
- 最终天空修正后，`python -B tools/compile_glsl.py` 使用已安装的
  glslangValidator 完成 156 组独立程序对编译／链接，全部通过。
- 完整代码审查与空白检查通过。运行观察表仍保留空白。

上述结果没有执行 Minecraft、Iris patcher、GPU 渲染负载或性能测量。
下一阶段按路线图处理场景色彩／HDR 基础；未完成的运行观察继续保留，
不会重新变成逐阶段人工批准门槛。

## 8. 面试时如何简洁说明

1. **为什么用太阳高度，而不是直接用世界时间？** 高度直接对应画面里的太阳方向，
   配色也能跟随太阳轨迹变化。
2. **观察空间的点积为什么不会随相机转动而变？** 同一个刚体旋转保持点积；
   如果把世界空间方向和观察空间方向混在一起，这个前提就失效了。
3. **为什么不能用阴影光源判断昼夜？** 它夜间会切换成月亮，高度不能区分白天和黑夜。
4. **为什么混色前要解码 sRGB？** 编码值与光强不是线性关系；在线性空间插值，
   才能按光贡献进行混合。
5. **这是否已经属于 HDR？** 不是。动态范围、场景缓冲、混合和最终 tone mapping
   都是需要单独处理的管线问题。
6. **怎样保护火把？** 配色权重与天空光成正比、与方块光反向关联；保护端点直接
   返回原结果，不进行额外颜色运算。
7. **阴影里为什么仍能有环境光？** 可见性只乘在直射光贡献上，环境光独立参与组合。
8. **这是不是物理大气散射？** 不是。它是有几何方向依据、连续插值的解析艺术配色。
9. **地平线颜色是否就是雾？** 不是。雾需要几何体距离和正确混合；修改背景色没有
   提供这些信息。
10. **编译通过后还缺什么证据？** 游戏集成、实际画面、运动稳定性和性能仍需要相应
    的运行或测量结果。

## 原始资料

- [Iris gbuffers 的职责](https://shaders.properties/current/reference/programs/gbuffers/)
- [Iris renderStage 标识](https://shaders.properties/current/reference/macros/render_stages/)
- [Iris 太阳、月亮与天气输入](https://shaders.properties/current/reference/uniforms/world/)
- [Iris 玩家状态输入](https://shaders.properties/current/reference/uniforms/status/)
- [下一步开发方向](AURORA_ROADMAP.zh-CN.md)
