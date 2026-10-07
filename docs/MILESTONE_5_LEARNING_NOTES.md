# Milestone 5 Learning Notes: Poisson PCF

This document is for learning the code, not just using the shader.

## 1. The one idea to remember

PCF answers:

> If I look at several nearby places in the shadow map, what percentage say this receiver can see the light?

Hard shadow mapping uses one comparison.

3x3 PCF uses nine comparisons.

5x5 PCF uses twenty-five comparisons.

Milestone 5 Poisson PCF uses eight comparisons, but places them irregularly inside a disk.

The important lesson is:

```text
sample count != sample distribution
```

Two filters with the same sample count can look different because they sample different positions.

---

## 2. Start from compareShadow()

The most important helper is conceptually:

```glsl
float compareShadow(vec2 shadowUV, float receiverDepth, ivec2 mapSize)
```

It performs one visibility test.

The logic is:

```text
1. Convert UV into a shadow-map texel.
2. Read the depth stored from the light's point of view.
3. Compare receiverDepth against storedDepth.
4. Return 1 if visible to the light.
5. Return 0 if blocked.
```

In simplified form:

```text
receiverDepth - bias <= storedDepth
```

If true:

```text
visibility = 1
```

Otherwise:

```text
visibility = 0
```

Everything else in PCF is mostly about deciding how many times to call this function and where to sample.

---

## 3. Hard shadow mode

Hard mode is the easiest possible filter:

```text
visibility = compareShadow(center)
```

Only one point in the shadow map is examined.

This makes the result binary:

```text
0 = shadow
1 = light
```

There are no intermediate values.

That is why the edge can look jagged.

---

## 4. Why 3x3 PCF creates gray values

A 3x3 filter samples:

```text
x x x
x x x
x x x
```

Suppose the nine tests produce:

```text
1 1 1
1 1 0
0 0 0
```

There are five lit samples.

So:

```text
visibility = 5 / 9
           ≈ 0.556
```

The pixel is therefore partially lit.

This does not mean the shadow map contains a gray depth value.

It means the shader averaged several binary visibility decisions.

This is one of the most important PCF concepts for interviews.

---

## 5. Why Poisson sampling exists

A regular grid has obvious structure.

For example:

```text
x x x
x x x
x x x
```

The samples line up in rows and columns.

When the shadow edge also lines up with this structure, the filtering error can become visually structured.

Poisson-style sampling instead looks more like:

```text
      x

  x       x

      x

 x            x

    x      x
```

The samples are spread out irregularly.

This does not eliminate error.

It changes the error from something that may look like a grid into something less regularly structured.

That is a recurring graphics idea:

> Sometimes a less structured error is less noticeable than an equally large structured error.

---

## 6. Read the Milestone 5 code

The Poisson branch uses eight fixed offsets.

Conceptually:

```glsl
vec2 tapStepUV = SHADOW_SOFTNESS / vec2(mapSize);
```

Interpret this carefully.

`1 / mapSize` converts one shadow-map texel into UV distance.

Then each Poisson offset is multiplied by that texel-scale.

So:

```text
Poisson point
x shadow texel size
x softness
=
final UV offset
```

Each tap then does:

```glsl
visibility += compareShadow(
    shadowCoord.xy + poissonOffset * tapStepUV,
    shadowCoord.z,
    mapSize
);
```

Finally:

```glsl
return visibility / 8.0;
```

That is the entire filter.

Do not let the code look more complicated than the concept actually is.

---

## 7. What SHADOW_SOFTNESS really changes

In this implementation, softness changes the distance between the center and the taps.

It does NOT change:

- the shadow map resolution;
- the number of samples;
- the light size;
- blocker distance;
- receiver distance.

For Poisson PCF:

```text
softness = 0
all offsets collapse to the center

softness = 1
use the original disk radius

softness = 2
sample twice as far away
```

This is why the control is useful artistically but is not physically based.

---

## 8. Why softness = 0 should approach Hard

Suppose every offset is multiplied by zero.

Then:

```text
offsetUV = poissonOffset * 0
         = (0, 0)
```

All eight samples read the center.

If the center comparison is lit:

```text
(1+1+1+1+1+1+1+1) / 8 = 1
```

If it is shadowed:

```text
(0+0+0+0+0+0+0+0) / 8 = 0
```

So Poisson softness zero should converge to the Hard result.

This is a very useful sanity check.

---

## 9. Why 8 Poisson samples can compete with 25 grid samples

It is NOT because eight magically contains more information than twenty-five.

Possible reasons include:

- the samples cover the region differently;
- the irregular pattern can hide grid structure;
- the eye may notice regular artifacts more strongly than irregular ones;
- the extra 5x5 samples may be redundant for some edges.

But this is scene-dependent.

The correct engineering attitude is:

```text
hypothesis -> implement -> benchmark -> compare
```

Do not claim one filter is better before measuring it.

---

## 10. Performance thinking

Per eligible receiver, approximate logical comparisons are:

| Filter | Comparisons |
|---|---:|
| Hard | 1 |
| 3x3 PCF | 9 |
| 5x5 PCF | 25 |
| Poisson PCF | 8 |

This is not the same as total frame cost.

The final GPU cost also depends on:

- how many pixels receive shadowing;
- texture cache behavior;
- memory latency;
- other shader work;
- resolution;
- GPU architecture;
- driver/compiler optimization;
- whether the game is CPU-bound.

Graphics engineers often separate:

```text
local shader cost
```

from:

```text
whole-frame performance
```

---

## 11. Why texelFetch matters

The implementation uses discrete texel reads.

That means the shader is explicitly choosing shadow-map texels rather than asking ordinary texture filtering to interpolate them.

This makes the educational experiment easier to reason about:

```text
one tap -> one discrete stored depth
```

However, fractional Poisson offsets are eventually converted to integer texel coordinates.

Therefore multiple logical taps may sometimes hit the same physical texel.

This becomes more likely with small softness values.

So:

```text
8 logical taps
```

does not always guarantee:

```text
8 unique shadow texels
```

That is a subtle but important real-world detail.

---

## 12. Spatial aliasing versus temporal aliasing

### Spatial aliasing

Artifacts visible in a still image:

- jagged edges;
- blocky shadow boundaries;
- repeated grid patterns.

### Temporal aliasing

Artifacts visible while the camera or light moves:

- shimmer;
- flicker;
- crawling edges;
- sudden visibility changes.

A filter may look excellent in a screenshot but unstable in motion.

That is why runtime testing must include camera movement.

Graphics quality cannot be judged only from still images.

---

## 13. Fixed Poisson pattern versus randomized Poisson

Milestone 5 uses a fixed pattern.

Advantages:

- deterministic;
- simple;
- easy to debug;
- stable code;
- easy to validate.

A randomized or rotated pattern can break repeated spatial structure further.

But then the error can change between pixels or frames.

That may create noise or temporal shimmer.

So randomization creates another trade-off:

```text
less structured spatial error
vs
possible temporal instability
```

This is why modern real-time rendering frequently combines stochastic sampling with temporal accumulation or denoising.

---

## 14. Poisson PCF is still PCF

Do not mentally treat Poisson as a completely different shadow algorithm.

The shadow algorithm is still:

```text
Shadow Mapping
  -> depth comparison
  -> multiple neighboring comparisons
  -> average visibility
```

The only thing that changed is the sample pattern.

This is important when explaining the project in an interview.

---

## 15. Poisson PCF versus PCSS

Milestone 5:

```text
fixed filtering radius
+
irregular samples
```

PCSS tries to estimate a changing penumbra.

Conceptually:

```text
Step 1: search for blockers

Step 2: estimate blocker distance

Step 3: estimate how wide the penumbra should be

Step 4: PCF using that variable radius
```

The intended visual behavior is:

```text
near contact
-> sharper

farther from blocker
-> softer
```

Milestone 5 does not do this.

---

## 16. Code-reading exercise

Open:

`shaders/lib/shadow.glsl`

Find these functions:

```text
compareShadow()
filterShadow()
shadowVisibility()
```

Be able to explain their responsibilities.

### compareShadow()

One shadow-map visibility decision.

### filterShadow()

Decides how many nearby comparisons are taken and averages them.

### shadowVisibility()

Finds where the current camera-visible receiver lies in the light's shadow map.

A useful mental decomposition is:

```text
Where am I in the light's image?
            |
            v
shadowVisibility()

How do I filter around that position?
            |
            v
filterShadow()

Is this individual position visible?
            |
            v
compareShadow()
```

---

## 17. What you should be able to explain now

Without reading notes, try to answer:

1. What information is stored in a shadow map?
2. Why do we need to transform the receiver into light space?
3. What exactly does compareShadow return?
4. What does PCF average?
5. Why can PCF return values between zero and one?
6. Why does 5x5 cost more than 3x3?
7. What is the difference between sample count and sample distribution?
8. Why can regular grid sampling create visible structure?
9. Why can Poisson sampling help?
10. Why can Poisson sampling still shimmer?
11. What does softness control in this implementation?
12. Why does softness zero approach Hard mode?
13. Why is Poisson PCF not PCSS?
14. Why must screenshots and motion both be tested?

If you can answer those naturally, you understand Milestone 5 at a useful graphics-engineering level.

---

## 18. One-minute interview answer

> I implemented shadow mapping first with a single hard depth comparison. Then I
> added grid-based PCF, where multiple neighboring binary depth comparisons are
> averaged into fractional visibility. I compared 3x3 and 5x5 kernels to understand
> the quality-versus-sampling-cost trade-off. After that I added an eight-tap
> Poisson-style filter. The important difference is not the underlying shadow
> algorithm but the sample distribution: irregular taps can reduce visible grid
> structure with a smaller sample budget. The implementation still uses a fixed
> radius, so it does not provide physically based contact hardening like PCSS, and
> temporal stability still needs runtime testing.

That is already a strong answer for an intern/junior rendering interview.
