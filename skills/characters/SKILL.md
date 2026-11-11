---
name: characters
description: How to build and adjust Daz Studio characters with the daz3d MCP tools - Genesis figures, character presets, morphs (shape), clothing, hair, poses and bones. Use when the user asks for a person or character, to dress, style, shape or pose a figure.
---

# Characters in Daz Studio

Read `daz-basics` and `scene-building` first.

## What a character is made of

- A **base figure**: Genesis 9 (one figure for every body type), Genesis 8 /
  8.1 Female and Male, older Genesis 3 and 2. Most current content is for
  Genesis 9 and Genesis 8.
- A **character preset** (`kind: character`) turns the base figure into a
  specific person: it sets shape dials and skin materials.
- **Shape dials (morphs)** change the body and face.
- **Clothing** and **hair** are separate figures fitted to the base figure;
  they follow its pose and shape.
- A **pose preset** rotates the bones.

Content only fits the generation it was made for. Always check
`figure_info(figure).generation` and search with that `generation`.

## Building one character

```text
content_search(query="genesis 9", kind="figure")        -> base figure path
content_load(path)                                      -> added: "Genesis 9"
node_set(node="Genesis 9", label="Ana")
content_search(kind="character", generation="Genesis 9") -> pick one
content_load(path, target="Ana")
content_search(query="dress", kind="clothing", generation="Genesis 9")
content_load(path, target="Ana")                        -> fitted_to: "Ana"
content_search(kind="hair", generation="Genesis 9")
content_load(path, target="Ana")
content_search(kind="pose", generation="Genesis 9")
content_load(path, target="Ana")
figure_info(figure="Ana")                               -> check it all
viewport_capture()
```

- Clothing, hair, poses, characters, shapes and materials **need a target**.
  Aiming a pose at an item the figure wears applies it to the figure.
- Rename figures right after loading. Daz numbers duplicate labels, so a second
  Genesis 9 is "Genesis 9 (2)" and a second pair of the same shoes is
  "Canvas Sneakers (2)".
- If `content_load` warns that an item is not fitted, it was made for another
  generation. Prefer an item for the right generation; `wearable_fit(item,
  figure)` forces a fit but results vary.
- A complete outfit is usually a top, a bottom (or a dress), shoes, and hair.
  Many outfits come as several files in one folder: search the folder.
- Removing an item: `node_delete(nodes=["Item label"])`.

## Shape (morphs)

- `morph_list(node, query="height")` finds dials; `only_nonzero=true` shows
  what a character preset set.
- `morph_set(node, values={"Body Tone": 0.5, "Height": -0.2})`. Values are
  0 to 1 for most dials (1 = 100 %); some go from -1 to 1. Values are clamped
  to the dial's range. Unknown names come back in `not_found` with similar ones.
- Keep changes moderate (0.1 to 0.6). Several strong dials at once look
  unnatural. Change, capture, look.
- Dials under "Pose Controls" (facial expressions, hand poses) are morphs too.

## Poses

- A pose preset from the library is the best start: it is made by an artist.
  Then fine-tune with `pose_bones`.
- `pose_bones(figure, bones={"head": [0, 15, 0]}, relative=true)` turns the
  head 15 degrees. `figure_info(all_bones=true)` lists every bone name.
- `pose_reset(figure)` returns to the default pose (Genesis 9 and 8 start in an
  A pose, arms about 45 degrees down).
- Axes depend on the bone. Usual Daz conventions:
  - head, neck, spine, hip: X bends forward/back, Y turns left/right, Z tilts sideways.
  - upper arms: Z raises/lowers, Y swings forward/back, X twists.
  - forearms: Y bends the elbow (Genesis 9), X twists.
  - thighs: X swings the leg forward/back, Z opens it sideways, Y twists.
  - shins: X bends the knee.
  Signs differ between left and right. Make one small change, capture, and
  correct, instead of setting many bones blind.
- Genesis 9 bone names: `hip`, `pelvis`, `spine1`-`spine4`, `neck1`, `neck2`,
  `head`, `l_shoulder`, `l_upperarm`, `l_forearm`, `l_hand`, `l_thigh`,
  `l_shin`, `l_foot`, and the same with `r_`. Genesis 8 uses `abdomenLower`,
  `chestUpper`, `neckLower`, `lCollar`, `lShldrBend`, `lForearmBend`,
  `lThighBend`, `lShin`, `lFoot`, and so on.
- After posing, check feet on the floor (`node_set(drop_to_floor=true)` on the
  figure) and hands not passing through the body or clothes (capture from two
  angles with `camera_set(yaw=...)`).
- `pose_bones` reports dials that Daz held at a joint limit (`clamped`).
  `figure_info(limits=[...])` lists the limits, and `figure_info(landmarks=true)`
  says where each body part ends up.
- Sitting, lying or leaning on furniture: follow the `furniture-poses` skill
  (`prop_surfaces`, `place_on`, `fit_check`).

## Materials of a character

- `material_list(node)` shows the surfaces (Head, Body, Arms, Legs, Eyes...
  for a figure; a few named surfaces for clothing) and their main values.
- `material_set(node, properties={"Base Color": "#2a6f97"}, surfaces=[...])`
  recolors clothing. Omitting `surfaces` changes all of them.
- Material presets (`kind: material`) restyle clothing or skin: load them with
  `content_load(path, target=item)`.
- Change skin only when the user asks; character presets already set it.
- Expressions, where the eyes look, and eye, skin, hair and makeup color: follow
  the `faces` skill (`face_expression`, `eyes_look_at`, `eye_color`).
