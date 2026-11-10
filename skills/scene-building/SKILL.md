---
name: scene-building
description: How to build a Daz Studio scene with the daz3d MCP tools - find installed content, load figures and props, place them, add cameras and lights. Use when the user asks to create, set up, compose or change a Daz scene.
---

# Building scenes in Daz Studio

Read `daz-basics` first. Units are centimeters, Y is up, figures face +Z, the
floor is Y = 0. Work in small steps and look at the result with
`viewport_capture` after each visible change.

## The order that works

1. **Start clean, safely.** `scene_info`. If the scene has content and unsaved
   changes, ask the user before `scene_new(discard_changes=true)`, or build on
   top of what is there.
2. **Find content.** `content_search` searches the user's installed libraries.
   Only use what it returns; never guess paths or assume a product is installed.
3. **Add figures and props** with `content_load(path)` (no target).
4. **Name and place them.** `node_set(node, label=..., position=..., rotation=...)`.
5. **Dress and pose** each figure (see the `characters` skill).
6. **Frame** with `camera_create(frame=[...])`, **light** with `light_create`
   and `environment_set`.
7. **Check** with `figure_info`, `scene_info` and a capture, then **render**
   (see the `rendering` skill) and **save** with `scene_save` to a new path.

## Finding content

`content_search(query, kind, generation, folder)`:

- `query`: words that must all appear in the file path ("jeans", "office chair",
  "walk"). Short queries find more. Empty with a `kind` lists everything of that kind.
- `kind`: `figure`, `character`, `clothing`, `hair`, `pose`, `material`, `shape`,
  `prop`, `light`, `scene`, `scene_subset`, `render_preset`, `environment`,
  `properties`, `preset`, `other`.
- `generation`: `"Genesis 9"`, `"Genesis 8.1"`, `"Genesis 8"`, `"Genesis 3"`.
  Use it for clothing, hair and poses: they are made for one generation.
  `figure_info` tells you a figure's generation. Content whose folder does not
  name a generation is left out when you filter, so search again without it
  if nothing comes back.
- `folder`: limit to a library folder, e.g. `People/Genesis 9/Poses`.
- Results come in pages (`limit`, `offset`, `more`, `next_offset`).
- `content_thumbnail(path)` shows a result's picture. Use it to choose a
  style or when names are not clear.
- After the user installs new content, pass `refresh_index=true` once.

Typical library folders: `People/Genesis 9` (base figure, `Characters`,
`Clothing`, `Hair`, `Poses`, `Materials`), `Props`, `Environments`,
`Light Presets`, `Camera Presets`, `Render Presets`.

Whole scenes (`kind: scene`) are opened with `scene_open` (`merge=true` adds
them), not `content_load`.

## Placing things

- `node_set(position=[x, y, z])` is relative to the parent; for figures and
  props at the top of the scene that is world space.
- `rotation=[0, 180, 0]` turns a figure to face -Z. Two figures facing each
  other at x = -60 and x = 60: rotations `[0, 90, 0]` and `[0, -90, 0]`.
  Slightly toward the camera instead: `[0, 25, 0]` and `[0, -25, 0]`.
- Leave about 60 to 120 cm between two standing people talking; 30 to 40 cm
  between hips when they stand side by side for a photo.
- `relative=true` nudges from the current values. `drop_to_floor=true` puts
  the lowest point on Y = 0 (useful after scaling a prop).
- `label=` renames a node. Give figures clear names ("Ana", "Leo") right after
  loading; a second Genesis 9 arrives as "Genesis 9 (2)".
- `node_delete` removes nodes, and the clothing fitted to a figure with it.
- Props like chairs: a seated figure needs a sitting pose and its hip placed
  over the seat; check from the side with `camera_set(yaw=90)` and a capture.

## Cameras

- `camera_create(label, frame=["Ana", "Leo"])` places and aims a camera that
  fits those nodes (and what they wear) in the picture, and makes it active.
  `yaw` turns around them (0 = in front, 90 = from their left side),
  `pitch` raises it (5 degrees by default), `margin` adds room (1.1 = 10 %).
- Or give `position` and `look_at` (a label or `[x, y, z]`).
- Focal length: 35 mm wide/environment, 50 mm natural, 65 mm default,
  85 to 135 mm portraits. Longer lenses need the camera farther away;
  `frame` handles it.
- Eye level for adults is about Y = 150 to 165.
- The framing uses the render's aspect ratio: call `render_settings(width,
  height)` before framing if you change it.
- "Perspective View" is the viewport's own camera, not a scene camera; renders
  should use a real one.

## Lights

- `light_create(type="spot", position, look_at, power, color)` adds a light.
  Spot and point lights use lumens (Iray default 1500). A key light 2.5 m away
  usually needs 3000 to 8000 lm.
- Classic three-point lighting for people: key 45 degrees to one side and
  above, fill on the other side at a third to half the key's power, rim
  behind them pointing at their shoulders.
- `type="distant"` is a sun: only its `rotation` matters, e.g. `[-40, 30, 0]`.
- `environment_set` controls the dome: `mode="dome_and_scene"` (default, soft
  sky light plus scene lights), `"scene_only"` for studio looks with only your
  lights, `hdri=` for an image-based environment, `draw_dome=false` to hide it
  from the background.
- A light preset from `content_search(kind="light")` loads with `content_load`.
