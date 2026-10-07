# 第 1 章：GPU Rendering Pipeline / GPU 渲染管线

## 1. 最重要的整体模型

实时 renderer 做的事情可以简单理解成：

> 把场景中的结构化数据，变成屏幕上的 pixel。

一个简化管线：

```text
CPU / Application
↓
提交 Draw / Dispatch
↓
Vertex Processing
↓
Primitive Assembly
↓
Clipping
↓
Rasterization
↓
Interpolation
↓
Fragment / Pixel Shader
↓
Depth / Stencil
↓
Blending
↓
Render Target
↓
Post-processing
↓
Present
```

OpenGL、Vulkan、Direct3D 的 API 写法不同，但这个 mental model 基本通用。

## 2. CPU 和 GPU 各干什么

CPU 常见工作：

- 创建/更新 buffer；
- 创建 texture；
- 组织 scene；
- culling；
- 设置 pipeline/material；
- 录制/提交 draw command。

GPU 擅长：

- 大量 vertex 并行处理；
- rasterization；
- fragment shading；
- texture sampling；
- compute；
- 各种大规模并行 memory operation。

面试时不要只说：

> GPU 负责渲染。

更好的回答是：

> CPU 负责组织资源和命令，GPU 按提交的 pipeline 对大量数据并行执行。

## 3. Vertex Shader

Vertex Shader 一般处理：

- position；
- normal；
- UV；
- tangent；
- vertex color；
- skinning data。

典型 position：

```text
clipPosition =
Projection * View * Model * localPosition
```

Vertex Shader 输出的不是最终 pixel。

它主要输出：

- clip-space vertex position；
- 后面需要 interpolation 的 varying。

## 4. Primitive Assembly

GPU 会把 vertex 组成：

- triangle；
- line；
- point。

实时 3D 最常见的是 triangle。

为什么大家喜欢 triangle？

因为三个点一定共面，定义简单，硬件非常适合做 triangle rasterization。

## 5. Clipping

超出 clip volume 的 primitive：

- 完全在外面 → 丢掉；
- 一部分在外面 → 裁剪。

Clip-space position 是：

```text
(x, y, z, w)
```

之后做：

```text
NDC = xyz / w
```

这就是 homogeneous / perspective divide。

## 6. Rasterization

Rasterization 解决：

> 这个三角形到底覆盖屏幕上的哪些 sample？

它会生成 fragment，并对 vertex shader 输出的数据做 interpolation。

也就是说：

```text
连续的 triangle
↓
离散的 screen samples
```

这是传统 GPU pipeline 的核心固定功能之一。

## 7. Fragment Shader

Fragment Shader 对每个 candidate fragment 计算结果。

可以：

- sample texture；
- 算 lighting；
- 查 shadow map；
- discard；
- 写多个 render target。

注意：

> fragment ≠ 一定会成为最终 pixel。

它之后还可能被 depth test 干掉。

## 8. Depth Test 与 Blending

Depth Test：

> 这个 fragment 是否在已经画过的东西前面？

Blending：

> 这个 fragment 的颜色如何和 framebuffer 里已有颜色结合？

两者不能混为一谈。

典型透明：

```text
depth test 可以开
depth write 常常关
blending 开
```

具体策略取决于 renderer。

## 9. 为什么现代 Renderer 是 Multi-pass

一帧可能：

```text
Shadow Pass
↓
Geometry / G-buffer Pass
↓
Deferred Lighting
↓
Transparency
↓
Post Process
↓
UI
↓
Present
```

你的 AuroraShader 已经在做真正的 multi-pass。

## 10. Graphics Pipeline vs Compute

Graphics Pipeline 自带：

- triangle assembly；
- rasterization；
- interpolation；
- depth/stencil 等传统流程。

Compute Shader：

> 只是通用并行计算。

```text
Dispatch workgroups
→ threads 执行程序
→ 读写 buffer/image
```

Compute 不会自动帮你 rasterize triangle。

如果你以后 Vulkan 项目做 compute rasterizer：

> 传统硬件 raster pipeline 帮你做的很多事情，你都要自己重新实现。

这正是研究价值所在。

## 11. OpenGL 与 Vulkan 面试怎么理解

OpenGL：

> 大量状态和 driver 工作被隐藏。

Vulkan：

> 把更多责任暴露给程序员。

典型显式概念：

- command buffer；
- pipeline；
- descriptor；
- synchronization；
- image layout；
- queue；
- resource lifetime。

不要认为 Vulkan 是“画面更高级”。

更准确：

> Vulkan 给你更显式的 GPU execution/resource control。

## 12. 面试问题

**What does rasterization do?**

> It converts projected primitives into covered fragments and interpolates vertex outputs across them.

**Is a fragment the same as a pixel?**

> No. A fragment is a candidate contribution and may later be rejected or combined with other samples.

**What does a vertex shader mainly produce?**

> Clip-space position and values that later stages interpolate.

**Graphics vs Compute?**

> Graphics has specialized primitive/raster stages; compute is general parallel execution without automatic rasterization.

## 13. 和 AuroraShader 的对应

你的代码已经对应：

```text
shadow.vsh/fsh
→ Shadow Pass

gbuffers_*.vsh/fsh
→ Geometry Pass

deferred.fsh
→ Deferred Fullscreen Lighting

final.fsh
→ Final / Debug / Color Grading
```

## 14. 你必须能自己讲出来

不要背 API。

你需要不看资料讲：

```text
vertex
→ triangle
→ clipping
→ rasterization
→ interpolation
→ fragment shader
→ depth/blend
→ render target
→ later passes
→ display
```

然后指出 AuroraShader 每个 pass 在哪里。
