# 第 5 章：Textures、Filtering、Mipmaps 与 Anisotropy

## 1. Texture Sampling 本质是什么

Texture 是离散 texel 网格。

Shader 的 UV 却是连续浮点数。

所以 GPU 必须解决：

> 一个连续位置应该从哪些 texel 重建出一个值？

这就是 texture filtering。

## 2. Nearest

Nearest：

> 找最近的一个 texel。

优点：

- 行为简单；
- pixel art 锐利；
- 不会混邻居。

缺点：

- 放大会方块；
- 缩小时 aliasing 很严重。

AuroraShader 的 G-buffer / shadow 一些位置使用：

```text
texelFetch
```

就是因为想读 exact texel，不希望 metadata 被自动混合。

## 3. Bilinear

Bilinear：

> 同一 mip level 内，取附近 4 个 texel 做二维线性混合。

它主要让 magnification 更平滑。

但：

> Bilinear 本身解决不了严重 minification。

## 4. Minification 为什么难

远处一块地面：

> 一个 screen pixel 可能覆盖几十甚至上百 texel。

如果你只从最高分辨率纹理取一两个点：

会漏掉大量高频信息。

结果：

- shimmer；
- moire；
- crawling；
- aliasing。

所以需要 mipmap。

## 5. Mipmap

Mipmap chain：

```text
1024²
512²
256²
128²
...
1²
```

每一级都是更低分辨率、更预过滤的 texture。

远处使用更低 mip：

> 先把高频 detail 平均掉，再采样。

所以 mipmap 同时是：

- anti-aliasing；
- performance/cache 优化。

## 6. Trilinear

Bilinear：

> 一个 mip 内 4 texel。

Trilinear：

> 对两个相邻 mip 分别 bilinear，再在 mip 之间 interpolate。

这样 mip level 切换不会太明显。

## 7. Derivative 与 LOD

Fragment shader 附近 pixels 可以估计 UV 的变化：

```text
dFdx
dFdy
```

Texture hardware 利用类似 derivative 信息估计：

> 当前 pixel 在 texture 上覆盖多大 footprint？

再选择合适 mip level。

这也是为什么 fragment quad/derivative 是 GPU 面试里常出现的概念。

## 8. Anisotropic Filtering

如果 surface 斜着看：

> texture footprint 不是方形，而可能是一条很长的椭圆/长条。

普通 isotropic mip filtering：

- 可能过糊；
- 可能 alias。

Anisotropic filtering 会更好地覆盖这种 elongated footprint。

典型例子：

> 向远处延伸的道路、地板。

## 9. Wrap Mode

常见：

- Repeat
- Clamp
- Mirror
- Border

错误 wrap 可能导致：

- seam；
- 重复图案；
- shadow map 边缘重复阴影。

AuroraShader shadow map 的做法是：

> 越界 sample 直接当 lit，而不是让 texture wrap。

## 10. Color Texture vs Data Texture

Texture 不一定存“颜色”。

Data Texture：

- normal；
- roughness；
- depth；
- shadow；
- ID；
- light level。

这些数据通常不能随便做 sRGB color decoding。

这是非常常见的工程坑：

> 把数据 texture 当颜色 texture 处理。

## 11. Texture Atlas

Minecraft 大量使用 atlas。

Atlas 的问题：

- tile bleeding；
- mip level 污染邻居；
- padding；
- edge seam；
- LOD/derivative 边界。

所以做 Minecraft shader 会比普通独立 texture 多一层复杂度。

## 12. 面试问题

**What is a mipmap?**

> 一系列预过滤的低分辨率 texture，用于匹配缩小时的 screen-space footprint。

**Why mipmaps reduce aliasing?**

> 先在较大区域内低通/平均高频信息，再采样到小 footprint。

**Bilinear vs trilinear?**

> Bilinear 在一个 mip 内插值；trilinear 还在两个 mip 之间插值。

**What does anisotropic filtering solve?**

> Grazing angle 下 elongated texture footprint 的 alias/blur 问题。

**Why texelFetch?**

> 需要 exact integer texel，不想要 normalized UV filtering 时使用。

## 13. 和项目对应

AuroraShader：

- G-buffer → exact texel metadata；
- Shadow → exact raw depth + 自己实现 PCF；
- Boundary → 手工防止 wrap。

这些都是 texture sampling policy，而不是“随便换个 API 函数”。
