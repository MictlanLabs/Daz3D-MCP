# Changelog

> [Leer en español](CHANGELOG.es.md)

All notable changes to the `daz3d-mcp` Python package (MCP server, DazScript
library and skills). The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/) as described in
[Versioning](README.md#versioning).

The bridge plugin (`bridge/`) has its own version in `bridge/src/version.h`,
noted below when it changes.

## [Unreleased]

## [0.5.0] - 2026-11-15

### Added

- Furniture poses: `prop_surfaces` measures where a chair, sofa or bed can be
  sat or lain on, `place_on` puts a posed figure on it and `fit_check` reports
  body parts that float or pass through it; joint limits and landmarks in
  `figure_info`. New `furniture-poses` skill.
- Faces: `face_expression` (named expressions), `eyes_look_at` and `eye_color`.
  New `faces` skill.
- Dialogue scenes: `camera_shot` frames close-ups, over-the-shoulder and two
  shots that respect the 180-degree rule, and `render_shots` renders a
  conversation one image per line. New `dialogue-scenes` skill.
- Daz Studio dialogs: `daz_dialog` reads and answers pop-up dialogs that stop a
  call (`dialog_open`), with preset rules and overwrite prompts handled; the
  call resumes once the dialog is answered.
- `render_animation`: renders timeline frames with Iray, resumes partial runs
  and encodes MP4 or GIF with ffmpeg; `render` can render a single frame.
- `render_cull` leaves out of the render what the camera cannot see (out of the
  picture, behind it, clothing under other clothing) while keeping what lights
  the scene; `render`, `render_shots` and `render_animation` take `cull=true`.
  New `render-culling` skill.
- `wearable_refit` checks and repairs clothing and shoes fitted from another
  Genesis generation (G8/G8.1 on G9 and the reverse). New
  `cross-generation-clothing` skill.
- This changelog; the package version now lives only in `pyproject.toml`.

### Fixed

- Tools tested against a real Daz Studio 6 for the first time.
- Animation retargeting from Daz-exported FBX (rotation order, clamped dials,
  FBX transforms and placement).
- Windows plugin loading on Daz Studio 6.
- `mesh_inspect` and `import_mesh` with Blender FBX scenery: sizes are read as
  Daz will import them (`bbox_cm`), a `suggested_scale` is given when the size
  is not believable, camera, light and empty nodes are left out, and
  see-through surfaces become Iray glass.
- `eyes_look_at` aims better near the eye joint limits; `content_load` handles
  deferred Daz dialogs before returning.
- `render_animation` no longer hangs when ffmpeg waits for console input.

### Changed

- README: marked as early-stage, Windows only, and documented that Iray needs an
  NVIDIA GPU.
- Bridge plugin 0.2.0 (dialog handling). Rebuild it to use `daz_dialog`.

## [0.4.0] - 2026-11-10

### Added

- Animation: keyframes (`anim_keys_set`, `anim_keys_get`, `anim_keys_delete`,
  `anim_key_pose`), timeline, built-in and saved presets, Mixamo FBX and BVH
  import onto Genesis figures, retiming, offsets, foot contact and previews.
  New `animation` skill.

## [0.3.0] - 2026-11-10

### Added

- Third-party assets: `package_inspect`, `package_install`, `package_list`,
  `package_uninstall`, `mesh_inspect`, `import_mesh`, `wearable_from_mesh` and
  `wearable_adjust`. New `third-party-assets` skill.

## [0.2.0] - 2026-11-10

### Added

- Characters (figures, morphs, clothing with `wearable_fit`, hair, poses,
  bones) and Iray rendering tools. New `characters` and `rendering` skills.

## [0.1.0] - 2026-11-10

### Added

- First MCP server, bridge plugin, scene tools, `setup`, `install` and `doctor`
  commands.

[Unreleased]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MictlanLabs/Daz3D-MCP/releases/tag/v0.1.0
