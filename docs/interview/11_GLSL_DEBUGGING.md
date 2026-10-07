# Chapter 11: GLSL and Graphics Debugging

## 1. Debug the pipeline, not just the final image

A black screen is not a diagnosis.

Rendering failures can originate from:

- CPU resource setup;
- shader compile/link;
- vertex transforms;
- missing attributes/uniforms;
- framebuffer configuration;
- depth/culling state;
- texture bindings;
- coordinate-space mistakes;
- NaN/Inf;
- incorrect pass ordering.

Debugging should isolate stages.

## 2. Start from a known baseline

When adding a feature:

1. confirm the previous milestone works;
2. add the smallest change;
3. expose a debug visualization;
4. validate one assumption at a time.

AuroraShader's milestone approach is a strong example.

## 3. Shader compile/link errors

Always check logs.

Common issues:

- syntax;
- version mismatch;
- type mismatch;
- missing varying;
- preprocessor branch;
- unsupported extension;
- uniform/sampler mismatch.

Do not debug runtime visuals until compile/link health is known.

## 4. Use debug colors

Replace complicated output with explicit diagnostic color.

Examples:

```text
red   = branch A
green = branch B
blue  = branch C
```

Or visualize vectors:

```text
normal * 0.5 + 0.5
```

Debug views are often faster than reading code repeatedly.

## 5. Validate coordinate spaces visually

For normals:

- different faces should show different colors;
- camera rotation should produce the expected space-dependent behavior.

For shadows:

- visibility should remain attached to world geometry;
- camera motion should not drag shadows incorrectly.

Visual behavior can identify the class of transform bug.

## 6. Binary search the pipeline

If final output is wrong, simplify:

```text
final output
-> raw buffer
-> earlier buffer
-> geometry output
-> constant color
```

Find the first stage where data becomes incorrect.

This is more reliable than modifying many formulas at once.

## 7. NaN and infinity

Invalid math can spread quickly.

Common sources:

- normalize zero vector;
- divide by zero;
- sqrt negative;
- log nonpositive;
- invalid homogeneous divide.

Use guards such as safe normalization and validity flags.

AuroraShader's `safeNormal` is an example.

## 8. Texture debugging

When a sampled texture looks wrong, verify:

- correct binding;
- expected dimensions;
- format;
- coordinate range;
- wrap mode;
- filter;
- mip level;
- color-space decoding.

For shadow maps, visualize raw depth directly.

## 9. Framebuffer debugging

Verify:

- attachment exists;
- format is correct;
- size matches;
- clear values make sense;
- draw buffers/MRT locations match shader outputs;
- blending is disabled for metadata buffers when required.

AuroraShader explicitly disables blending for G-buffer metadata.

## 10. State bugs

Classic OpenGL bugs are often stale state:

- wrong VAO;
- wrong program;
- wrong texture unit;
- depth test disabled;
- culling wrong;
- blending wrong;
- viewport wrong.

Explicit APIs reduce hidden mutable state but introduce their own descriptor,
layout and synchronization mistakes.

## 11. Graphics debuggers

RenderDoc can inspect:

- draw-call sequence;
- pipeline state;
- attachments;
- textures;
- mesh input/output;
- shader resources;
- pixel history.

Learning a frame debugger is one of the highest-value practical graphics skills.

## 12. Regression testing

A renderer feature can silently break an old feature.

Keep:

- fixed scenes;
- debug views;
- validation scripts;
- screenshots;
- benchmark configurations.

AuroraShader's milestone acceptance checklists are a form of regression discipline.

## 13. Common interview questions

### How would you debug a black screen?

Check compile/link/logs, framebuffer and viewport, then simplify to a constant output
and trace geometry/transforms/resources stage by stage.

### How debug a coordinate-space bug?

Visualize intermediate vectors/positions, verify each transform contract, and test
behavior under controlled camera/object motion.

### Why visualize G-buffer channels?

It exposes whether stored intermediate data is already wrong before lighting uses it.

### Why can NaN be dangerous?

It propagates through arithmetic and can produce undefined/unexpected shader output.

## 14. AuroraShader connection

Your debug modes are not just convenience features. They demonstrate good graphics
engineering:

- normals;
- light levels;
- NdotL;
- raw shadow depth;
- shadow visibility.

Each isolates a different stage of the pipeline.
