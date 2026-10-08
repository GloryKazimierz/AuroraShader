# Shadow Bias 学习指南 — Milestone 6

面向初级 Graphics/Rendering Engineer 面试。M6 仍是实验实现，是否能在
Minecraft/Iris 中正常运行，需要用户实测确认。[English](SHADOW_BIAS_STUDY_GUIDE.md)

## 1. 深度精度回顾（Depth Precision Refresher）

Shadow map 保存从光源看见的最近投影物体深度。光栅化、有限的存储精度和接收点
重建，会各自引入误差。归一化深度并不以 Minecraft 方块为单位；同一个数值的意义
取决于投影和深度范围。M6 保持这两者不变。

## 2. 为什么会出现自阴影错误（Why Self-Shadowing Happens）

重建出的接收点与查询到的阴影纹素，未必对应表面上的同一点。因此，同一个表面也
可能错误地遮挡自己。问题既包含精度误差，也包含采样位置不一致，不能全部归因于
浮点数舍入。[Microsoft：阴影贴图伪影](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/common-techniques-to-improve-shadow-depth-maps)

## 3. 固定偏移（Constant Bias）

本项目比较的是 `receiverDepth - bias <= storedDepth`，成立表示受光。例如
`0.50003 - 0.0002 <= 0.50000` 成立。Constant 模式原样返回 `SHADOW_BIAS`，
默认值 `0.0002` 保留 M5 的比较容差。但同一个容差无法适应所有表面朝向、投影和
过滤覆盖范围。

## 4. 阴影痤疮（Shadow Acne）

错误的自遮挡常表现为条纹、斑点或暗块。调大 bias 前，先确认深度比较和坐标变换
正确。偏移增大后斑点减少，并不意味着整个阴影系统就更准确了。

## 5. 阴影悬浮（Peter-Panning）

容差太大，会把接触处真实的遮挡也忽略掉。阴影与物体脱离，看上去像物体悬浮在地面
上。检查紧贴地面的柱子：地面没有斑点，只能说明一个问题有所缓解，还必须查看接触
阴影有没有出现缝隙。

## 6. 掠射角（Grazing Angles）

光线几乎沿着表面传播时，shadow-map UV 的微小变化可能对应较大的接收面深度变化。
附近的过滤采样点，本来就应使用不同的接收深度。一个固定容差在这里可能偏小，而在
正对光源的表面上又偏大。

## 7. N dot L 与表面朝向（Surface Orientation）

`N` 是归一化的 **view-space 接收面法线**；`L` 是由 `shadowLightPosition` 得到的、
指向天体阴影光源的 **view-space 方向**。正对光源时点积接近 1，掠射时接近 0。
M6 将负值截到 0，因此背光面也使用最大的角度偏移。不要把 world-space 法线与
view-space 光线方向直接点乘。

## 8. 随角度调整的偏移（Angle-Aware Bias）

输入方向有效时，本次的确切模型为：

```text
lo = clamp(min(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
hi = clamp(max(SHADOW_BIAS_MIN, SHADOW_BIAS_MAX), 0, 0.002)
n = clamp(dot(normalize(N), normalize(L)), 0, 1)
bias = clamp(mix(lo, hi, 1 - n), lo, hi)
```

默认 `lo = 0.0001`、`hi = 0.0005`。向量无效或退化时，不去归一化无效向量，
而是令 `n = 0`，得到 `hi`。上下限相同就退化为固定值；填反会先排序。
Constant 模式完全跳过这套公式。它只是依据朝向设置有界容差的 heuristic，
没有直接测量真实深度误差，也不保证画面一定改善。

## 9. 真正的光栅化斜率偏移（True Slope-Scaled Raster Bias）

Raster bias 在图元光栅化时调整深度。常用的斜率度量是
`max(abs(dz/dx), abs(dz/dy))`，其中坐标属于 raster/window space；阴影 pass
对应光源的投影。API 将斜率项与常量项组合，具体规则还取决于 API 和深度格式。
M6 没有计算这种导数，只调整接收点比较时的容差，不能称为同一个算法。
[Direct3D 深度偏移定义](https://learn.microsoft.com/en-us/windows/win32/direct3d11/d3d10-graphics-programming-guide-output-merger-stage-depth-bias)

## 10. 法线方向偏移（Normal Offset Bias）

Normal offset 会先沿法线移动接收位置，再投影到 shadow map，因此 UV 和深度都
可能改变。M6 只是借助法线选择一个标量容差，没有移动几何，也没有移动查询位置。
[Pettineo 的实现说明](https://mynameismjp.wordpress.com/2013/09/10/shadow-maps/)

## 11. 接收平面深度修正（Receiver-Plane Depth Bias）

先估计深度在 shadow-map 坐标中的局部梯度，再为每个采样点预测接收深度：
`zTap ≈ zCenter + dz/du * du + dz/dv * dv`。它依赖局部平面假设，需要处理几何
不连续和不稳定导数。M6 尚未实现这种逐 tap 修正。
[Microsoft：使用导数计算逐纹素偏移](https://learn.microsoft.com/en-us/windows/win32/dxtecharts/cascaded-shadow-maps)

## 12. Bias 与 PCF

PCF 平均的是二值可见性比较结果，不是原始深度。把错误的自阴影比较进行平滑，并不
能让比较本身变正确。M6 对每个接收点只计算一次 bias，然后供全部 tap 共用。
进入有效过滤路径时，Hard、3×3、5×5 分别比较 1、9、25 次。覆盖范围越大，遇到
接收面深度变化的机会也越多。
[NVIDIA：PCF 的定义](https://developer.nvidia.com/gpugems/gpugems/part-ii-lighting-and-shadows/chapter-11-shadow-map-antialiasing)

## 13. Bias 与 Poisson PCF

M6 保留固定圆盘内的 8 个偏移和 8 次比较。采样分布改变查询位置，并不会消除容差
需求。每个 tap 仍共用同一个 bias；没有加入随机旋转或时间过滤。
Softness 为 0 时，PCF 查询位置都回到中心；Hard 仍不受 softness 影响。

## 14. 薄几何问题（Thin Geometry Problems）

薄片可能不足一个纹素宽，前后深度间隔也很小，较大容差容易抹掉它的遮挡。
Cutout 覆盖率、物体是否参与投影、法线朝向，以及几何是单面还是双面，都会独立
影响结果。M6 不修复这些表示问题；不要为了调 bias 顺手翻转法线或改变 caster 范围。

## 15. 漏光（Light Leaking）

偏移过大，会把真实的遮挡判成受光，接触处或薄墙就可能看似透光。项目还保留了
“shadow map 外的采样按受光处理”的规则，这也可能使边界变亮。先区分原因，再调参数。

## 16. 调试清单（Debugging Checklist）

1. 固定场景、相机、时间、投影、过滤模式和 softness。
2. 对比 Constant `0.0002` 与 Angle-Aware `0.0001–0.0005`。
3. 查看法线、原始深度、阴影可见性和有效 bias 的调试画面。
4. 检查接触点、掠射面、树叶、薄物体和阴影贴图边界。
5. 移动相机后再检查四种过滤模式，以及 softness 为 0 的情况。
6. 确认环境光和方块光仍然可见；记录观察到的伪影，不预设改善结论。

静态结构与数值验证不能证明 GPU 编译、运行稳定性、画质或性能。

## 17. 面试问题（Interview Questions）

1. **Acne 的原因？** 同一表面的接收深度与存储深度不一致。
2. **Bias 为什么有用？** 给可见性比较留出容忍小误差的余量。
3. **什么是 peter-panning？** 偏移过大，使接触阴影与物体脱离。
4. **固定 bias 为什么不完美？** 误差随朝向和采样情况变化。
5. **掠射面为什么难处理？** 相邻阴影纹素之间的接收深度变化很快。
6. **N dot L 表示什么？** 单位法线相对于单位光线方向的朝向关系。
7. **什么是 angle-aware bias？** 按法线与光线夹角选择有界接收容差的启发式。
8. **等于硬件 slope bias 吗？** 不等于；它没有测量光栅深度导数。
9. **什么是 slope-scaled depth bias？** 按图元深度斜率调整的光栅化深度偏移。
10. **什么是 normal offset？** 沿接收面法线移动阴影查询位置。
11. **什么是 receiver-plane bias？** 根据接收平面，为相邻 tap 分别预测接收深度。
12. **PCF 能解决 acne 吗？** 不能；它可能只是在过滤错误的比较结果。
13. **Poisson 能解决 bias 吗？** 不能；采样分布无法替代正确的深度容差。
14. **偏移过大为什么漏光？** 原本被挡住的点可能被错误判成受光。
15. **实际引擎中怎么排查 acne？** 核对坐标与深度，隔离 bias 变量，检查接触，再测试运动。

## 18. 一分钟解释（One-Minute Explanation）

Shadow mapping 把接收点深度与光源看见的最近深度比较。采样位置和精度存在差异，
同一表面可能错误地遮挡自己。Bias 给比较增加容差，但过大会让阴影脱离或产生漏光。
M6 保留固定偏移，又加入一个有上下限的角度启发式：使用 view-space 法线和光线
方向，正对光源时容差小，掠射时容差大，同一接收点的所有 PCF tap 共用一个值。
它既不是真正的光栅化 slope-scaled bias，也不是逐 tap 的 receiver-plane 修正。
过滤研究“在哪里采、采多少”，bias 研究“每次比较容忍多少误差”。最终必须用运行
测试同时检查 acne 和接触质量，不能只看某一张没有斑点的截图。
