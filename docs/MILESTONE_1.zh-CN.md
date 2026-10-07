# Milestone 1：Color Grading / 颜色后处理

> 中文学习版。英文原版：[MILESTONE_1.md](MILESTONE_1.md)

**状态：** 已经通过 Minecraft 实机测试。

Milestone 1 是 AuroraShader 最基础的后处理阶段：**场景已经渲染完以后，再修改最终颜色**。它不改变几何体、深度、法线或光照结构。

## 1. 先记住数据流

```text
Minecraft 渲染场景
        ↓
colortex0 保存场景颜色
        ↓
final.fsh 读取 colortex0
        ↓
gradeColor(scene.rgb)
        ↓
屏幕最终颜色
```

所以 M1 本质上是：

> 已经有一张图了，我再对每个 pixel 的 RGB 做处理。

## 2. Exposure / 曝光

Exposure 用“stop”来理解：

```text
+1 stop ≈ 线性光强乘 2
-1 stop ≈ 线性光强乘 0.5
```

当前实现大致：

```text
显示 RGB
→ 近似转 linear
→ 乘 2^exposure
→ 再转回显示空间
```

对应：

```glsl
color = pow(max(color, vec3(0.0)), vec3(2.2));
color *= exp2(EXPOSURE);
color = pow(color, vec3(1.0 / 2.2));
```

重点不是死记代码，而是理解：

> 亮度/光强运算更适合在 linear space 中进行。

## 3. Temperature / Tint

Temperature：

- 负数：更冷
- 正数：更暖

Tint：

- 负数：更绿
- 正数：更偏洋红

这里是简单的 RGB artistic adjustment，**不是严格 Kelvin 色温/白平衡模型**。

面试时不要说成“我实现了物理正确的 white balance”。

## 4. Saturation / 饱和度

先算 luminance：

```text
gray = dot(color, (0.2126, 0.7152, 0.0722))
```

然后：

```text
mix(gray, color, saturation)
```

所以：

- 0 = 完全灰度
- 1 = 原始饱和度
- >1 = 更鲜艳

## 5. Contrast / 对比度

围绕 0.5 调整：

```text
(color - 0.5) * contrast + 0.5
```

contrast > 1：

> 黑的更黑、亮的更亮。

contrast < 1：

> 整体更“灰”、差异更小。

## 6. 为什么处理顺序重要

当前顺序：

```text
Exposure
→ Temperature/Tint
→ Saturation
→ Contrast
→ Grayscale
→ Clamp
```

这些操作通常不能随便交换。

例如：

> 先调 contrast 再调 saturation，和反过来做，结果未必一样。

这就是 shader pipeline 中很常见的 **operation ordering** 问题。

## 7. LDR 限制

最后：

```text
clamp(color, 0, 1)
```

意味着超过 1 的亮部会直接被截断。

所以当前还不是完整 HDR pipeline，也没有：

- tone mapping；
- auto exposure；
- filmic curve；
- HDR scene buffer。

## 8. 你真正应该学到什么

M1 最重要的不是“会调颜色”，而是理解：

1. Fullscreen post-process 是什么。
2. Render target 可以作为后续 shader 的输入。
3. Shader option 怎么暴露给用户。
4. Linear / gamma 空间为什么不同。
5. 为什么后处理顺序会影响结果。
6. Artistic control 和 physically calibrated transform 的区别。
7. 为什么 HDR/Tone Mapping 会成为下一层问题。

## 9. 代码阅读顺序

1. `shaders/lib/settings.glsl`
2. `shaders/lib/color.glsl`
3. `shaders/final.fsh`
4. `shaders/shaders.properties`
5. `shaders/lang/en_us.lang`

## 10. 面试高频

**What is a post-process?**

> A fullscreen operation applied to an already rendered image or render target.

**Why apply exposure in linear space?**

> Because light intensity behaves linearly there; gamma/display values are not proportional to physical light.

**What does +1 exposure stop mean?**

> Approximately twice the linear light.

**Why does order matter?**

> Color operations are generally not commutative, so changing the order changes the output.

**What is the limitation of LDR clamp?**

> Highlight information above the display range is discarded instead of preserved for tone mapping.

## 11. 60 秒项目解释

> Milestone 1 是一个 fullscreen color-grading pass。我读取已经渲染好的 scene color，然后实现 exposure、temperature/tint、saturation、contrast 和 grayscale。neutral 参数保持原画面。Exposure 用近似 gamma-to-linear 的方式处理，而 temperature/tint 是艺术性的 RGB adjustment，不是严格白平衡。最终仍然是 LDR 并 clamp 到 [0,1]，所以强曝光时会发生 highlight clipping。
