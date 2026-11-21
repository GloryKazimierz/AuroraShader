# 泡沫、日光与月光

[English](WATER_M5_FOAM.md)

## 设置与来源

`WATER_FOAM=0` 关闭，`1` 使用当前帧本地证据，`2` 增加高档持续历史。活动路径仍要求已有水体光学、风格、线性颜色、调试及硬件条件。预设不会自动打开泡沫。它位于光学传输之后、原有 bloom 之前，精确保留 alpha。水下、熔岩、无效前表面、多层水和覆盖物保守回退。后续 M3B 可以独立处理水下光学，此处不会伪造水下泡沫层。

泡沫由两类证据产生：

- 明确水平材料流动映射的局部面积压缩，计算真正的二维雅可比行列式；不是把高度或法线陡峭程度冒充挤压。
- 水面附近实际可见的不透明几何。四个投影采样围绕 0.45 方块环，必须有配对场景颜色/深度、有效方向光份额、没有透明归属层且最终深度吻合。使用真实世界 XZ 距离与高度差，仅是局部接触估计，不是完整世界岸线距离场。单独的水面到水底间距不能生成岸边泡沫；遮挡或离屏岸线仍未知。

流动模型为 `X(q,t)=q+1.5*s*sum(A_i*khat_i*cos(phi_i))`，采用 W2 六个波模态及固定足迹过滤。直接求二维雅可比和材料速度；收缩上界 0.1778662224，行列式下界超过 0.675，映射不会折叠。三个有界 Newton 步求可见位置对应的材料坐标。泡沫产生阈值是对压缩的美术近似，并非真实空气卷入模拟；Minecraft 网格不位移。


## 光照

泡沫采用漫反射反照率除以 pi，分别接收天空、方向光和局部灯光估计。方向光在水面实际位置做稳定 2×2 阴影比较；环境天空和灯光不被方向阴影一并抹掉。这里使用已有 Minecraft 光照信息作视觉照明估计，不宣称还原物理流明。

没有自发光或无条件白色项：天空/灯光输入皆零时，泡沫辐亮度精确为零。泡沫先应用与已解析水色相同的表面到相机雾，再混合，因此不会重复施加相机雾。新增 `water_shadow_bindings.glsl` 与 M4 接收面共用七个阴影 uniform 和偏置函数，避免重定义；各自仅在活动条件内包含。

## 仅高档：历史成本和回退

只有模式 2 声明并写入历史目标：

| 目标 | 格式 | 内容 |
| --- | --- | --- |
| 13 | RGBA16F | 覆盖率、年龄、世界法线八面体编码 XY |
| 14 | RG32F | 完整浮点窗口深度、精确 frameCounter+1 |

1920×1080 双缓冲额外约 **63.28125 MiB**，不包括已有目标及驱动开销。本地档没有这两份目标。最初元数据方案约 95 MiB；量化覆盖率/法线、删除冗余视口字段后降低成本，同时保留完整深度精度。

当前不支持的像素会明确写零。非零连续帧标记拒绝清空、过期和跳帧数据，并支持帧计数回绕。还检查纹理尺寸、有限数值、年龄、相机平移/旋转跳变、投影变化、世界法线，以及历史像素中心处当前水面平面的完整浮点深度。历史是点采样覆盖率，不是颜色 TAA 或通用时域降噪。

材料点移动到上一波浪相位，再投影到上一相机。衰减半衰期 0.65 秒，年龄上限 2.5 秒；历史失效时始终退回当前证据。时间采用 Iris `frameTime`（上一帧时长），所以变帧率下的平流仍是有约束近似。半精度年龄和覆盖率的存储量化由原生测试覆盖。

只读检查了本机 Iris 1.10.5 / Minecraft 1.21.11 的字节码，确认创建与尺寸变化会要求完整清空。对应分支源码显示完整清空忽略普通逐帧 clear 关闭，并清两侧：[RenderTargets](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/targets/RenderTargets.java)、[ClearPassCreator](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/targets/ClearPassCreator.java)、[流水线顺序](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java)。零标记与 textureSize 检查依赖这个分配/重置行为；不能只看尺寸就声称旧数据已清除。

该版本还在帧尾将已翻转的持续目标从 alternate 复制到 main，额外消耗全屏带宽：[FinalPassRenderer](https://github.com/IrisShaders/Iris/blob/1.21.11/common/src/main/java/net/irisshaders/iris/pipeline/FinalPassRenderer.java)。因此持续模式仅属高档。原生工具验证数据与读回后下一帧，没有执行 Iris 的真实分配、复制及游戏调度，也不报告游戏帧率。

## 水面高光

在“水面”页开启“日月水面高光”。小片水面的坡度按 Beckmann 分布近似；远处小于像素的细波会增加粗糙度，使高光自然变宽。晴天亮带集中，雨天亮带更宽、更暗，月光偏冷并受月相影响。阴影取自水面位置，雾只衰减这段高光；最后由泡沫覆盖相应面积。可见水面即使没有可信的池底记录也能反光。

[日光、满月与雨天的对照图](validation/WATER_GLINT_views.png)和[泡沫及阴影的对照图](validation/WATER_FOAM_views.png)均为自建场景的实际显卡输出。[高光报告](validation/WATER_GLINT_GPU.json)检查了光路互换、正视角菲涅耳、雨天展宽和透明度。[泡沫报告](validation/WATER_FOAM_GPU.json)包含雅可比的独立有限差分、岸线、光照、量化历史与镜头运动验证。[共享接收面函数的 14 组对照](validation/M5_interface_refactor.json)也保留了前一组合版本的颜色、透明度和历史结果。

[三帧组合对照](validation/WATER_FOAM_GLINT_OVERLAP.json)中，泡沫在 1,870 个受到高光照明的颜色通道采样上降低了亮度，透明度保持一致。
