---
name: render-culling
description: How to make Daz Studio renders lighter with the daz3d MCP tools by leaving out what the camera cannot see - things out of the picture or behind the camera, clothing hidden under other clothing, the far parts of a big set - and when hiding is not safe (shadows, light through windows, reflections). Use when renders are slow, run out of memory or hang, when rendering on a CPU or a small GPU, or for many shots and animation loops of one scene.
---

# Leaving out what the camera cannot see

Read `rendering` first. Iray loads every visible node of the scene, with all
its geometry and textures, even what the camera never sees: the shoes of a
character framed from the knees up, the underwear under a long skirt, the
hundred trees of a park behind the camera. On a CPU that costs time; on a GPU
it costs memory, and a scene that does not fit falls back to the CPU or stops.

`render_cull` finds those nodes for one camera and switches off their
**Visible in Render**. The viewport, the node's Visible eye and the saved file
do not change, and `restore` puts everything back.

## The quick way: cull=true on the render

```
render(camera="Shot", cull=true, max_time=60)
render_shots(beats=[...], cull=true, ...)        # per beat, for that beat's camera
render_animation(camera="Cam A", cull=true, ...) # what any frame sees is kept
```

Each render hides what its camera does not see, renders, and puts it all back,
even when the render fails. The result has a `cull` entry: what was hidden, the
share of facets saved, the texture files no longer needed, and warnings. Use
this by default for final renders of big scenes and for every render on a CPU.

## Looking first: render_cull

- `render_cull(camera)` (action `check`) only reports: `would_hide`, `kept`
  with the reason, `counts`, `savings` and `warnings`. `detail=true` lists every
  node with its status. Run it once on a new set or camera and read it.
- `render_cull(camera, action="hide")` hides them and records what it hid in
  `~/.daz3d-mcp/cull-active.json`. A second hide (another camera) first puts
  back the first one. Renders then run without them until
  `render_cull(action="restore")`.
- `scene_save` puts hidden nodes back for the save and hides them again after,
  so a saved scene never keeps them switched off. Opening or clearing a scene
  forgets the record.
- For an animation pass `start_frame`/`end_frame` (and `samples`, default 12
  frames spread over the range): a node seen at any of them stays.

## What it leaves out

| status | what | example |
|---|---|---|
| `out_of_frame` | its bounding box is outside the picture or behind the camera | shoes in a knees-up shot, trees behind the camera |
| `covered` | a worn item hidden under other opaque clothing of the same figure | underwear under a long skirt, a shirt under a closed coat |
| (shell) | a geometry shell (toon outline) of a dropped node | `G9 Shoes Toon Outline` |

The covered test draws the figure's clothes into a small depth buffer
(`resolution`, default 400 px wide) and drops an item only when it sits at
least `depth_margin` (0.3 cm) behind other clothing everywhere it is in the
picture. See-through surfaces (Cutout Opacity below 1 or with a map: lace, mesh
fabric, hair cards; glass) cover nothing, so what shows through them stays.
Strand hair cannot be tested and always stays. `occlusion="none"` turns the
covered test off.

## What it keeps on purpose, and why

Things off screen still change the picture. A node is kept (`kept`, with its
reason) when:

- `around_camera`: its box contains the camera, like the room the camera
  stands in. Hiding it would open the room to the sky.
- `holds_light_in`: a wall, floor or ceiling (2 m or more in two directions)
  within 10 m. The wall behind the camera keeps the dome light and the sun out
  and bounces light back onto the subject; without it an interior gets much
  brighter and flatter.
- `light_path`: it stands between a scene light and something in view (it
  casts a shadow that is in the picture). A window frame or curtain between a
  lamp and the bed stays.
- `near_view`: it is within `shadow_margin` (30 cm) of the picture's edges: a
  branch just outside the frame shades the ground just inside it.
- `emits_light`: a lamp, screen or neon with an emissive surface lights the
  scene from off screen.
- `mirror_in_view`: a mirror-like surface (metallic, glossy) is in the
  picture. It can show anything, so nothing out of frame is dropped. Pass
  `ignore_reflections=true` only when you know what it reflects (and `keep`
  that). Glass in view only gives a warning: it reflects a little of the room
  behind the camera, which matters at night or against a dark outside.
- `keep`: you asked. `keep=["Ana"]` keeps Ana and everything she wears.

What the tool cannot know, so check it yourself:

- **The sun and the HDRI.** The dome and Sun-Sky light come from everywhere,
  not from a scene light. A tall building or a tree out of frame can still
  throw its shadow into the picture under a low sun. Raise `shadow_margin`
  (300-1000 cm outdoors in low sun) or `keep` the big shapes.
- **Light through windows.** The window, the walls around it and what stands
  outside it shape the patches of light on the floor. A room shell is usually
  one node and stays. Separate window, curtain or shutter props behind the
  camera can go when the light does not come through them into the frame;
  `keep` them when it does.
- **Covered clothing that moves.** A dForce skirt or a dancing figure can show
  what is under it between the tested frames. For an animation, test the whole
  range; if in doubt use `occlusion="none"`.
- **Close or wide.** A close-up on a face drops the whole body's clothing below
  the shoulders; the next wide shot needs it back. Cull per shot (`cull=true`
  on `render_shots`), never once for the whole scene.

When unsure, make a small test render with and without the cull and compare
them: the lighting must be the same.

## What it cannot drop

It works on whole nodes. One mesh is either in the render or not:

- A figure's own body is one mesh, so bare feet out of frame still render;
  they share the Legs textures anyway. What costs memory is what the figure
  wears, and that is separate nodes.
- A set made of one mesh (many rooms and parks are) stays whole. Sets made of
  many props, or trees placed as instances, drop part by part.

Other ways to lighten a render, by hand:

- **SubD:** a Genesis figure renders at its Render SubD Level (Minimum),
  often 3-4, which is millions of polygons. A figure far away or small in the
  picture looks the same at 1 or 2. It is a property of the figure's shape
  (with "View SubD Level", "Resolution Level").
- **Size and time:** render at the size you need and set `max_time`.
- **Fewer lights** and no unseen emissive props.

## Recipes

**A character in a long skirt, knees to head:**
```
render_cull(camera="Medium")
# would_hide: ["Shoes", "Panties (covered)", "Shoes Toon Outline"]
render(camera="Medium", cull=true, max_time=120)
```

**A big park, one character at one spot:**
```
render_cull(camera="Bench", detail=true)
# would_hide: 140 trees, the far paths, the fountain behind the camera
# kept: Tree 12 near_view, Streetlamp 3 emits_light
render(camera="Bench", cull=true, ...)
```
Check `kept` and the warnings, and raise `shadow_margin` for a low sun.

**A visual novel scene, many angles:** `render_shots(..., cull=true)`. Each
beat drops what its own camera does not see, and `shots.json` records how
much each beat hid.

**An animation loop from three cameras:** one `render_animation(camera=...,
cull=true)` per camera; each tests 12 frames of its range.

## What it saves, measured

Daz Studio 6.26, RTX 5060 8 GB, the saloon set (one 1.8 M facet mesh) with
two talking characters and three more people around the room, 1280x720, 500
samples, denoiser on:

| shot | without cull | with cull | image |
|---|---|---|---|
| close-up | 232 s, and 674 s on a second run (stopped at the time limit) | 82-83 s | mean difference 0.3 of 255, no pixel off by more than 25 |
| two shot | 478 s (stopped at the time limit) | 73 s | mean difference 0.3 of 255 |

It hid 12 % of the facets and 355 MB of textures for the close-up, 1 % for the
two shot, yet both got 3 to 6 times faster: the whole scene did not fit in
the card's memory, Iray slowed to a fraction of its speed (0.4-2 million
samples a second against 7 with the culled scene) and the CPU took part of
the work. The saving comes from staying under the GPU's memory, so it is
largest on cards of 8 GB or less, with several characters in the set and
heavy hair; on a scene that already fits it is small (73 s against 83 s on a
light close-up).
