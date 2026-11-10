# Stage 4 closing test

Goal: an agent makes, on a real Daz Studio 6, **a walk cycle from scratch**
on one Genesis 9 and **adapts a Mixamo animation** to a second Genesis 9.

Stage 4 passes its closing test in simulation
(`tests/test_stage4_closing.py`, against `tests/fake_daz`). The simulated Daz
keys properties, interpolates between keys and computes bone positions with
forward kinematics, following the public DazScript API reference
(DzFloatProperty keys, DzScene time, DzBone orientation). It is not Daz
Studio: the checks below are what only a real Daz Studio can confirm.

## 1. Prepare

1. Stages 1 to 3 must pass first ([stage1](stage1-closing-test.md),
   [stage2](stage2-closing-test.md), [stage3](stage3-closing-test.md)), with
   Genesis 9 Starter Essentials installed.
2. From [Mixamo](https://www.mixamo.com) (free Adobe account), pick any
   character and a walk, for example "Walking". Download it as
   **FBX Binary (.fbx)**, **30 frames per second**, skin "Without Skin",
   keyframe reduction "none", into `~/Downloads/Walking.fbx`. Leave
   "In Place" unchecked.
3. Optional: a mocap BVH, for example one of the CMU files converted for
   MotionBuilder (cgspeed), into `~/Downloads/`.
4. Update the agent (`uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --client claude-code`)
   and restart it so it picks up the new tools and the `animation` skill.
5. Start Daz Studio with an empty scene.

## 2. Run in the agent

> In Daz Studio, load two Genesis 9 figures called Ana and Leo, Leo 150 cm to
> Ana's left. Make Ana walk with a walk cycle you build from scratch with
> keyframes: two steps, keep her feet on the floor, save it as a looping
> preset called "walk cycle", make her walk three cycles, slow it to 80 % and
> have her walk along +X starting at x = -200, z = 100. Then put
> ~/Downloads/Walking.fbx from Mixamo on Leo, starting at frame 10. Show me
> frames 0, 30, 60 and 90.

Then play the timeline in Daz Studio (the play button) and look at both.

## 3. Pass criteria

| Check | Result |
| --- | --- |
| The timeline is 30 fps and ends at frame 120 | |
| Ana's legs swing forward and back the right way (the foot in front is the opposite of the arm in front) | |
| Ana's knees bend forward, never backward | |
| Ana's feet stay on the floor: no sinking, no floating, little sliding | |
| The preset shows in `anim_preset_list` and repeats without a jump between cycles | |
| After the retime and the move, Ana walks along +X from (-200, 100) | |
| `anim_import` reports `calibration` and `check_joint_angle_error_deg` under 5 | |
| Leo's walk looks like the one on Mixamo: arms down by his sides (not in a T), legs and arms in step | |
| Leo walks forward (+Z), at about the speed on Mixamo, starting at frame 10 | |
| `anim_preview` images match what Daz plays | |
| Saving and reopening the scene keeps both animations | |
| No dialog blocked Daz Studio | |

Also note: what `anim_file_inspect` and `anim_import` reported (rig,
bone_map, calibration convention, warnings), the slide in centimeters from
`anim_foot_contact`, and anything the agent had to do with `run_script`.

## 4. What only a real Daz Studio can confirm

| Area | Assumption | Where |
| --- | --- | --- |
| Time | 4800 ticks per second; `Scene.getTimeStep()` is ticks per frame; `setTimeStep`, `getAnimRange`/`setAnimRange`, `getPlayRange`/`setPlayRange`, `getTime`/`setTime`, `new DzTimeRange(start, end)` | `core.dsa`, `anim_timeline.dsa` |
| Keys | DzFloatProperty `setValue(time, value)` makes a key once the property is animated (or always); `getValue(time)` interpolates; `getNumKeys`, `getKeyTime(i)`, `getKeyValue(i)`, `deleteAllKeys`, `deleteKeys(range)` | `core.dsa` |
| Keys | A property's first key does not also key frame 0 | `anim_keys_set.dsa` |
| Keys | Daz interpolates with TCB by default; the simulation is linear, so motions in Daz can overshoot a little between keys | everywhere |
| Bones | `getOrigin()` / `getEndPoint()` are rest positions in cm; `getOrientation()` is a DzQuat (x, y, z, w) of the joint axes; `getRotationOrder()` gives the order as three letters or a number | `anim_skeleton.dsa` |
| Bones | A bone's rotation is parent · orientation · Euler(dials) · orientation⁻¹. `anim_import` measures which of four conventions Daz uses on the first run (`calibration`); if all four miss by more than 3 degrees the import warns | `anim_tools.py` (`calibrate`) |
| Bones | `getWSPos()` of a bone follows the current time after `Scene.setTime` | `anim_sample.dsa` |
| Bones | Genesis 9 dials: negative thigh X swings the leg forward, positive shin X bends the knee (the walk cycle table in the skill) | `skills/animation/SKILL.md` |
| Hip | Hip translation dials ("XTranslate"...) move the whole body in cm | `anim_keys_set.dsa` |
| Presets | An animated pose preset (.duf with keys) loads at the current frame through `ContentMgr.openFile(path, true)` | `anim_preset_load.dsa` |
| Content | Bought animation presets sit under `/Animations/` or have type `preset_animation`, so `content_search(kind="animation")` finds them | `content.py` |
| Preview | `viewport_capture` at a frame shows the pose of that frame | `anim_preview` |
| Files | Real Mixamo FBX files: names with `mixamorig:`, PreRotation, unit scale, very long takes; the reader handles FBX 7.x binary only | `motion.py` |
