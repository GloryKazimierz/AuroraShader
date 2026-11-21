# Finite recent-view reflection: coverage evidence

This is an independent geometry study, not an installed shader feature. [Executable reference](offscreen_history_reference.py) uses exact3D ray/box intersections; [retained result](OFFSCREEN_COUNTEREXAMPLE_v2.json) passed. Version2 clarifies equality of **currently camera-visible geometry**, not all real-world indirect lighting.

A camera at(0,2,4) looks down24.5° then26°, with50° vertical FOV. The old target(2,2,−8) moves from previous UV.y0.98865 to current1.02297, while the reflecting water point remains visible at0.64240. A new0.2m box lies on the ray entirely outside the current view. The old target still matches current light-view depth, but the actual reflection hits the box at6.10431m before the target at6.40312m. **Endpoint validation alone accepts the wrong result.**

Exact light queries along the entire segment reject this new caster. These queries are stronger than a finite shadow texture. If the obstacle is absent from the caster set, even that oracle cannot distinguish it: previous samples, current camera-visible geometry and current shadow geometry do not observe it. Limiting a temporal contribution bounds its influence, not the truth of its visibility.

## Required conditions for a production experiment

- Distinguish a fully checked current screen exit from budget exhaustion, short projected rays, invalid data and unknown acceleration prefixes. Current `WATER_TRACE_UNRESOLVED` combines them.
- Reject known roof/intersection, transparent ownership veto, multiple water, missing old color/depth/share, stale allocation/frame, resize, dimension/FOV changes and camera cuts.
- Reproject the actual old3D point, match previous depth, and confirm it against current shadow geometry. Require coverage along the complete reused segment; outside-map data is unknown.
- Test a newly inserted offscreen intermediate obstacle, removed endpoint, moving noncaster, light/material change and cutouts. A valid endpoint never overrides an intermediate blocker.
- Keep any temporal fallback opt-in, one-frame and contribution-limited, with explicit static-caster coverage limits. A no-ghost guarantee requires hard rejection or more current visibility data.

Current `shadowEntities = false` means the shadow map is incomplete. Old radiance can also lag changed illumination/material for one frame. Large camera cuts must invalidate history.

## Resources and status

A quarter-width/height RGBA32F cache of previous matched RGB+raw depth costs nominally3.96MiB for both sides at1080p, before normals/classification. Logical16 would require a defined `MAX_COLOR_BUFFERS > 16` gate and an additional sampler;11 is planar proof and12 is reserved for the separate water-history filter.

No new binding, shader pass, setting, GPU result or performance measurement is implemented here. A raster history cache is not a full-world ray-tracing acceleration structure. Measure the limited newly-offscreen coverage before adding this cost.

Primary references: [Iris previous-frame matrices](https://shaders.properties/current/reference/uniforms/matrices/), [Iris color-buffer count and double buffering](https://shaders.properties/current/reference/buffers/colortex/). The geometry evidence comes from the local reference.
