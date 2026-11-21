# Looking through a moving water surface

[中文](WATER_M3_REFRACTION.zh-CN.md)

Open **Water → Water Optical Transport**, enable it, then choose **Water Refraction**. At the default Off setting, transport uses the original pixel. The experimental options trace a single 64- or 128-step ray, or up to three 128-step rays for RGB dispersion.

**Measured cost.** A 1280×720 full-water, two-metre checker pool on Intel Iris Xe took 2.31 ms for the composite with refraction off and 339.58 ms for the original 64-step ray. At 640×360 the RGB mode took 211.75 ms. These are isolated GPU draws on a frozen development snapshot with the same refraction algorithm. The reference modes are for visual comparisons on this hardware. The 720p 128-step batch was cancelled before a measurement. [Raw timings and comparison errors](validation/WATER_M3_REFRACTION_cost.json)

In the [three-angle comparison](validation/WATER_M3_REFRACTION_views.png), follow the checkerboard along the pool edge. The change in apparent scale is visible from above and stronger at an oblique angle. Near the horizon only a narrow part of the frame has a confidently visible bottom. The scene uses synthetic geometry, the pack's water capture, composite and final display path.

Light bends toward the surface normal when entering water from air. The trace searches for the receiver along that direction. At the hit it samples the receiver's own radiance and direct-light fraction. The bent path supplies the extinction distance on the return trip. RGB mode evaluates representative 650, 550 and 450 nm refractive indices for liquid water at 20 °C using the IAPWS relation. [IAPWS refractive index release](https://iapws.org/documents/release/Rindex)

The visible water surface must have a single owner with matching final depth. The receiver neighborhood must be consistent, below the local surface, and in the same pool within a 4 cm height tolerance. An unobserved endpoint, a foreground layer, a discontinuity or an exhausted search blends back to same-ray transport. Hidden geometry, curved receivers, different-height pools and the submerged-camera interface have limited coverage. This stage allocates no extra color targets.

The [native GPU report](validation/WATER_M3_REFRACTION_GPU.json) records analytic Snell and extinction checks, isolated changes at the target, exact fallback, alpha and the three views. Run `python -B tools/validate_gpu.py --suite water-refraction` to repeat the optical checks, with `--debug-plate docs/validation/NEW_REFRACTION.png` to include the image. Ray steps and neighbor tests make the RGB mode a demanding experimental configuration.

The [full native rendering regression](validation/WATER_M1_full_render.json) also passed against the frozen M1 shader tree at `7c32ba6`, using the collision-free fixture names from `9fd2fa3`. It covers baseline bloom, waves, foliage, celestial glow, screen reflections, debug and optical transport.
