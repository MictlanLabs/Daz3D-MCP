---
name: rendering
description: How to render Daz Studio scenes with the daz3d MCP tools - render settings, Iray limits, test renders, cameras and output files. Use when the user asks for a render, a final image, or better render quality or speed.
---

# Rendering in Daz Studio

Read `daz-basics` and `scene-building` first. Daz Studio renders with NVIDIA
Iray: physically based, progressive (the image gets cleaner over time) and
slow without an NVIDIA GPU. On a Mac Iray runs on the CPU only, so keep
renders small and short there unless the user asks otherwise.

## Before rendering

1. A scene camera exists and frames the subject: `camera_create(frame=[...])`.
   Do not render from "Perspective View".
2. There is light: scene lights (`light_create`) and/or the dome
   (`environment_set`). `environment_set()` without arguments reports the
   current environment; `mode="scene_only"` with no lights renders black.
3. A `viewport_capture(camera=...)` looks right: framing, poses, nothing
   clipping. A capture costs seconds; a render costs minutes.

## Test render, then final render

- **Test:** `render(camera, width=800, height=450, max_time=60)`. Look at the
  image: lighting, exposure, framing.
- **Final:** larger size and more time, for example `width=1920, height=1080,
  max_time=600` or `max_samples=2000`. Ask the user before a render that will
  take more than about 10 minutes.
- Iray stops at whichever limit comes first: `max_samples`, `max_time`
  (seconds), or the quality target (`quality`, 1 = default). Always set
  `max_time` so a render cannot run for hours.
- `render_settings` reads the current renderer, size and limits, and changes
  them for later renders. `render(width, height, ...)` changes them too.
- The aspect ratio comes from `width` and `height`. Set it before framing a
  camera: the framing depends on it.

## Output

- `render` waits until Iray is done, saves the image and returns a preview.
  Daz Studio is busy for that whole time.
- Without `out_path` images go to `~/.daz3d-mcp/renders/` with a time stamp.
  With `out_path` (absolute, `.png` or `.jpg`) an existing file is never
  replaced unless `overwrite=true`.
- Tell the user where the file is. Describe what the image really shows,
  including problems (noise, dark areas, clipping).

## Fixing common problems

- **Too dark:** raise light `power` (lumens), add a fill light, or raise the
  dome `intensity`. Bright is easier to judge than dark.
- **Noisy/grainy:** more `max_time` or `max_samples`; small lights and dark
  scenes need more.
- **Flat light:** move the key light to the side and above (45 degrees), lower
  the dome, add a rim light behind.
- **Subject cut off:** reframe with a bigger `margin` or another `yaw`/`pitch`.
- **Render takes too long:** smaller size, lower `max_time`, fewer lights, hide
  what the camera does not see (`node_set(visible=false)`).
- **The render failed:** check the folder exists and that Daz shows no dialog.
