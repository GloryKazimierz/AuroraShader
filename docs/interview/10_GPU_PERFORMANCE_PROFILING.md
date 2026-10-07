# Chapter 10: GPU Performance and Profiling

## 1. Never optimize from intuition alone

Real-time graphics performance is the time of the slowest relevant work on the
critical path.

A visually "complex" shader is not automatically the bottleneck.

You must measure.

## 2. Frame time matters more than FPS

FPS is nonlinear.

```text
frameTimeMs = 1000 / FPS
```

Examples:

- 60 FPS = 16.67 ms
- 120 FPS = 8.33 ms
- 144 FPS = 6.94 ms

Going from 30 to 40 FPS saves much more frame time than going from 130 to 140 FPS.

Compare milliseconds when optimizing.

## 3. CPU-bound versus GPU-bound

CPU-bound symptoms:

- GPU has idle gaps;
- reducing resolution changes little;
- draw-call/scene submission cost dominates.

GPU-bound symptoms:

- reducing resolution helps significantly;
- heavy shader/pass changes affect frame time;
- GPU workload is saturated.

Real frames can shift bottlenecks dynamically.

## 4. Vertex-bound, fragment-bound and bandwidth-bound

Possible GPU bottlenecks include:

- vertex/geometry processing;
- raster/fragment shading;
- texture sampling;
- memory bandwidth;
- compute;
- synchronization;
- fill rate;
- ray tracing traversal.

Do not assume "more shader instructions" is always the issue.

## 5. Fill rate and resolution scaling

If cost scales strongly with pixel count, suspect screen-space work:

- fragment shaders;
- G-buffer writes;
- fullscreen passes;
- post-processing.

A simple diagnostic:

> Reduce resolution. If frame time drops significantly, pixel-related GPU work is
> likely important.

## 6. Texture bandwidth and cache

Many texture reads do not translate directly into proportional time.

Performance depends on:

- locality;
- cache hit rate;
- format size;
- memory bandwidth;
- latency hiding;
- occupancy.

This is why 25 PCF taps do not mean a frame is exactly 25x slower.

## 7. Overdraw

Heavy transparent/particle/foliage scenes can execute fragment shading multiple
times per pixel.

Profiling overdraw helps separate geometry count from actual fragment cost.

## 8. Draw calls and state changes

On APIs/drivers with nontrivial submission overhead, many tiny draws can become a
CPU cost.

Common strategies:

- batching;
- instancing;
- reducing unnecessary state changes;
- GPU-driven rendering;
- indirect draws.

Modern explicit APIs change the cost model but do not make submission free.

## 9. Synchronization stalls

The GPU and CPU should work asynchronously.

Operations that force one side to wait can destroy parallelism.

Examples:

- CPU readback of GPU data;
- waiting for fences too early;
- unnecessary queue synchronization;
- pipeline barriers/layout transitions with overly broad scope.

Vulkan interviews often emphasize synchronization because it is explicit.

## 10. Occupancy and divergence

GPU threads execute in groups such as warps/wavefronts/subgroups.

Branch divergence can cause different lanes to serialize paths.

But "branches are always bad" is outdated.

Cost depends on:

- branch coherence;
- work per path;
- compiler;
- architecture.

Measure rather than blindly removing branches.

## 11. Arithmetic intensity

A shader can be:

- compute-heavy;
- bandwidth-heavy.

Arithmetic intensity asks how much computation is performed per byte moved.

This concept helps explain why some optimizations should reduce memory traffic
rather than ALU operations.

## 12. Profiling methodology

A strong workflow:

1. establish a repeatable scene;
2. disable FPS caps/VSync if appropriate;
3. measure stable frame time;
4. identify CPU or GPU bound;
5. capture a GPU frame/profile;
6. find the expensive pass;
7. change one variable;
8. retest;
9. verify visual correctness;
10. keep/regress the benchmark.

## 13. Common tools

Depending on platform:

- RenderDoc: frame capture/debugging;
- Nsight Graphics: NVIDIA graphics profiling;
- Radeon GPU Profiler;
- PIX: Direct3D;
- Xcode GPU tools: Metal.

Know the purpose of these tools even if you have not mastered all of them.

## 14. Common interview questions

### FPS versus frame time?

Frame time is linear work budget; FPS is its reciprocal and can hide the magnitude
of improvements.

### How detect GPU-bound?

Test resolution/workload sensitivity and inspect CPU/GPU timelines with a profiler.

### Why can many texture samples be expensive?

They add memory/cache/latency and comparison work, but cost depends heavily on
locality and hardware.

### Are branches always bad on GPU?

No. Divergent branches can serialize lanes, but coherent branches may be cheap.

### What is the first rule of optimization?

Measure before and after; do not optimize unsupported guesses.

## 15. AuroraShader connection

M4/M5 benchmark documents are your first profiling discipline:

- fixed scene;
- same settings;
- change one shadow filter;
- record frame time and quality;
- avoid claiming performance from sample count alone.

That methodology matters more in interviews than a made-up FPS number.
