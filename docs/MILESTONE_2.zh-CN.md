# Milestone 2：Deferred Lambert Lighting / 延迟方向光

> 中文学习版。英文原版：[MILESTONE_2.md](MILESTONE_2.md)

**状态：** 已通过 Minecraft 实机测试。

M1 只是“最终颜色处理”。

M2 开始进入真正的 rendering pipeline：

> 几何阶段先把一些额外的 surface information 存下来，之后再用 fullscreen pass 做 lighting。

## 1. 总数据流

```text
Geometry Pass
   │
   ├─ colortex0 = 原始 scene color
   ├─ colortex1 = view-space normal + valid flag
   └─ colortex2 = block light + sky light
   │
   ↓
Deferred Pass
   │
   ├─ 读取 scene color
   ├─ 读取 normal
   ├─ 读取 light levels
   ├─ 计算 N dot L
   └─ 调制 directional lighting
   │
   ↓
Final Pass
   ├─ 正常画面 / Debug View
   └─ M1 Color Grading
```

这就是一个非常简化但真实的 **Deferred Shading** 思路。

## 2. 为什么需要 G-buffer

假设 geometry 已经画完了。

后面的 fullscreen pass 想计算 lighting，需要知道：

> 这个 pixel 对应的表面朝哪个方向？

但 normal 本来只在 geometry 阶段最容易拿到。

解决方法：

> geometry pass 把 normal 先写进额外 texture，后面再读。

这类保存几何/材质信息的 screen-space buffers 统称：

```text
G-buffer
```

当前项目：

| Buffer | 内容 |
|---|---|
| colortex0 | 已经存在的 scene color |
| colortex1 | 编码后的 view-space normal + valid flag |
| colortex2 | block light + sky light |

它不是完整 PBR G-buffer，只是教学用最小版本。

## 3. MRT：Multiple Render Targets

一个 fragment shader 可以一次写多个 output：

```text
location 0 -> color
location 1 -> normal
location 2 -> light metadata
```

这叫：

> Multiple Render Targets。

同一次 geometry rasterization，就可以生成多个 per-pixel buffer。

## 4. 为什么 Normal 用 View Space

Normal 经过：

```text
gl_NormalMatrix * gl_Normal
```

进入 View Space。

同时 sunlight/moon light direction 也用 View Space。

于是：

```text
dot(N, L)
```

两者在同一个 coordinate space 中。

这是非常重要的 Graphics 基础：

> Dot product 两边必须是兼容的空间。

## 5. 为什么插值之后还要 Normalize

Vertex shader 中 normal 即使是 unit vector，经过 triangle interpolation 后：

> 长度通常不再是 1。

所以 fragment shader 使用之前需要重新 normalize。

否则 N·L 数值会错。

## 6. Normal Encoding

真实 normal 分量大约：

```text
[-1, 1]
```

但 texture 通常更方便保存：

```text
[0, 1]
```

所以 encode：

```text
normal * 0.5 + 0.5
```

decode：

```text
encoded * 2 - 1
```

然后再 normalize。

## 7. Valid Flag

`colortex1.a` 用来告诉 deferred pass：

> 这里是不是真的有一个有效 surface。

天空/background 并没有我们记录的 surface normal。

所以不能对所有 pixel 无脑 lighting。

## 8. Minecraft Lightmap Metadata

M2 还保存：

```text
R = block light
G = sky light
```

注意：

这不是新算出来的物理 irradiance。

只是把 Minecraft 已经有的 lighting level 作为 metadata 保存下来，让后面的 pass 判断：

> 这个地方适不适合加强 directional lighting？

## 9. Lambert Lighting

最核心公式：

```text
NdotL = max(dot(N, L), 0)
```

直觉：

- N 和 L 越同方向 → 越亮
- 90° 左右 → 接近 0
- 光在背面 → 负数，clamp 到 0

之后：

```text
lambert = ambient + direct * NdotL
```

## 10. 为什么不能再乘一次 Minecraft Lightmap

`colortex0` 里的 scene color 本来已经被 Minecraft lightmap 影响了。

如果 deferred 再完整乘一次 lightmap：

> 等于把同一份 lighting 重复应用。

所以 M2 只是对现有 scene 做方向光调制，而不是重新从 albedo 做一遍 physically based lighting。

## 11. Cave / Torch Protection

项目用了：

```text
skyWeight = skyLevel * (1 - blockLevel)
```

直觉：

- 室外 skylight 高、block light 低 → directional effect 强
- 洞穴 skylight 低 → 尽量保持原画面
- 火把 block light 高 → 减少 sunlight modulation

这样不会让原本有火把的洞穴突然黑掉。

## 12. 当前 Lighting Equation

```text
lambert = ambient + direct * NdotL
factor = mix(1, lambert, strength * skyWeight)
output = originalScene * factor
```

这是教学 lighting model，不是完整 BRDF/PBR。

## 13. Debug Views

### Normal View

把 normal 映射成 RGB。

用于检查：

- face direction；
- normal 是否有效；
- camera movement 时空间转换是否正常。

### Lightmap View

```text
Red = block light
Green = sky light
```

### NdotL View

白：

> surface 朝向 light。

黑：

> surface 背离 light。

这是 orientation，不是 shadow occlusion。

## 14. 为什么 G-buffer 用 texelFetch

如果用普通线性 filtering：

> 一个 object 边缘的 normal 可能和另一个 object 混在一起。

G-buffer metadata 通常希望：

> 当前 screen pixel 就读取当前 pixel 当时写进去的 exact value。

所以这里使用 `texelFetch` 很合理。

## 15. M2 还没有什么

没有：

- PBR；
- specular；
- roughness；
- metalness；
- shadow；
- SSAO；
- SSR；
- HDR lighting。

这非常正常。

M2 的任务不是“一次做完整 renderer”，而是把 deferred pipeline 主干搭起来。

## 16. 你必须掌握

1. G-buffer 是什么。
2. MRT 是什么。
3. Deferred Shading 为什么要存 metadata。
4. View Space 是什么。
5. 为什么 N 和 L 必须同空间。
6. Normal 为什么插值后要 normalize。
7. Normal encode/decode。
8. Lambert N·L。
9. 为什么不能 double-apply lightmap。
10. 为什么 G-buffer edge 不应该随便 linear filtering。

## 17. 面试回答

**What is a G-buffer?**

> A set of screen-space render targets storing per-pixel data for later shading.

**Why deferred lighting?**

> Geometry and lighting are separated so later passes can shade visible pixels from stored surface data.

**Why normalize interpolated normals?**

> Interpolation changes vector length, so the fragment normal is generally no longer unit length.

**What is Lambert diffuse?**

> A simple diffuse term proportional to max(dot(N,L),0).

## 18. 60 秒项目解释

> M2 给项目加入了一个小型 Deferred Rendering pipeline。Geometry pass 除了原来的 scene color，还写入 view-space normal 以及 Minecraft block/sky light metadata。之后 deferred fullscreen pass 读取这些 G-buffer，使用和 normal 相同空间里的 celestial light direction 计算 Lambert N·L，再调制原本已经 lightmapped 的 scene。为了不破坏洞穴和火把照明，我根据 sky light 和 block light 控制新增方向光的作用强度，同时提供 normal、lightmap、N·L debug views。
