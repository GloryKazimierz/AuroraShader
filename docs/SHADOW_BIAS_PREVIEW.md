# Next Topic Preview: Shadow Bias, Acne, and Peter-Panning

This note prepares the next shadow milestone.

Milestone 5 changes filtering.

The next problem is different:

> How should the depth comparison tolerate numerical and geometric error?

That is the shadow-bias problem.

---

## 1. Start from the depth comparison

The project currently uses the idea:

```text
receiverDepth - bias <= storedDepth
```

Without bias:

```text
receiverDepth <= storedDepth
```

sounds perfect.

But real rasterization is not mathematically perfect.

The depth stored during the shadow pass and the depth reconstructed during the camera
pass can differ slightly even for the same physical surface.

That tiny difference can make a surface shadow itself.

---

## 2. Shadow acne

Shadow acne usually appears as:

- dark stripes;
- speckled patterns;
- self-shadowing;
- moire-like artifacts.

Conceptually:

```text
actual surface
      |
      v

stored depth      = 0.50000
receiver depth    = 0.50003

0.50003 <= 0.50000
false
```

The shader concludes that another object blocks the light.

But there is no blocker.

The surface is blocking itself because of numerical/sampling mismatch.

---

## 3. Constant bias

Add a small tolerance:

```text
receiverDepth - 0.0002 <= storedDepth
```

Using the example:

```text
0.50003 - 0.0002
=
0.49983
```

Now:

```text
0.49983 <= 0.50000
true
```

The false self-shadow disappears.

That is why bias works.

---

## 4. Why bias cannot simply be very large

Suppose you keep increasing bias.

Eventually real occlusion can be ignored near the caster.

The shadow appears detached from the object.

This is called:

```text
peter-panning
```

Visually:

```text
object
████

     shadow
     ███████
```

instead of:

```text
object
████████shadow
```

The name comes from the impression that the object is floating above its shadow.

---

## 5. The fundamental trade-off

Too little bias:

```text
shadow acne
```

Too much bias:

```text
peter-panning
```

So constant bias tuning is a compromise.

There is no universally perfect constant value for every:

- surface orientation;
- shadow-map resolution;
- projection;
- scene scale;
- light direction.

---

## 6. Why grazing-angle surfaces are difficult

Consider a surface almost parallel to the light direction.

Across a small movement on the surface, light-space depth can change relatively quickly.

A tiny displacement in shadow-map coordinates can therefore correspond to a larger
depth change.

This makes sloped/grazing surfaces more sensitive to self-shadowing.

That motivates slope-aware bias.

---

## 7. Slope-scaled bias intuition

The idea is:

```text
flat / favorable surface
-> small bias

steep depth slope
-> larger bias
```

A common conceptual form is:

```text
bias =
constantBias
+
slopeFactor * depthSlope
```

The exact implementation depends on the pipeline.

Do not memorize one API-specific formula yet.

Understand the reason:

> The amount of tolerance should relate to how quickly shadow depth changes across the surface.

---

## 8. Normal-based bias intuition

Another family of approaches offsets the receiver based partly on the surface normal and light direction.

If:

```text
N dot L
```

is small, the surface is at a grazing angle relative to the light.

That can justify a larger offset.

Conceptually:

```text
grazing surface
-> more bias

surface facing light directly
-> less bias
```

Again, this is a heuristic.

---

## 9. Receiver-plane bias

A more advanced idea estimates how the receiver's depth changes across the shadow-map plane.

Instead of blindly using one constant bias, it tries to predict the correct depth adjustment for nearby PCF samples.

This becomes especially relevant because PCF samples positions around the center.

A single center bias may be imperfect for every neighboring tap.

You do not need to implement this immediately.

But it is useful to know that professional shadow filtering often treats bias and filtering together.

---

## 10. Filtering does not solve bias

Important misconception:

```text
soft shadow filter
!=
bias solution
```

PCF can smooth the visible appearance of a shadow edge.

It does not remove the underlying depth-comparison problem.

You can still have:

- acne with PCF;
- peter-panning with PCF;
- acne with Poisson PCF;
- peter-panning with Poisson PCF.

Sampling and bias are related but separate engineering problems.

---

## 11. Debug experiment for the next milestone

Use a scene with:

- flat ground;
- vertical wall;
- sloped blocks/surfaces;
- long directional shadows.

Try several bias values.

For example, using only values already exposed by the project:

```text
0
0.00005
0.0001
0.0002
0.0005
0.001
0.002
```

For each value observe:

```text
acne?
contact gap?
thin geometry?
grazing surfaces?
distant geometry?
```

Do not select a value only because one screenshot looks good.

Move the camera and change world time.

---

## 12. What the next milestone should teach

A good next milestone should compare:

```text
constant bias
vs
angle/slope-aware bias
```

while keeping the shadow filtering unchanged.

That isolates the experiment.

The lesson should be:

```text
M4/M5:
Where should I sample?

Next milestone:
How should I compare depth robustly?
```

Those are different questions.

---

## 13. Interview questions

You should eventually be able to answer:

### What causes shadow acne?

Small mismatches between receiver depth and stored shadow depth can make a surface
incorrectly fail its own visibility test.

### Why does bias help?

It adds tolerance to the comparison so small numerical/sampling differences do not
become false occlusion.

### What is peter-panning?

Too much bias separates the visible shadow from the caster.

### Why is a constant bias imperfect?

Different surface slopes and scene conditions need different amounts of tolerance.

### Why are grazing surfaces more difficult?

Their light-space depth can vary rapidly across neighboring shadow-map samples.

### Does PCF solve acne?

No. PCF changes visibility filtering; the underlying depth comparisons can still
suffer bias errors.

---

## 14. One-sentence mental model

Remember:

> Bias is a tolerance added to an imperfect depth comparison; too little causes self-shadowing, too much detaches the shadow.

That sentence is enough to reconstruct most of the topic later.
