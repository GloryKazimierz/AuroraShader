# 贴近水面时怎样恢复浅水底颜色

把视点降到浅滩水面下约一厘米，向斜下方看。水面可能已被镜头的近裁剪平面裁掉，水底仍在画面内。开启「水面 → 反射与折射 → 贴近水面的浅水底」，并启用水体光学与阴影空间焦散后，光影可以在连续的阴影记录中找到那段浅水，再按光程恢复水底颜色。此功能默认关闭。

## 哪些像素足够确定

1. 检查引擎相机介质，以及同一像素的实际近裁点、透明叠层、前景深度和不透明深度。
2. 在阴影纹理中取连续的有限水面片，确认眼睛和近裁点都浸没、水底近乎水平，水深在 0.08–0.50 米。眼睛到床面最多 1.5 米。
3. 沿视线投影和入射光折射路径分别走过最多 32 个阴影纹素区间。即使两个端点都有水，中途有一格空缺也保留原色。匹配的直射光先经过入水那一段，水底反射的光再经过回到眼睛的那一段。
4. 完成颜色合成，全程保留原像素的透明度。岸边、屋顶、玻璃叠层、空气、跨界的未知水段和缺失记录各自保留游戏原有结果。掠射时，毫米级几何误差就可能变成明显的水色误差，因此跨界长度需要单独的几何依据。

每种形状都可能存在小于阴影纹素的孔洞。这个办法能支持有限范围内的一部分贴水镜头。开销取决于有多少像素需要逐格验证，两条路径最坏共有 768 次阴影纹素读取，适合单独对照。画质预设保留原选择。

## 如何复验

[独立几何参考](validation/nearclip/NEARCLIP_REFERENCE.zh-CN.md) 使用有解析几何真值的水面与床面。显卡复验还运行实际的阴影采集、水体合成和最终显示。将贴水实验关闭、遮掉中间一格或放入玻璃，能检查原有像素是否逐分量保持一致。

[显卡光学读回](validation/WATER_NEAR_BED_GPU.json) · [最终显示验证](validation/WATER_NEAR_BED_FINAL.json) · [三个水位的固定视角](validation/WATER_NEAR_BED_views.png) · [关闭与能力不足时的编译对照](validation/WATER_NEAR_BED_OFFLINE.json)

`python -B tools/validate_gpu_water_nearclip_color.py --report docs/validation/NEW_near.json --plate docs/validation/NEW_near.png` 会生成一份新报告，使用已有文件名会停止。最终显示测试使用 `tools/validate_gpu_water_nearclip_color_final.py`。离线检查使用 `tools/validate_water_nearclip_source.py --baseline <上一提交导出的 shaders 目录> --report docs/validation/NEW_source.json`。这些是有真值的合成视角，实际 Iris 存档中的透明排序和游戏帧率仍需观察。

## Implementation notes

The near plane can clip away a water surface while the camera is already submerged. The optional shallow-bed path reconstructs the individual pixel's near point, checks transparent ownership against paired opaque depth, then walks the shadow grid along both the eye-to-bed projection and the incoming refracted light path. A missing intermediate cell returns the incoming native color even when both endpoints have valid water. The depth range is 8–50 cm, and the camera-to-bed distance is capped at 1.5 m.

Paired, pre-fog radiance and its direct-light share feed the two-leg transport. The direct component travels down through water; all reflected bed light then travels back to the eye. The pass preserves alpha. Crossing rays with an uncertain water length and unobserved volumes remain unresolved. The [final-stage readback](validation/WATER_NEAR_BED_FINAL.json) includes the missing-interior-cell counterexample.
