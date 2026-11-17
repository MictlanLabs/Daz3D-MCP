# Changelog

> [Leer en español](CHANGELOG.es.md)

All notable changes to the `daz3d-mcp` Python package (MCP server, DazScript
library and skills). The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/) as described in
[Versioning](README.md#versioning).

The bridge plugin (`bridge/`) has its own version in `bridge/src/version.h`,
noted below when it changes.

## [Unreleased]

### Added

- `contact_bake`: a figure's own hand pressing a breast deforms it for real. Every frame it measures where the palm and each finger enter the flesh on the posed mesh, pushes the skin back to the hand's surface, bulges the flesh around it and adds spring inertia (lag, overshoot on release, settling), baked as one morph per frame.
- Contact dials for animation: `morph_generate` makes `bust_press_left` / `bust_press_right` ("MCP Bust Press Left/Right") on Genesis 9 and 8 / 8.1, a dent under a pressing palm with the flesh around it bulging out, to key in sync with a hand. They are not character traits, so character sheets do not use them.

## [1.1.0] - 2026-11-16

### Added

- Character sheets for building unique characters from a description and reusing them: `character_create` builds a character (base figure, body, height, every face detail, skin, eyes, hair, clothes) and saves it as an editable JSON sheet plus a Daz character preset (`.duf`); `character_load` puts it in any scene, or on a figure already there; `character_update` changes only what is asked (one trait, the hair, one piece of clothing) and keeps the rest; `character_list` lists the saved characters and the trait vocabulary.
- About 115 traits from -1 to 1 cover body build (height, weight, muscle, age, bust, belly, hips, thighs, arms, proportions) and every part of the face: face and skull shape, forehead, temples, brows, eyes, eyelids, epicanthic fold, lashes, irises, pupils, nose (bridge, hump, tip, nostrils, septum, crooked), cheeks, dimples, lips, philtrum, mouth, jaw (angle, shift, jowls, double chin), chin, ears (lobes, angle, pointed), teeth (size, length, taper, gap, crooked, bite, gums, fangs, tusks), wrinkles and natural asymmetry. Each time a sheet is applied the traits are mapped to the dials installed on the figure, so one sheet works on Genesis 9, 8.1 and 8; traits with no installed dial are reported, and near substitutes are marked as approximated. On Genesis 9 the paired left and right asymmetry dials shape lips, eye tilt, eyelids, cheeks, brows and face shape even without the morph packs.
- Sheets also keep heterochromia (one iris per eye), the color of the whites of the eyes, eyebrows and facial hair with their own colors (root and tip), teeth, gum, nail and lip colors, add-ons such as horns or a tail, and any other material change; `dials` reach the Genesis 9 Mouth and Eyes with `mouth:` and `eyes:`.
- `morph_generate` makes new shape dials for traits with no installed morph (20 dials on Genesis 9 and Genesis 8 / 8.1: nose width, size, length, bridge and tip, philtrum, temples, eye bags, cheekbones, chin length and projection, jaw width and definition, lip fullness, ear size and angle, age, weight, muscle and belly), built from the figure's own mesh, its face and body bone weights and points found on the face. It saves them as morph assets in a content library, so new figures load them, and projects them onto what the figure wears (clothing, hair, brows, lashes, eyes, mouth), linked so they follow. Character sheets find them by trait, and loading or updating a character makes newly worn items follow them.
- `morph_generate` also makes bust, breast shape, areola size and nipple projection dials. `morph_export` writes a figure's base mesh as OBJ for sculpting in Blender, and `morph_import` turns the sculpt into a dial: size and Y-up / Z-up axes are matched, it is saved in a content library and worn items follow it.
- Character sheets take anatomy geografts (`anatomy`, or `["auto"]` for the installed one matching the body), with their dials as `anatomy:<dial>`; `character_list(include_anatomy=...)` lists the installed ones and the result says when none is installed.
- `eye_color(sclera=...)` colors the whites of the eyes (red, black, yellow) and leaves the iris as it is.
- A `character-design` skill: when to ask and what to assume, an ordered checklist of every feature, a phrase-to-trait table for body, face, eyes, nose, mouth, jaw, ears and teeth, what works with only the starter content, how to make faces unique with few dials and keep a cast distinct, how to check the result in renders, skin, eye, hair and fantasy looks, and the differences between Genesis 9, 8.1 and 8.
- `characters_dir` setting for where sheets and presets are kept (default `~/.daz3d-mcp/characters`).

## [1.0.3] - 2026-11-16

### Fixed

- `render_settings(exposure=...)` and the tone mapper properties did nothing in a new scene, which has no Tonemapper Options node until the Render Settings pane or a render makes one; the node is now created when needed.
- `eyes_look_at` with `head > 0` added more head turn on every call; the head now takes the given share of the full turn, so repeating a call leaves it where it was.
- `face_expression("angry")` was barely visible on Genesis 8.1, which lacks the Brow Squeeze dial; it now uses the figure's own Angry expression dial, with the mouth held closer.
- `light_set(on=true)` set an Iray light's Illumination to "Diffuse Only" instead of "On".

### Changed

- The README (English and Spanish) shows the project logo, an architecture diagram and an examples section with renders made through the tools: facial expressions, lighting, dialogue shots and an animation GIF. The images live in `docs/images/` and are linked by absolute URLs so they also show on PyPI.

## [1.0.2] - 2026-11-16

### Fixed

- `install` and `doctor` find Claude Desktop's settings in `%LOCALAPPDATA%\Claude-Data\<folder>\claude_desktop_config.json`, where recent Windows builds (the Microsoft Store app) keep them, instead of `%APPDATA%\Claude`.

## [1.0.1] - 2026-11-16

### Fixed

- `setup` did not copy the plugin after Windows granted administrator rights when the Daz Studio plugins folder already existed (always, on a normal install).

## [1.0.0] - 2026-11-16

First public release: on PyPI (`uvx daz3d-mcp`) with the compiled bridge
plugin on the GitHub release.

### Changed

- `setup` asks Windows for administrator rights (a UAC prompt) when the Daz
  Studio plugins folder is protected, instead of failing. `--no-elevate` turns
  this off.
- `setup` stops with a clear message when Daz Studio is open and would keep
  the old plugin locked, and when the Daz Studio found is 4.24, which has no
  prebuilt plugin.
- The README (English and Spanish) is written for a first install: requirements,
  install, adding the server by hand to each client, updating, uninstalling and
  troubleshooting. Its links work on PyPI.
- The package says it runs on Windows only.

## [0.6.0] - 2026-11-16

### Added

- `wearable_refit` repairs any clothing from another Genesis generation, not
  only shoes. It reports `rig` (how much of the item hangs from bones the
  figure has) and `shape` (distance to the skin with and without each clone
  shape), with the problems `not_converted` and `other_shape`; `fix=true`
  rebuilds such a piece with Daz's Transfer Utility and the clone of its
  generation, then converts what was fitted to it (belts, zips, buttons).
  New `convert` argument.
- `wearable_refit(item=<figure>)` checks, or with `fix=true` repairs,
  everything a figure wears.
- `wearable_refit` reports `below_floor` for a sole under the floor, and
  `feet.*.heel_minus_toe_cm`.
- `daz_dialog` reports `more_dialogs` when Daz opens another dialog right after
  the stopped call finishes (Auto-Fit asks once for each piece of an outfit).

### Fixed

- Items of an outfit whose Auto-Fit dialog was never answered stayed with the
  other generation's bones and shape (a Genesis 9 overall on Genesis 8 kept
  its arms down and did not follow the pose). They are now found and rebuilt.
- Boots with a thick sole and no modeled insole were reported as
  `foot_floating`; an even gap is now a note.
- Camera framing assumed the 36 mm frame spans the picture's width; Daz Studio
  spreads it over the height. `render_cull` dropped things at the sides of a
  wide picture that were in view (a figure's eyelashes and gloves at the edge
  of a two shot), `camera_shot` framed 1.8 times wider than asked on 16:9
  pictures, and `camera_create(frame=...)` left extra room. Close-ups are now
  as tight as their shot names say, and `extreme_close_up` keeps the mouth in
  the picture.
- `wearable_refit` measured feet against an item fitted to another item; it
  now uses the figure that wears it.

## [0.5.1] - 2026-11-15

### Added

- `render_settings(exposure=...)` sets the Iray Exposure Value; the result
  reports `exposure` (EV, shutter speed, f-stop, ISO).
- `camera_shot(avoid_walls=true)`: walls and other props between the face and
  the camera are found by themselves (`wall`, `wall_cm`, `pulled_in_cm`).
- `package_inspect` and `package_install` report `requires`: products a package
  needs that are not installed.

### Fixed

- `light_create` made spot and point lights with Photometric Mode off, so Iray
  ignored their lumens. They are now made like Daz's Create menu makes them,
  and `light_set(power=...)` turns the mode on for an older light.
- Setting "Exposure Value" by script did not change the render: Iray uses the
  shutter speed, f-stop and ISO. The value is now turned into a shutter speed,
  and changing those three keeps Exposure Value in step.
- `import_mesh(room=true)` took the largest level surface for the floor, which
  in a building with a flat roof is the roof (the Wild West Saloon sank
  6.9 m). The floor is now the largest level surface with something over it
  and room to stand on it (of storeys about as big, the lowest), at the height
  most of it is at. The saloon now stands on its ground floor boards.
- `camera_shot` put the camera outside or behind the walls of a small room
  unless `max_distance` was given by hand. It now comes in front of the wall
  with a shorter lens that keeps the framing, and warns below 14 mm.
- `package_install` gave no warning when a package needs a base figure (e.g.
  Genesis 8.1 Female), the product a morph pack is for, or a body morph pack
  its presets dial (e.g. Vlad Gens, Breastacular).
- `package_inspect` could fail on Windows on packages with a nested .zip,
  while removing its temporary folder.

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

[Unreleased]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/MictlanLabs/Daz3D-MCP/releases/tag/v1.0.0
[0.6.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MictlanLabs/Daz3D-MCP/releases/tag/v0.1.0
