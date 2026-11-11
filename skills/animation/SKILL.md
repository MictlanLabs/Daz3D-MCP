---
name: animation
description: How to animate Daz Studio figures, props and cameras with the daz3d MCP tools - keyframes, the timeline, walk cycles and other motions made from scratch, animation presets, Mixamo FBX and mocap BVH import onto Genesis figures, moving, retiming and fixing feet. Use when the user asks for motion, animation, a walk, a dance, keyframes, Mixamo or BVH.
---

# Animation in Daz Studio

Read `daz-basics` and `characters` first: animation keys the same bone dials
that `pose_bones` sets.

## How Daz animates

- The timeline counts **frames** (30 per second by default). `anim_timeline`
  reads and sets the frame rate, the range (first and last frame) and the
  current frame, and lists what is animated.
- A **key** fixes a value (a bone rotation, the hip's translation, a figure's
  position, a dial) at a frame. Daz fills in the frames between keys.
- Key every channel you animate at its **first frame too**. A channel with a
  single key holds that value on every frame, before and after it.
- Once a value has keys, changing it with `pose_bones`, `node_set` or
  `morph_set` at another frame also makes a key there.
- Clothing and hair fitted to a figure follow it: animate the figure only.
- Figures face +Z, their left is +X, Y is up, distances are cm.

## Keyframes

```text
anim_keys_set(node="Ana", keys=[
  {"frame": 0,  "bones": {"head": [0, 0, 0]}},
  {"frame": 15, "bones": {"head": [0, 35, 0]}},        # turns the head
  {"frame": 30, "bones": {"head": [0, 0, 0]}, "morphs": {"Jaw Open": 0.3}}])
anim_keys_get(node="Ana", summary=true)    -> what is keyed, over which frames
anim_keys_delete(node="Ana", bones=["head"], start_frame=10, end_frame=20)
```

- `bones` are rotations in degrees, `bone_positions` translations in cm (the
  hip carries the body up, down and forward), `position`/`rotation` move the
  node itself, `morphs` animate dials (expressions), `properties` any number
  (a light's power, a camera's focal length).
- `[x, null, z]` keys only some axes.
- `replace=[first, last]` clears old keys in that range first.
- `anim_key_pose(figure, frames=[...])` keys the current pose: load a pose
  preset (`content_load`) or pose with `pose_bones`, then key it.
- Cameras and props animate the same way (`position`, `rotation`).

## Checking a motion

Never trust key values alone: bone axes and signs vary.

- `anim_sample(figure, frames, bones)` gives world positions of bones as Daz
  computes them: is the left foot in front at frame 8 (larger z when walking
  toward +Z), does the hand reach the cup.
- `anim_preview(frames=[0, 8, 16, 24])` returns viewport images of several
  frames. Look at them before you report the motion as done.
- `anim_foot_contact(figure)` finds frames where a foot goes through the
  floor or the figure floats, and how far planted feet slide.
  `fix="lift"` raises the hip where feet go through the floor; `fix="plant"`
  also lowers it where both feet float (walks and runs, not jumps).

## A walk cycle from scratch

Block the key poses, then fill in. Two steps (a full cycle) take about 32
frames at 30 fps for a relaxed walk, 24 for a brisk one, 16 to 20 for a run.
Each step has four poses, 4 frames apart at 32 frames a cycle:

| pose | planted leg (thigh, shin, foot X) | swinging leg (thigh, shin, foot X) | hip y |
|------|------|------|-----|
| contact (0, 16) | -25, 5, -10 (heel down in front) | 25, 10, 15 (toes pushing off behind) | -3 |
| down (4, 20)    | -18, 15, 0 (knee takes the weight) | 15, 45, 25 (foot lifts) | -4 |
| passing (8, 24) | -5, 5, 0 (straight under the body) | -20, 55, 5 (knee comes through) | +1 |
| up (12, 28)     | 10, 5, 10 (heel lifts) | -30, 30, -5 (reaches forward) | +2 |

The left leg is planted from frame 0 to 16, the right one from 16 to 32;
frame 32 repeats frame 0. Values are Genesis 9 dials, in degrees.

- Arms swing opposite to the legs (left arm back when the left leg is forward):
  upper arm Y about 20 at contact, 0 at passing; forearms a little bent.
  The arms are mirrored: on Genesis 9 the same Y value on `l_upperarm` and
  `r_upperarm` swings them in opposite directions (+20 takes the left arm
  back and the right arm forward). So key both at +20 when the left leg is in
  front and both at -20 when the right leg is, and check with `anim_sample`.
- Travel: the hip moves forward one step per half cycle. A step is about
  `2 * leg length * sin(thigh swing)`, about 70 to 75 cm for a Genesis 9 at
  25 degrees. Key the hip z at every key pose (18.4 cm every 4 frames, 147 cm
  a cycle) so the speed stays even. Too little travel makes planted feet
  slide forward, too much backward; `anim_foot_contact` reports the slide.
  A cycle blocked by hand slides 10 to 25 cm; add keys where it slides most.
- Signs: on Genesis 9 and 8 a negative thigh X swings the leg forward and a
  positive shin X bends the knee. Key frame 0, check with `anim_sample` that the
  left foot is in front, then do the rest.
- Then `anim_foot_contact(fix="plant")` to settle the hip height, and
  `anim_preview`.
- To make it reusable: `anim_preset_save(figure, name="walk-relaxed",
  loop=true)`. Applying it with `repeat=4` walks four cycles, carrying on from
  where each ended.

## Presets

- `anim_preset_list()` lists built-in presets (idle-breathing, head-nod,
  head-shake) and the ones saved with `anim_preset_save`.
- `anim_preset_apply(figure, preset, start_frame, speed, repeat, in_place)`.
  `in_place=true` keeps a walk on the spot.
- Animation presets bought for Daz: `content_search(kind="animation")`, then
  `anim_preset_apply(figure, preset=<path>, start_frame=...)`. aniBlocks
  (aniMate) are not supported.
- A preset is made for one generation. On another one the bone names are
  translated, but check the result.

## Mixamo, mocap and other files (BVH, FBX)

```text
anim_file_inspect(path="/Users/me/Downloads/Walking.fbx", figure="Leo")
   -> rig (mixamo, cmu...), frames, fps, rest pose, bone_map pairs, missing bones
anim_import(path=..., figure="Leo", start_frame=0)
   -> frames, pairs, body_scale, root_travel_cm, check, warnings
anim_foot_contact(figure="Leo", fix="lift")
anim_preview()
```

- From Mixamo, download **FBX Binary**, 30 fps, "Without Skin" or "With
  Skin" (either works; with skin the bind pose is exact). "In Place" gives a
  motion that stays on the spot; or pass `in_place=true`.
- Mocap BVH (CMU, Truebones, Rokoko, Daz exports) works too. ASCII FBX does
  not: re-export it as binary.
- The bone map is automatic for Mixamo, CMU, Unreal, 3ds Max Biped and
  Genesis names. When `figure_bones_missing` or `file_bones_unused` show a
  gap, pass `bone_map={"file bone": "figure bone"}`; `null` drops a bone.
- The import adapts the rest pose (Mixamo's T pose to Genesis' A pose), the
  facing direction and the body size, and keys every frame. The first import
  in a Daz install also measures how Daz turns bones (`calibration`, about
  0.01 degrees off on a real Daz Studio 6); later imports reuse it.
- A file whose figure was placed or turned (an FBX exported from Daz with the
  figure turned 90 degrees) is told in the figure's own space:
  `file_placement_removed_deg` says how much turn was taken out, and the
  target walks its own way forward (+Z). Turn or move it after with
  `anim_offset`.
- `check_joint_angle_error_deg` above about 5 means Daz does not show what was
  computed: look at it with `anim_preview` and tell the user.
- Fingers come along when both rigs have them. Faces are not in Mixamo files.

## Moving and retiming

- `anim_offset(node, frames=30)` starts it a second later;
  `move=[x, y, z]` carries the whole motion; `turn=90` turns its path;
  `start_at=[x, z]` puts the hip on that spot at the first key.
- `anim_retime(node, speed=0.8)` slows it to 80 %; `length=48` fits it to
  48 frames; `start_frame`/`end_frame` retime only a part, and later keys move
  with it.
- `anim_timeline(fps=24)` changes the frame rate keeping the duration;
  `keep="frames"` keeps the frame numbers (the motion plays faster or slower).
- Combine motions in time: one animation from frame 0 to 60, the next from 60
  (`start_frame=60`), keys around the joint to smooth it.

## Rendering an animation

`anim_preview` shows the viewport. To render the animation with Iray use
`render_animation` (see the `rendering` skill): one image per frame, joined
into an MP4. It takes about frames x `max_time`: agree with the user on the
frames, size and time per frame first. A single frame is `render(frame=N)`.
