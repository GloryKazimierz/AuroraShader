# 第 7 章：Forward vs Deferred、MRT 与 G-buffer

## 1. Forward Rendering

传统 Forward：

```text
画一个 object
→ rasterize
→ fragment shader
→ 当场算 material + lighting
→ 写最终颜色
```

优点：

- 直观；
- transparency 更自然；
- MSAA 通常更容易；
- 不需要超大的 G-buffer。

潜在问题：

> light 很多时，同一个 object/pixel 的 lighting work 可能重复很多次。

## 2. Deferred Rendering

Deferred 把：

```text
Geometry
和
Lighting
```

拆开。

Geometry Pass：

> 先记录 visible surface data。

Lighting Pass：

> 后面再读取这些数据算光。

```text
Geometry
→ G-buffer
→ Screen-space Lighting
```

## 3. G-buffer 可以存什么

完整 PBR renderer 可能存：

- normal；
- albedo；
- roughness；
- metallic；
- emissive；
- material flags；
- depth；
- motion vector。

但：

> 每多存一个 channel，都增加 memory/bandwidth。

所以 G-buffer 设计是工程 trade-off，不是“越多越好”。

## 4. MRT

Multiple Render Targets：

> 一次 fragment shader invocation 同时写多个 attachment。

AuroraShader：

```text
colortex0 → scene color
colortex1 → normal + validity
colortex2 → block/sky light
```

这就是 MRT 的真实使用。

## 5. Deferred 为什么不一定更快

Deferred 可以减少 repeated lighting。

但会增加：

```text
Geometry 写很多 G-buffer
+
Lighting 又把它们读回来
```

高分辨率下 bandwidth 很贵。

所以面试不要说：

> Deferred 一定比 Forward 快。

正确：

> 它改变了 cost distribution，优势取决于 lights、materials、resolution、bandwidth 等。

## 6. Transparency 是 Deferred 的难点

普通 G-buffer 每个 pixel 通常只保留一层 surface。

但透明：

> 后面可能有多层 surface 都要贡献颜色。

所以传统 Deferred 对 transparency 不自然。

很多 engine：

```text
Opaque → Deferred
Transparent → Forward
```

AuroraShader 现在也有类似现象：

> water/glass/hand 等后画 category 不全进入 deferred relighting。

## 7. MSAA

Deferred + MSAA 可能很贵。

因为每个 MSAA sample：

> 可能需要不同 surface attributes 和 lighting。

Forward 与硬件 MSAA 往往结合更自然。

## 8. Forward+

Forward+：

> 保留 Forward shading，但先把屏幕分 tile/cluster，给每块建立 relevant light list。

这样 fragment 只考虑：

> 附近/相关 light。

这让 Forward 也能更好处理 many lights。

## 9. Clustered Shading

Clustered 进一步把 view volume 按 x/y + depth 分区。

比纯 2D tiled light culling 更适合：

> 深度范围很大的 many-light scene。

## 10. 面试问题

**Forward vs Deferred?**

> Forward 在 geometry draw 时直接 shading；Deferred 先保存 visible surface data，再 screen-space lighting。

**Why deferred for many lights?**

> 可以针对 visible pixels/light volume 做 lighting，而不是反复对 object 做完整 light evaluation。

**Deferred disadvantages?**

> G-buffer bandwidth/memory、transparency、MSAA complexity。

**What is MRT?**

> Fragment stage 一次写多个 render target。

**What is Forward+?**

> Forward shading + tiled/clustered light culling。

## 11. 和 AuroraShader 的关系

M2：

```text
Geometry
→ G-buffer metadata
→ Deferred Lambert
```

但你要诚实说明：

> colortex0 已经是 Minecraft prelit scene color，所以这不是一个完整“从 albedo 开始”的 PBR deferred renderer。

这反而是很好的面试回答，因为说明你知道 pipeline 的边界。
