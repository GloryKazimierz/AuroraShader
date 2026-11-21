# Finite near-clip waterline: frozen CPU reference

This snapshot is a geometry prototype, not a Minecraft rendering result or installed color change. It uses existing compact RGBA16 water-shadow records, matching D24 front depth, and separate opaque light depth. Real finite water/bed rectangles, roof and glass boxes generate those inputs by independent world-ray intersections.

An initial2×2 patch locates a near-horizontal top plane. Re-sampled2×2 patches around the camera and each near-plane point must agree; barycentric line clipping proves that the eye→near projection stays inside their finite triangle union. The initial plane only locates observations: it does not justify extrapolating a water surface beyond the verified patches. At most three unique2×2 queries, including the initial lookup, are used here.

The geometric normal comes from reconstructed depth. Filtered wave normals identify the optical surface but do not change its position. Each perspective ray shares the eye; each pixel has a different near-plane point. Signed distances classify that point and integrate the actual water portion of the eye→near segment.

Conditions: current water record/depth agreement; front water strictly before finite opaque depth; top-plane upward normal≥.995; four water heights within4mm; planar residual≤2mm; edge footprint≤.5m; continuous bed heights within25mm; water-bed separation≥8cm; camera within5cm of the sampled top; near point more than0.1mm from the ambiguous boundary; no native transparent ownership veto. Any missing condition returns UNKNOWN and must keep native color.

The finite footprint is sampled evidence. A tiny hole invisible to every shadow sample cannot be identified by these inputs. This prototype therefore does not establish a general enclosed water volume or a no-aliasing guarantee. Native optical integration must keep this limitation explicit.

## Observed result

[CPU report](NEARCLIP_CPU.json):15 light/eye-height cases,34,560 pixel queries;26,640 accepted with exact medium classification,5,624 actual clipped crossings. Maximum water-segment error is0.1075mm. The0.25mm test budget corresponds to less than1e−4 relative Beer attenuation error at the current largest configured extinction0.384/m. This is a numerical tolerance, not a claim of physical millimeter accuracy in Minecraft.

All11 negative controls return UNKNOWN: missing record, depth mismatch, opaque-only/bottom, native overlay, roof, glass, close bed, shore, water-height step, bed step and low light.

The classification image has three light rows and eye-height columns−4cm,−1cm,0,+1cm,+4cm. Gold=air; blue=water; gray=UNKNOWN. About23% of queries fall back because two endpoint patches do not cover an intermediate crossed cell. A future bounded grid traversal may add actual intermediate patches; it must not fill the gap by extending a plane.

![CPU finite near-plane classification; not game imagery](NEARCLIP_classification.png)

Run `python -B nearclip_reference.py` after copying only the script to an empty D: directory; retained reports refuse overwrite. The original failed single-patch design was replaced because a5cm near segment often leaves that one patch; this is why explicit finite coverage matters.
