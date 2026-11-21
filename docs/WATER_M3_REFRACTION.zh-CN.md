# 透过波动水面看池底

[English](WATER_M3_REFRACTION.md)

在“水面”设置中开启“水体光学”，再调整“水面折射”。默认关沿原像素计算水体透光。64 步和 128 步追踪一条折射线，RGB／128 步最多追踪三条，用于观察色散。

看[三个角度的对照图](validation/WATER_M3_REFRACTION_views.png)时，可以盯着紧贴池边的一排格纹。俯视时格纹的大小略有变化，斜看时偏移更清楚。贴近水面看，只有较窄的一带还能可靠地看到池底。这张图使用合成几何和项目实际的水面采集、合成、最终显示程序。

光从空气进入水后会向法线偏折。命中池底后，水体需要沿弯折路径取回该点自己的颜色、直射光占比和水中距离。三色模式使用 20 °C 液态水在 650、550、450 纳米附近的折射率近似 RGB 色散。[IAPWS 水的折射率公式](https://iapws.org/documents/release/Rindex)

水面必须只有一层可信记录，且与当前深度匹配。目标周围的池底需连续，位于已观测的水面以下，局部水面高度允许相差 4 厘米。玻璃或其他前景、超出屏幕、池底断层和步数用尽都会退回同像素透光。弯曲池底、不同水位、被挡住的物体和水下看出水面的视角有覆盖边界。本阶段复用已有缓冲。

[显卡验证报告](validation/WATER_M3_REFRACTION_GPU.json)包含 Snell 定律与消光的独立验算、只改变目标像素的遮挡对照、透明度和三种视角。运行 `python -B tools/validate_gpu.py --suite water-refraction` 可以复现；附加 `--debug-plate docs/validation/NEW_REFRACTION.png` 可生成图片。三色档属于高开销实验配置。

[完整显卡回归记录](validation/WATER_M1_full_render.json)也验证了冻结的 M1 着色器 `7c32ba6`。测试使用 `9fd2fa3` 修正后的独立临时文件名，覆盖辉光、植被、波浪、反射、调试显示及水体透光。
