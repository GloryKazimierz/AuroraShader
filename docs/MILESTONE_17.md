# Milestone 17: Grouped settings, Chinese labels and profiles

Date: 2026-11-13. Branch: `codex/milestone-17-settings-profiles`.
Base: M16 commit `581ffa86d0800b70cdab2d486a65606b2bc9e160`.
[中文使用与学习版](MILESTONE_17.zh-CN.md).

M17 makes existing features easier to find and configure. It adds complete Simplified
Chinese labels and three limited-scope profiles. GLSL source and shader defaults are
unchanged. Menu appearance and profile interaction in Minecraft remain unobserved;
executed validation results belong in a separate record.

## 1. Use the first-screen profile selector

Open AuroraShader's **Shader Pack Settings**, choose a profile on the first screen,
then apply the pending settings through Iris. Adjust individual controls in the
groups below. Selecting a profile changes only its six controls; the other 45 options,
including color, fog, exposure, debug and scene pipeline, retain their current values.

To use Chinese labels, select Simplified Chinese in Minecraft's language settings
and reopen the shader settings. `shaders/lang/zh_cn.lang` contains the same 159 keys
as `en_us.lang`, saved as UTF-8. Iris reads shader language files using UTF-8.
[Language loader](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/shaderpack/LanguageMap.java).

| Group | Controls to look for |
|---|---|
| Aurora Sky and Light | Sky palette and blend, sunlight/ambient colors, directional-light factors |
| Shadows | Enable, Hard/PCF/Poisson, softness and bias |
| Water Color and Sky Reflection | Water style/tint/reflection, normal waves and depth color |
| Cloud Color and Atmosphere | Native cloud style, tint and fog |
| Aurora Night Ribbons | Night aurora enable, intensity and motion |
| Controlled Bloom | Enable, strength, threshold and soft transition |
| Distance and Height Fog | Enable, density, clear distance, reference height, falloff and rain |
| Color Grading | Exposure, saturation, contrast, warm/cool tendency, tint and grayscale |
| Advanced and Debug | Debug view; nested Scene Color and Highlights for pipeline/tone mapping |

All 51 options are explicitly placed once. Exposure now belongs only to Color Grading;
scene storage/tone mapping remains under Advanced. No option is removed or renamed.
Submenus and the profile selector use Iris's existing settings syntax.
[Settings syntax](https://shaders.properties/current/reference/shadersproperties/shader_settings/).

## 2. Exactly six profile-controlled settings

| Setting | Light / 轻量 | Balanced / 均衡（默认） | Soft Shadows / 柔和阴影 |
|---|---|---|---|
| `SHADOWS_ENABLED` | On | On | On |
| `SHADOW_FILTER` | 0: Hard | 1: 3x3 PCF | 2: 5x5 PCF |
| `BLOOM_ENABLED` | 0 | 1 | 1 |
| `AURORA_ENABLED` | 0 | 1 | 1 |
| `WATER_WAVES` | 0 | 1 | 1 |
| `WATER_DEPTH_TINT` | 0 | 1 | 1 |

Balanced matches the existing source defaults for these six values. Light inherits
Balanced, then changes filtering and the four optional effects. Soft Shadows inherits
Balanced and changes only filtering. Profile inheritance is ordinary Iris behavior.
[Profile parser](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/shaderpack/option/ProfileSet.java).

“Default” does not mean a full settings reset. Adding these profiles does not automatically
apply Balanced or replace an existing saved configuration. Selecting Balanced restores
these six values while retaining artistic choices, including saved zero strengths.

## 3. How the profile label follows manual edits

Iris compares only the values listed in each profile. A manual edit can match another
profile, or show **Custom** if none matches. Editing an option outside the six does not
force Custom.
[Matching logic](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/shaderpack/option/Profile.java).

| Starting from Balanced, change… | Matching label |
|---|---|
| Exposure or fog density | Balanced |
| Only filtering to 5x5 PCF | Soft Shadows |
| Only bloom to Off | Custom |
| Shadows to Off | Custom; every named profile enables shadows |

A matching label describes settings, not visible output. Legacy scene mode, debug views,
environment gates, zero effect strengths or a disabled parent style can independently
suppress an enabled feature. For example, Balanced does not turn Aurora Sky back on
if that separate option was previously disabled.

The shared selector tooltip uses `profile.comment`; profile names use
`profile.BALANCED`, `profile.LIGHT` and `profile.SOFT_SHADOWS`.
Per-profile `profile.NAME.comment` entries are not used by this widget.
[Profile widget](https://github.com/IrisShaders/Iris/blob/99d855970316329f2e0e42ac2b79ef763cb77cc3/common/src/main/java/net/irisshaders/iris/gui/element/widget/ProfileElementWidget.java).

## 4. What the names say about cost

For an active in-range receiver at nonzero softness, Hard, 3x3 and 5x5 use 1, 9 and
25 shadow-depth comparisons respectively. Zero softness follows the existing Hard
shortcut. All three profiles keep the 2048 shadow map and 64-block caster-distance
setting; Light does not eliminate shadow-map rendering.

Bloom Off bypasses its visual contribution but retains the four fullscreen passes and
half-resolution scratch buffers. Turning off aurora, wave normals and depth color skips
their optional shader work when those paths would otherwise be active. These changes
do not establish an FPS improvement or a tested hardware tier. No timings are claimed.

Profiles retain native water alpha and composition; “depth color” remains a vertical
background-gap heuristic, not absorption. Color temperature remains an artistic
warm/cool control, not a physical Kelvin setting. These meanings are preserved in
the Chinese tooltips.

## 5. Files and evidence boundary

`shaders.properties` defines the groups and profiles; `en_us.lang` adds group/profile
labels; new `zh_cn.lang` translates every English key. No new rendering pass, buffer,
sampler, option or GLSL formula is introduced. Existing language/option identifiers
remain stable.

The linked Iris implementation is pinned to
`99d855970316329f2e0e42ac2b79ef763cb77cc3`; the currently installed Iris version has not
been freshly verified. Native-driver compilation can check profile-selected shader
variants, but cannot prove that the actual Iris menu renders or applies them correctly.

| Runtime observation | Actual result |
|---|---|
| English/Chinese labels, glyphs and tooltip wrapping fit the menu | |
| All groups and the nested scene-color page are reachable | |
| Each profile changes only its six fields after applying | |
| Artistic edits retain a matching label; unmatched controlled edits show Custom | |
| Existing saved options survive adding the new profiles | |
| Light/Balanced/Soft Shadows compare as described in a fixed scene | |

## 6. Four useful distinctions

1. **Profile versus reset:** a profile applies a defined subset, not the entire configuration.
2. **Label versus appearance:** matching option values does not override feature gates.
3. **Feature Off versus zero cost:** allocated passes/buffers can remain after a visual bypass.
4. **Translation parity versus UI testing:** equal keys avoid omissions, but layout still needs observation.

## 7. Executed checks

The focused settings validator passed: **93 preserved files**, all **51 controls
exactly once across 11 screens** (including root/nested pages), three six-key profiles,
159 matching language keys, and all 152 pre-existing English values preserved.
The full historical CPU/structural validator and whitespace/syntax checks also passed.
Language reads are explicitly UTF-8 so the Chinese file is decoded correctly.

All **72 program/profile combinations** (24 program pairs across three profiles)
passed both offline GLSL and native driver compilation/linking.
The [native profile report](validation/M17_GPU_profiles.json) records the resolved
profile maps, Intel Iris Xe / OpenGL 3.3 compatibility / driver 31.0.101.3962,
and an unchanged shader-tree digest before successful completion.
These are compile and structure results, not Iris menu, Minecraft visual or FPS tests;
the runtime observation table remains blank.

Next work remains the bounded water-transparency design and broader integrated validation.
Related notes: [M15 validation layers](MILESTONE_15.md), [M16 depth color](MILESTONE_16.md),
[roadmap](AURORA_ROADMAP.md).
