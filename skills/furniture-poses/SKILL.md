---
name: furniture-poses
description: How to put Daz Studio figures on furniture with the daz3d MCP tools - sitting on a chair, sofa or bench, lying on a bed, leaning, standing on a step - with measurements instead of guesses, so the body rests on the surface without floating or passing through it, and the pose looks natural. Use when the user wants a character sitting, lying, or resting on or against a prop.
---

# Figures on furniture

Read `characters` first (bones, axes, pose presets). Placing a body on a prop
by eye fails: a chair's bounding box says nothing about its seat, and the
viewport hides a hip 5 cm inside a cushion. Measure, place, check, look.

## The loop

1. **Measure the prop.** `prop_surfaces(node="Chair")` lists its flat
   surfaces: `height` (world cm), `size_cm`, `center`, and for a seat with a
   backrest `facing_yaw` (the figure's Y rotation to face out of it) and
   `back_edge_cm`. A seat is usually 40 to 50 cm high, a sofa 38 to 45, a bed
   mattress 45 to 60, a bar stool 65 to 80. If the biggest surface is not the
   one you want (a table top, an armrest), note the `index` of the right one.
2. **Pose first, then place.** Load a sitting or lying pose preset for the
   figure's generation, or build the pose with `pose_bones` (starting angles
   below). `pose_bones` reports `clamped` dials that hit a joint limit; check
   limits up front with `figure_info(figure, limits=["l_upperarm", "l_thigh"])`.
3. **Place.** `place_on(figure, prop, contact="seat")` turns the figure to
   face out of the seat, centers the hips across it, slides them back until
   the back of the body is `back_gap` (1 cm) from the backrest, moves the
   knees clear of the seat front, and lowers the hips onto the cushion
   (`sink` 0.5 cm). For a bed: `contact="back"` (face up), `"front"` (face
   down), `"left_side"` or `"right_side"`. Standing on a step: `"feet"`.
   It returns where it put the figure and a `fit` report.
4. **Read the fit report** (`fit_check` gives the same for any figure):
   - `parts.<part>.max_depth_cm` and `way_out`: how deep that body part is
     inside the prop and which way gets it out, as the figure sees it (up,
     down, forward, back, left, right). Up to 1 cm is contact, not overlap.
   - `gap_below_cm`: how far a part floats above the surface under it.
   - `touching`: parts resting on something.
   - Thighs 2 to 5 cm into a soft cushion read as the cushion giving way.
     More than that, or anything into a hard frame, backrest or armrest, needs
     a fix: change the pose of that part (not the whole figure) and place again.
5. **Feet.** `fit_check(figure, against=["<room or floor prop>"],
   floor_y=<floor height>)` adds `feet.<foot>.above_floor_cm`. Aim for 0 to 1.
   A foot in the air: lower the knee (thigh X less negative, about 0.8 cm per
   degree for an adult thigh) or bend the knee less. A foot through the floor:
   the opposite. Then `place_on` again, since the legs change where the hips
   land. Tilt the foot (foot X) so the sole lies flat. When the seat is too
   high for the figure, heels off the floor with the toes down is natural.
6. **Hands.** `figure_info(figure, landmarks=true)` gives the lowest point of
   every body part (world cm): compare hands with thighs, armrests or a table.
   Hands on the thighs, in the lap, on the armrests or on the seat beside the
   hips are all natural; `fit_check` shows hands inside the cushion.
7. **Look from two sides.** Front and side views catch what numbers miss.
   For a seat with `facing_yaw` = a, a side camera about 100 cm to one side:
   `camera_create(label="Side", position=[x, 70, z], look_at=[seat x, 55,
   seat z], focal_length=24)` with x = seat x + 100 cos(a), z = seat z - 100
   sin(a). If `viewport_capture` fails (a locked screen), a small, short
   render (480x360, `max_time` 8) works. Hide props that block the view with
   `node_set(visible=false)` and show them again afterwards.
8. **Save** the scene to a new file.

## Starting angles (Genesis 9, measured in Daz Studio 6)

Sitting on a chair, back against the backrest (seat 45 to 50 cm, an average
adult). Measured on a real Genesis 9; one `place_on` after this put the hips
on the seat and both feet within 1 cm of the floor.

| Bone | Value | Notes |
|---|---|---|
| `l_thigh` / `r_thigh` | `[-76, -3, -5]` / `[-74, 3, 5]` | X swings the leg forward (-90 is level), Z opens the knees |
| `l_shin` / `r_shin` | `[85, 0, 0]` / `[78, 0, 0]` | X bends the knee; the shin is vertical when shin X = -thigh X |
| `spine1`, `spine2` | `[4, 0, 0]`, `[3, 0, 0]` | a slight forward curve; 0 sits bolt upright |
| `l_upperarm` / `r_upperarm` | `[0, -12, -40]` / `[0, 12, 40]` | Z stops at -40 / 40 (the arm cannot drop below that from the A pose): swing Y forward instead |
| `l_forearm` / `r_forearm` | `[0, -25, 0]` / `[0, 25, 0]` | Y bends the elbow; more bend lifts the hands into the lap |
| `neck2`, `head` | `[3, 6, 0]`, `[4, 8, 3]` | turn the head toward what the person looks at |

- Feet ahead of the knees (shin X smaller than -thigh X) looks relaxed; feet
  under or behind the knees looks attentive.
- Legs crossed: the upper thigh Y about 15 toward the other leg and Z to lift
  it over, its shin bent less. One figure cannot be tested against itself,
  so look from the front and the side for thigh through thigh.
- Lying on the back: a lying pose preset, or turn the figure with
  `node_set(rotation=[-90, yaw, 0])`, then `place_on(contact="back")`.
  Shoulders and hips sink 2 to 4 cm into a mattress. The head belongs on the
  pillow: `prop_surfaces(node="Pillow")` and the head's `gap_below_cm`.
- Genesis 8: the same idea with `lThighBend`, `lShin`, `lFoot`, `lShldrBend`,
  `lForearmBend`, `abdomenLower`, `chestLower`. Signs can differ: change one
  bone by 10 degrees, check where it went with `figure_info(landmarks=true)`
  or `anim_sample(bones=[...])`, then go on.

## What makes a pose look natural

- **Weight goes somewhere.** A seated body rests on hips and thighs and leans
  on the backrest, or forward on the knees or a table. Floating hips, or a
  straight back with nothing behind it, look stiff.
- **Asymmetry.** Never mirror both sides exactly: one foot 5 to 10 cm ahead,
  knees a few degrees apart, one hand higher, head tilted 2 to 5 degrees.
- **Nothing locked.** Elbows and knees a little bent, fingers slightly curled
  (hand "Pose Controls" dials, or finger bones a few degrees).
- **Stay inside the limits.** A dial pinned at its limit (`clamped`) usually
  means another joint should do the work: bend the spine, the shoulder
  (`l_shoulder`) or the forearm instead. Use `ignore_limits=true` only for a
  pose that really needs it, and look closely at the result.
- **Gaze.** Turn the head (and a little of the chest) toward what the person
  attends to: another figure, a screen, the camera.
- **Clothing.** A skirt or coat can pass through the seat while the skin does
  not: `fit_check(worn=true)` tests clothes too (their parts show as
  `worn:<part>`); fix them with the garment's dials or `wearable_adjust`.
