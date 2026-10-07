# Milestone 3A：基础 Hard Shadow Mapping

> 中文学习版。英文原版：[MILESTONE_3A.md](MILESTONE_3A.md)

**状态：** 静态检查通过，并且已经由你在 Minecraft 中确认实机运行正确。

Milestone 3A 是 AuroraShader 第一次真正加入“遮挡阴影”。

M2 只知道：

> 这个表面朝不朝向太阳？

M3A 开始回答：

> 就算它朝向太阳，中间有没有东西挡住光？

---

## 1. Shadow Mapping 的核心

Shadow Mapping 可以理解成：

> 先让“光源”当一次摄像机。

从光源视角渲染场景，只保存最近深度：

```text
shadow map = light POV depth image
```

之后真正从玩家视角渲染时：

1. 找到当前 pixel 对应的 3D receiver。
2. 把 receiver 变换到 light space。
3. 看它在 shadow map 哪个位置。
4. 比较 receiver depth 和 stored depth。

如果 receiver 更远：

> 前面有别的物体挡住光。

于是进入 shadow。

---

## 2. 整个 Pipeline

```text
Shadow Pass
  ↓
shadowtex1 保存 light-space depth

Camera / G-buffer Pass
  ↓
保留 scene color / normal / light levels / camera depth

Deferred Pass
  ↓
从 camera depth 重建 receiver position
  ↓
转到 light space
  ↓
做一次 depth comparison
  ↓
得到 visibility 0 或 1
  ↓
只影响 direct Lambert light
```

这是最基础的 Hard Shadow Mapping。

---

## 3. 为什么不额外保存 Position Buffer

你可能会想：

> 为什么不直接给每个 pixel 存 world position？

这个项目没有这么做，而是从 `depthtex1` 重建 position。

原因之一：

> Position 可以从 depth + inverse matrices 恢复，省一个额外 G-buffer attachment。

这也是很多 deferred renderer 的常见思路。

---

## 4. Receiver Position Reconstruction

核心步骤：

```text
screenUV
↓
camera depth
↓
camera NDC
↓
gbufferProjectionInverse
↓
view position
↓
gbufferModelViewInverse
↓
player-relative position
```

之后：

```text
shadowModelView
↓
shadowProjection
↓
light clip
↓
divide by w
↓
light NDC
↓
shadow UV + depth
```

---

## 5. 为什么要除以 w

Clip Space 中 position 是 homogeneous coordinate：

```text
(x, y, z, w)
```

要进入 NDC：

```text
(x/w, y/w, z/w)
```

这就是 perspective divide / homogeneous divide。

这个步骤不能漏。

---

## 6. 当前坐标空间 Contract

M3A 里一个非常重要的点：

```text
playerPosition
```

不是绝对 world coordinate。

它是：

> Iris player-relative / feet-relative 的 world-oriented space。

所以不要再额外加 `cameraPosition`。

否则 caster 和 receiver 使用的 coordinate convention 会不一致，阴影可能跟着 camera 漂。

---

## 7. Hard Shadow Comparison

shadow map 中存：

```text
storedDepth
```

receiver 在 light space 中有：

```text
receiverDepth
```

比较：

```text
receiverDepth - bias <= storedDepth
```

成立：

```text
visibility = 1
```

不成立：

```text
visibility = 0
```

因此 Hard Shadow 的结果是二值的。

---

## 8. Bias

默认：

```text
SHADOW_BIAS = 0.0002
```

注意单位：

> 这是 normalized shadow-depth units，不是 block。

它主要用来缓解 self-shadowing / shadow acne。

bias 太小：

```text
acne
```

bias 太大：

```text
peter-panning / detached shadow
```

---

## 9. 为什么 Shadow 只影响 Direct Light

Lighting：

```text
lambert =
AMBIENT_LIGHT
+
DIRECT_LIGHT * NdotL * visibility
```

这里 shadowVisibility 只乘在 direct term 上。

这是合理的简化：

> 被太阳挡住，不等于环境光、火把光全部消失。

所以阴影区域仍然可以有 ambient / block lighting。

---

## 10. Shadow Map 参数

当前：

```text
shadowMapResolution = 2048
shadowDistance = 64
```

并且：

- 不用 cascades；
- 不做 distortion；
- 不做 mipmap；
- M3A 不做 PCF；
- hardware filtering 关闭。

因此这是非常直接、容易学习的 raw shadow map。

---

## 11. Caster Scope

当前重点 caster：

- terrain；
- cutout terrain；
- block entities。

不完整支持：

- translucent geometry；
- player；
- entities as casters；
- glass/water transmission；
- colored shadow。

这不是 bug，而是 M3A 的 scope 控制。

---

## 12. Alpha Cutout

树叶这类 texture 不能整个 quad 都投影。

所以 shadow fragment shader 会根据 alpha：

```text
alpha < threshold
→ discard
```

这样透明洞不会写 shadow depth。

因此树叶阴影至少能保留洞，而不是整块矩形。

---

## 13. Debug 4：Raw Shadow Depth

Debug 4 直接把 shadowtex1 显示到屏幕。

它看起来像：

> 从光源角度看到的 grayscale depth image。

注意：

- 它不是 camera view；
- orthographic depth 可能对比度很低；
- 空区域可能是白色。

---

## 14. Debug 5：Shadow Visibility

Debug 5 显示：

```text
white = lit
black = shadow
```

它比 raw depth 更容易判断：

> receiver 到底有没有通过 shadow test。

---

## 15. 常见 Bug 怎么判断

### Shadow 跟着 Camera 走

大概率：

```text
coordinate transform mismatch
```

### 全白 Raw Depth

可能：

- 没 caster；
- shadow pass 没写进去；
- map 没正确绑定。

### Visibility 全黑

可能：

- reconstruction 错；
- coordinate space 错；
- bias 错；
- depth compare 错。

### 地面黑色条纹

通常：

```text
shadow acne
```

### 阴影和物体分离

通常：

```text
bias 太大
```

### 远处突然没阴影

当前单张 64-block shadow map 的 coverage limitation。

---

## 16. M3A 最大的学习价值

你真正要学的是：

1. Shadow pass 是什么。
2. Light-space depth map 是什么。
3. Camera depth 如何重建 position。
4. Matrix inverse 的实际用途。
5. View → player-relative → light view → light clip。
6. Homogeneous divide。
7. Shadow UV mapping。
8. Depth comparison。
9. Bias。
10. Direct light visibility。

---

## 17. 面试回答

**How does shadow mapping work?**

> Render scene depth from the light, project the visible receiver into that light-space depth map, then compare depths to determine occlusion.

**Why reconstruct position from depth?**

> It avoids storing a full position attachment and uses the camera depth plus inverse projection/model-view matrices.

**Why does the shadow move with the camera when transforms are wrong?**

> Because the receiver and shadow caster are no longer expressed consistently in light/world-related coordinates.

**Why only shadow direct light?**

> Blocking the main directional light does not imply all ambient or local lighting disappears.

---

## 18. 60 秒项目解释

> M3A 给 deferred pipeline 加入了基础 Shadow Mapping。我让 Iris 从太阳/月亮的光源视角渲染一个 2048² depth shadow map。在 deferred pass 里，我从 camera depth 重建每个 receiver 的 view-space position，再转换到 Iris 的 player-relative space，然后经过 shadowModelView 和 shadowProjection 进入 light clip space，做 perspective divide 后得到 shadow UV 和 depth。最后进行一次 depth comparison 得到 0/1 visibility，并只把 visibility 乘到 direct Lambert term 上，因此 ambient 和 Minecraft block lighting 仍然保留。默认 constant bias 是 0.0002，用来减少 shadow acne。
