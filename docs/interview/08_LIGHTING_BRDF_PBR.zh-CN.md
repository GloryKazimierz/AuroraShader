# 第 8 章：Lighting、BRDF 与 PBR 基础

## 1. Lighting 到底在算什么

核心问题：

> 一束光从某个方向打到 surface 后，有多少能量朝 camera 方向出去？

常见方向：

- N = normal
- L = toward light
- V = toward viewer
- H = L 和 V 的 halfway vector

## 2. Lambert Diffuse

AuroraShader 已经用了：

```text
max(N dot L, 0)
```

直觉：

> 光越正着打 surface，单位面积收到的能量越高。

更物理规范的 Lambert BRDF 会包含：

```text
albedo / π
```

你的项目现在是艺术性/教学式 Lambert modulation，不是完整 physically normalized BRDF。

## 3. Specular

Specular 不只是 N·L。

它强烈依赖：

- view direction；
- light direction；
- surface microstructure。

老模型：

- Phong；
- Blinn-Phong。

现代 PBR 常用 microfacet BRDF。

## 4. BRDF 是什么

Bidirectional Reflectance Distribution Function。

它描述：

> 光从方向 L 入射，surface 有多少反射到 V 方向。

概念：

```text
f_r(L, V)
```

Physically plausible BRDF 通常要考虑：

- energy conservation；
- reciprocity；
- 合理 directional response。

## 5. Microfacet BRDF

常见 Cook-Torrance 风格：

```text
D * F * G
------------
4(N·L)(N·V)
```

不要只背公式。

### D

Normal Distribution Function。

> 微表面法线怎么分布。

### F

Fresnel。

> 在当前角度反射多少。

### G

Geometry / Masking-Shadowing。

> 微表面彼此遮挡多少。

## 6. Roughness

Roughness 主要控制：

> microfacet orientation spread。

低 roughness：

- 高光窄；
- 边缘锐。

高 roughness：

- 高光宽；
- 能量分散。

Roughness 不等于“specular strength”。

## 7. Fresnel

一个很重要的事实：

> 很多材质在 grazing angle 看起来都会更反光。

常见 Schlick：

```text
F = F0 + (1-F0)(1-cosθ)^5
```

F0 是接近法线方向的基础反射率。

## 8. Metallic Workflow

常见 metallic-roughness：

Dielectric：

- base color 多用于 diffuse；
- specular F0 相对低。

Metal：

- 基本没有传统 diffuse；
- base color 更多影响 colored specular。

不同 engine encoding 会有差异，所以不要把某一个 engine implementation 当成宇宙定律。

## 9. Energy Conservation

不能让 material：

> 反射出去的能量比收到的还多。

所以 PBR 中：

> specular 增加时，diffuse 可用能量通常要相应减少。

不能简单：

```text
diffuse + huge specular
```

无脑相加。

## 10. Direct vs Indirect Lighting

Direct：

> 从 light 直接到 surface。

Indirect：

> 光经过环境/其他 surface bounce 后到达。

Indirect 方法：

- lightmap；
- probe；
- environment map；
- GI；
- path tracing。

AuroraShader 的 ambient：

> 是艺术近似，不是算出来的真实 GI。

## 11. IBL

Image-Based Lighting：

> 用 environment map 表示来自大量方向的环境光。

常见 PBR IBL：

- diffuse irradiance；
- prefiltered specular environment；
- BRDF LUT。

这是以后做完整 PBR renderer 很常见的一步。

## 12. 面试问题

**What is Lambert diffuse?**

> 基于 max(N·L,0) 的 cosine diffuse；规范 Lambert BRDF 常写 albedo/π。

**What is BRDF?**

> 描述 incoming direction 到 outgoing/view direction 的反射函数。

**D/F/G?**

> microfacet distribution、Fresnel、geometry masking-shadowing。

**Roughness vs Metallic?**

> Roughness 控制 microfacet spread；metallic 改变材质主要反射机制和 diffuse/specular 分配。

**Direct vs indirect?**

> Direct 没有 scene bounce；indirect 已经过环境/其他 surface interaction。

## 13. 和 AuroraShader 的关系

你现在：

```text
M2 = N dot L + ambient/direct artistic modulation
```

还不是 PBR。

面试更好的说法：

> 我的当前 shader 是有意保持简单的 deferred Lambert 教学实现。真正升级 PBR，需要先把 albedo/material data 从 Minecraft prelit scene 中更明确地分离，再加入 BRDF，而不是直接硬叠一个 specular。

这说明你知道下一步架构问题。
