---
name: daz-basics
description: Core knowledge for controlling Daz Studio through the daz3d MCP server. Use whenever a task involves Daz Studio, Daz 3D scenes (.duf), Genesis figures, or the daz3d tools (scene_info, viewport_capture, run_script).
---

# Daz Studio basics

You control a running Daz Studio through the `daz3d` MCP tools. Daz Studio is a
3D scene editor built around rigged human figures (Genesis 8, 8.1 and 9), with
clothing, hair, props, cameras and lights. Rendering uses NVIDIA Iray.

## First steps in every session

1. `daz_status` to confirm Daz Studio answers and see its version and the open scene.
2. `scene_info` to learn what is in the scene before changing anything.
3. `viewport_capture` to look at it. Check your work with a new capture after
   each visible change; describe what you see, not what you expect.

If `daz_status` fails, tell the user to open Daz Studio and run
`uvx daz3d-mcp doctor`. Do not retry in a loop.

## Safety rules

- Never throw away the user's work. `scene_new` and `scene_open` refuse when
  the scene has unsaved changes; ask the user whether to save first
  (`scene_save`) before passing `discard_changes=true`.
- `scene_save` without a path overwrites the current file. Saving to a new
  path is safer when you are unsure; it never overwrites another file unless
  you pass `overwrite=true`.
- Paths are absolute. On Windows `C:\Users\Ana\scene.duf` and
  `C:/Users/Ana/scene.duf` both work.
- One request runs at a time. Opening a heavy scene can take minutes and Daz
  Studio is frozen meanwhile; wait for the answer instead of sending more calls.
- Daz may show a dialog (missing files, licences). If a call times out, ask the
  user to look at the Daz Studio window.

## How a scene is organized

- **Units:** centimeters. A Genesis 9 adult is about 170-185 cm tall.
- **Axes:** Y is up, the figure faces +Z by default, X is the figure's left.
  The floor is the plane Y = 0.
- **Nodes** form a tree. `scene_info` reports each node's `label` (the name the
  user sees in the Scene pane), internal `name`, `type`, `parent`, world
  position, local rotation in degrees and bounding box. Use labels when you talk
  to the user and when tools ask for a node.
- **Node types** reported by `scene_info`:
  - `figure`: a rigged figure such as a Genesis 9 character. Its bones are
    hidden unless you ask for `include_bones=true`.
  - `fitted_figure`: clothing or hair fitted to a figure; `fitted_to` tells
    which. It follows the figure's pose automatically.
  - `prop`: rigid geometry (furniture, buildings, environment pieces).
  - `camera`, `light`, `group`, `node` (null or empty node).
- **Timeline:** `frames.start`, `frames.end` and `frames.current`. A still
  scene usually has start = end = 0.

## Describing a scene to the user

Combine `scene_info` with a capture:

- Count the main things: figures (and what they wear), props, lights, cameras.
- Give rough sizes and placement from the bounding boxes ("a 180 cm figure
  standing at the center, a sofa 2 m behind her").
- Mention what the capture shows that the data does not: pose, framing,
  lighting mood, whether something clips through something else.
- Say which camera the capture used. The viewport camera ("Perspective View")
  is not a scene camera and is not used for final renders.

## Files and content

- `.duf` is the native Daz format for scenes and for every content preset
  (figures, clothing, poses, materials). `.dsf` files are the data they point to.
- Content lives in content libraries ("My Library", "My DAZ 3D Library") with
  folders such as `People/Genesis 9`, `Environments`, `Props`, `Light Presets`.
  Opening a scene that references content the user does not own shows a
  missing-files dialog.
- Saving with `scene_save` writes a scene `.duf`; it does not copy the assets.

## More guides

- `scene-building`: find content, place figures and props, cameras and lights.
- `characters`: figures, character presets, shape dials, clothing, hair, poses.
- `rendering`: Iray settings, test and final renders.
- `third-party-assets`: .zip packages from other stores, OBJ/FBX import, imported garments as clothing.

Agents without skills support read them with `daz_guide(topic)`.

## run_script: when the named tools are not enough

`run_script` runs DazScript, Daz Studio's JavaScript dialect, inside Daz. The
code is the body of a function: read `args`, `return` a JSON-friendly value,
and use `DazMcp.log("...")` for messages.

```js
// Rename the selected node and report its new label.
var node = Scene.getPrimarySelection();
if (!node) { throw DazMcp.fail("bad_args", "Nothing is selected."); }
node.setLabel(args.label);
return { label: node.getLabel() };
```

Rules that avoid most errors:

- Write plain ES5: `var`, `function`, no `let`/`const`, arrow functions,
  template strings or classes. It runs on both Daz Studio 4.x (Qt Script) and
  Daz Studio 6.
- Global objects: `Scene` (the scene), `App`, `MainWindow`, and `DazMcp`
  (helpers: `DazMcp.findNode(label)`, `DazMcp.vec(v)`, `DazMcp.nodeType(node)`,
  `DazMcp.fail(code, message)`).
- Return data, not Daz objects: convert vectors with `DazMcp.vec(v)` and nodes
  with `{ label: n.getLabel() }`.
- Transform properties are on the node: `node.getXPosControl()`,
  `getYRotControl()`, `getScaleControl()`; call `.setValue(x)` on them. Values
  are in centimeters and degrees.
- Never open dialogs (`MessageBox`, file pickers): nobody is there to click.
- Keep each script small and check the result with `scene_info` or a capture.
- Prefer the named tools whenever one exists; `run_script` may be disabled by
  the user (`allow_run_script` in `~/.daz3d-mcp/settings.json`).

API reference: https://docs.daz3d.com/public/software/dazstudio/4/referenceguide/scripting/api_reference/start

## Daz Studio 4.x and 6

Daz Studio 6 moved to Qt 6 and a newer JavaScript engine. The tools work on
both. Differences you may meet in `run_script`:

- Daz Studio 6 accepts modern JavaScript, 4.x does not; stay with ES5.
- `include()` is deprecated in Daz Studio 6; do not use it.
- On macOS, Daz Studio 6 draws the viewport with Metal. If a capture comes back
  as a small thumbnail (`method: saveThumbnailImage`), that is the fallback
  path; it is still a faithful preview of the scene.
