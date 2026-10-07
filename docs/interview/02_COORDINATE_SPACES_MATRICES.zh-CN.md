# 第 2 章：Coordinate Spaces & Matrices / 坐标空间与矩阵

## 1. 为什么有这么多“空间”

同一个 3D 点，可以相对于不同参考系描述。

常见：

- Model / Local Space
- World Space
- View / Camera Space
- Clip Space
- NDC
- Screen / Window Space
- Tangent Space
- Light Space

图形学非常多 bug 的本质都是：

> 数字本身没错，但你把它当成了另一个 coordinate space 里的数据。

## 2. Model / Local Space

Mesh 自己的局部坐标。

例如一个 cube 可以围绕自己的原点建模。

Model Matrix 把它放进场景：

```text
worldPosition = Model * localPosition
```

Model Transform 通常包含：

- translation；
- rotation；
- scale。

## 3. World Space

World Space 是整个场景的公共参考系。

在这里比较：

- 两个 object 的位置；
- light 和 object 的关系；
- physics 等。

但并不是所有引擎都坚持绝对 world coordinate。

Iris 有 player-relative convention，所以你的 M3A 特别重要：

> 必须尊重引擎规定的空间 contract，不能自作主张再加 cameraPosition。

## 4. View / Camera Space

View Matrix：

```text
viewPosition = View * worldPosition
```

可以理解成：

> 不是真的把 camera 搬到原点，而是把整个世界反向变换，让 camera 成为参考原点。

AuroraShader M2：

- normal 在 View Space；
- sun/moon direction 也在 View Space。

这样：

```text
dot(N, L)
```

才有正确几何意义。

## 5. Projection 与 Clip Space

Projection：

```text
clip = Projection * viewPosition
```

Perspective projection 会把距离因素编码到 homogeneous coordinate 的 `w` 中。

之后必须：

```text
NDC = clip.xyz / clip.w
```

这就是 perspective divide。

忘掉这一步：

> 透视投影就不成立。

## 6. NDC

Normalized Device Coordinates 是投影之后的标准化空间。

之后 viewport transform 再把它映射到屏幕像素。

从 NDC x/y 到常见 texture UV：

```text
uv = ndc.xy * 0.5 + 0.5
```

也就是：

```text
[-1,1] → [0,1]
```

## 7. Matrix Order

矩阵乘法：

```text
A * B != B * A
```

不能交换。

在常见 column-vector 写法：

```text
clip = P * V * M * local
```

实际作用顺序：

```text
local
先 M
再 V
再 P
```

不要只背 PVM/MVP。

面试时最好说：

> 顺序取决于 vector convention 和 library convention，我会确认当前系统的数学定义。

这比机械背公式专业。

## 8. Inverse Matrix

Inverse 就是把 transform 反过来。

例如：

```text
clip = P * view
```

那么：

```text
view ≈ inverse(P) * clip
```

AuroraShader M3A 就使用 inverse projection：

> 从 camera depth/NDC 重建 view-space position。

这是 inverse matrix 的真实工程用途。

## 9. Position 与 Direction 的 w

Homogeneous coordinates：

Position：

```text
(x,y,z,1)
```

Direction：

```text
(x,y,z,0)
```

为什么？

因为 translation 应该影响“点”，但不应该影响“方向”。

这是面试很喜欢问的小基础。

## 10. Light Space

Shadow Mapping 等于多了一台“光源摄像机”。

当前 receiver：

```text
camera depth
↓
View Position
↓
Player-relative Position
↓
Light View
↓
Light Clip
↓
Light NDC
↓
Shadow UV / Depth
```

然后才能和 shadow map 比。

## 11. 为什么阴影会跟着 Camera 飘

如果 receiver reconstruction 得到的是一种坐标 convention，而 shadow matrix 期待另一种：

> camera 一移动，两者 mismatch 就变化。

视觉表现常见：

```text
shadow slides with camera
```

这通常不是 PCF 问题，而是 transform/space 问题。

## 12. 面试问题

**Why do we need multiple coordinate spaces?**

> 不同操作在不同参考系下更自然：建模、场景摆放、Camera、Projection、Light、Tangent frame 都有自己的需求。

**What does View Matrix do?**

> 把 world coordinates 转换到 camera coordinate frame。

**Why divide by w?**

> Perspective projection 使用 homogeneous coordinates，除以 w 才进入 NDC。

**What is inverse projection useful for?**

> 例如从 depth/NDC 重建 view-space position。

**Position vs direction?**

> position 通常 w=1，direction 通常 w=0，所以 translation 不影响纯方向。

## 13. 和项目对应

你最强的实际例子就是 M3A：

```text
Camera Depth
→ View
→ Player-relative
→ Light View
→ Light Clip
→ Shadow Map
```

以后面试被问 coordinate space，不要只背课本。

直接讲你 debug 过“shadow 是否跟 camera 漂”，会更像真正做过图形项目的人。

## 14. 你必须会画

不看资料画：

```text
Model → World → View → Clip → NDC → Screen
```

然后再画：

```text
Depth → inverse Projection → View
      → inverse View → world-relative
      → Light View → Light Clip → Shadow UV
```

并解释每一个箭头为什么存在。
