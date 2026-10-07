# 第 11 章：GLSL & Graphics Debugging / Shader 调试

## 1. 黑屏不是“问题原因”

Black screen 只是症状。

原因可能：

- shader compile fail；
- link fail；
- vertex transform；
- framebuffer；
- texture binding；
- depth state；
- culling；
- wrong uniform；
- coordinate mismatch；
- NaN；
- pass ordering。

所以 Debug Renderer 要：

> 一层一层隔离 pipeline。

## 2. 从已知正确 Baseline 开始

最好：

```text
Old Milestone Works
↓
只加一个小变化
↓
加入 debug visualization
↓
验证
↓
再继续
```

你的 M1→M5 结构其实就是很好的工程习惯。

## 3. Compile / Link

第一件事：

> 看 log。

检查：

- syntax；
- GLSL version；
- type；
- varying mismatch；
- preprocessor；
- extension；
- sampler/uniform。

Shader 根本没 link 成功时，不要先研究“是不是 lighting formula 错了”。

## 4. Debug Color

非常实用：

```text
Branch A → red
Branch B → green
Branch C → blue
```

Vector visualization：

```text
normal * 0.5 + 0.5
```

Debug View 往往比盯代码 30 分钟更快。

## 5. 用“运动行为”判断 Coordinate Bug

Normal Debug：

> Camera 转动时，View Space Normal 应该按预期变化。

Shadow：

> Camera 移动时，shadow 应该附着在 world geometry。

如果 shadow 跟 camera 滑：

> transform contract 很可能错。

这是利用视觉行为分类 bug。

## 6. Pipeline Binary Search

最终颜色错了：

不要一次改十个文件。

反向：

```text
Final Color
↓
Raw Lighting Buffer
↓
G-buffer
↓
Geometry Output
↓
Constant Color
```

找到：

> 第一处开始错误的数据。

这就是 graphics debugging 的“二分”。

## 7. NaN / Inf

危险来源：

- normalize zero；
- divide by zero；
- sqrt(negative)；
- log(<=0)；
- clip.w = 0。

NaN 会传播。

所以 AuroraShader 有：

```text
safeNormal()
```

和 validity flag。

这不是“多余代码”，是 defensive shader programming。

## 8. Texture Debug

Texture 错：

检查：

- binding；
- size；
- format；
- UV range；
- wrap；
- filter；
- mip；
- sRGB；
- sampler type。

Shadow 最好的 debug 之一：

> 直接把 raw shadow depth 显示出来。

## 9. Framebuffer / MRT

检查：

- attachment 是否存在；
- format；
- dimensions；
- clear color；
- output location；
- draw buffer mapping；
- metadata 有没有错误 blending。

AuroraShader 对 normal/light metadata：

> 显式关 blending。

非常合理。

## 10. State Bug

OpenGL 常见：

- wrong VAO；
- wrong program；
- wrong texture unit；
- depth test 忘开；
- blend 忘关；
- viewport 错；
- culling 错。

Vulkan hidden state 少一些，但会换成：

- descriptor；
- image layout；
- synchronization；
- pipeline state；
- resource lifetime。

## 11. RenderDoc

以后一定值得学。

RenderDoc 可以看：

- draw call；
- pipeline state；
- mesh；
- texture；
- framebuffer；
- shader input/output；
- pixel history。

对于 Graphics Engineer：

> 会 frame debugger 的价值非常高。

## 12. Regression Test

Renderer 新 feature 很容易：

> 修 A，坏 B。

所以保留：

- fixed test scene；
- debug mode；
- validation；
- screenshot；
- benchmark。

你的 milestone checklist 就是在做 regression discipline。

## 13. 面试问题

**How debug a black screen?**

> 先看 compile/link/log，确认 framebuffer/viewport，再用 constant output 和逐级 buffer visualization 找第一处错误。

**How debug coordinate-space bug?**

> 可视化中间 vector/position，并通过 camera/object controlled motion 验证 transform contract。

**Why visualize G-buffer?**

> 可以在 lighting 之前确认 intermediate data 是否已经错。

**Why NaN dangerous?**

> 会沿 arithmetic 传播，让后续输出失效/异常。

## 14. 和项目对应

你已经有：

- Normal Debug；
- Block/Sky Debug；
- NdotL Debug；
- Raw Shadow Depth；
- Shadow Visibility。

这不是“为了好看”。

这是一个真正 renderer 应该有的：

> observability。

面试里可以强调这一点。
