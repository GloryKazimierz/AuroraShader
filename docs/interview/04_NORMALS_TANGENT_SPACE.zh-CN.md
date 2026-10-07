# 第 4 章：Normals、Normal Matrix 与 Tangent Space

## 1. Normal 表示什么

Normal 表示：

> 表面朝向。

不是位置。

它会用于：

- diffuse；
- specular；
- normal mapping；
- backface；
- bias heuristic。

Lighting 里一般希望 normal 是 unit vector。

## 2. 为什么 Normal 不能总是当普通 Vector 变换

Position 描述：

> 点在哪里。

Normal 描述：

> 一个局部平面的方向。

如果 Model Matrix 包含：

```text
non-uniform scale
```

例如 x 放大 2 倍，y 不变。

直接拿同样 matrix 乘 normal：

> normal 可能不再垂直于变换后的 surface。

于是 lighting 错。

## 3. Normal Matrix

一般：

```text
NormalMatrix = transpose(inverse(M))
```

通常指 linear 3x3 部分。

为什么？

因为我们要保证：

> transformed normal 仍然和 transformed tangent plane 垂直。

这比死背“inverse transpose”更重要。

## 4. 直觉推导

原来：

```text
N dot T = 0
```

T 是 surface tangent。

变换以后：

```text
T' = M T
```

我们希望：

```text
N' dot T' = 0
```

inverse-transpose 正是为了保持这个 orthogonality 关系。

## 5. 为什么 Fragment 里还要 Normalize

Vertex normal 就算一开始长度是 1：

> triangle interpolation 后通常不再是 1。

所以：

```text
interpolate
→ normalize
→ lighting
```

AuroraShader M2 已经这么做了。

## 6. Normal Encoding

Normal 分量：

```text
[-1,1]
```

Texture 常存：

```text
[0,1]
```

所以：

```text
encode = N * 0.5 + 0.5
decode = encoded * 2 - 1
```

decode 后最好再 normalize。

## 7. Face Normal vs Vertex Normal

Face normal：

> 一个 triangle 整张面同一个 normal。

Vertex normal：

> 可以把相邻面的 normal 平均，让 lighting 看起来平滑。

所以一个低面数 mesh：

> Geometry 仍然是折的，但 shading 可以看起来圆滑。

这就是 geometry normal / shading normal 的区别。

## 8. Tangent Space

Tangent Space 是贴在 surface 上的局部坐标系。

通常：

```text
T = Tangent
B = Bitangent
N = Normal
```

合起来：

```text
TBN basis
```

Normal Map 通常保存 Tangent Space Normal。

为什么？

因为同一张纹理可以铺到各种朝向的 surface 上。

## 9. Normal Map 怎么进入 Lighting

Normal Map 读出来：

```text
N_tangent
```

Lighting 可能在 View Space。

所以：

```text
N_view = TBN_view * N_tangent
```

再和 view-space light direction 做 dot。

这里最常见 bug：

- tangent handedness 错；
- bitangent 方向错；
- TBN 不正交；
- texture Y convention 不一致。

## 10. Normal Map 为什么是蓝色

Flat tangent normal：

```text
(0,0,1)
```

映射到 [0,1]：

```text
(0.5,0.5,1.0)
```

所以看起来偏蓝。

## 11. Normal Map 不会改变 Geometry

Normal map 只改变 shading orientation。

不会：

- 改 silhouette；
- 真正把 surface 顶起来；
- 自动产生真实 detailed shadow；
- 自动产生真实 parallax。

所以 bump/normal mapping 和 displacement 不是一回事。

## 12. 面试问题

**Why inverse-transpose?**

> 因为 non-uniform scale 下 normal 必须继续垂直于 transformed tangent plane。

**Why renormalize after interpolation?**

> interpolation 不保持 unit length。

**What is tangent space?**

> 以 surface tangent/bitangent/normal 为 basis 的局部坐标系。

**Why normal maps look blue?**

> flat tangent-space normal 是 +Z，编码后约为 (0.5,0.5,1)。

**Does normal mapping change geometry?**

> No，它改变 shading normal，不改变 mesh。

## 13. 和 AuroraShader 的关系

M2 已经真实使用：

```text
gl_NormalMatrix
→ View Space Normal
→ Encode
→ G-buffer
→ Decode
→ Normalize
→ N dot L
```

所以如果面试官问 Normal Matrix：

不要只背公式。

直接说：

> 我在 deferred lighting 项目里必须保证 stored normal 和 celestial light 都处于 view space，而且 normal 插值/编码后需要重新 normalize。
