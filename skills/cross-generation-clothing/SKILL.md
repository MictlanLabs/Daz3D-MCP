---
name: cross-generation-clothing
description: How to put clothing and shoes made for one Genesis generation on a figure of another (Genesis 8 or 8.1 items on Genesis 9 and the reverse) with the daz3d MCP tools - the Auto-Fit dialog, and finding and repairing what Auto-Fit leaves wrong (pieces left in the old figure's shape and bones that do not follow the pose, belts fitted to other clothes), above all shoes that end up in the wrong place (the foot flat through a heeled shoe, the shoe sunk under the floor or in the middle of the foot). Use when content_load opens the Auto-Fit dialog or warns an item is for another generation, when the only clothes or shoes the user has are for another Genesis, or when shoes look misplaced in a capture or render.
---

# Clothing from another Genesis generation

Read `characters` first. Content is made for one generation: Genesis 8 and
8.1 share theirs, Genesis 9 has its own. Daz can convert an item on load
(Auto-Fit), but it often leaves pieces unconverted and gets shoes wrong.
`wearable_refit` finds and repairs both. This is the routine.

## 1. Load: the Auto-Fit dialog

```text
figure_info(figure="Laura").generation                      -> "Genesis 9"
content_load(path=".../Genesis 8 Female/.../Bardot Sandals.duf", target="Laura")
   -> error dialog_open: "Auto-Fit : Bardot Sandals" ... Buttons: Accept, Cancel, Fit Only, ...
daz_dialog(button="Accept")                                 -> call_result: fitted_to "Laura"
```

- **Accept** converts the item: reshapes it from the old figure to the new
  one and gives it the new figure's bones. This is the one to press.
- **Fit Only** skips the conversion (the item keeps the old figure's shape):
  do not use it. **Cancel** loads nothing.
- The dialog only appears when the clone of the old figure is installed for
  the new one (Genesis 9 ships with clones of Genesis 8 Female and Male). The
  two drop-downs (which figure, what type of item) cannot be changed through
  `daz_dialog`; their defaults work, and `wearable_refit` covers what the
  "type of item" choice would have done for shoes.
- No dialog and the warning "not fitted ... another figure generation": there
  is no clone. Use `wearable_from_mesh(item, figure)` (see
  `third-party-assets`), then continue here.
- An outfit asks once **per piece**, and only the first dialog stops the
  `content_load` call: the others open after it returns. `daz_dialog` lists
  them in `more_dialogs` with a hint; answer every one. A piece whose dialog
  nobody answers stays in the old figure's shape and bones.
- The buttons named after a figure ("Genesis 9", "Genesis 8 Female") and
  "None" pick which figure the item was made for. The right one is usually
  already picked; pressing it first (`daz_dialog(button="Genesis 9",
  wait=0)`) and then **Accept** is harmless.

## 2. Check the whole figure

```text
wearable_refit(item="Laura")                 # a figure: everything she wears
   -> items: [{item: "Bardot Top", verdict: "misplaced", problems: ["not_converted"]},
              {item: "Bardot Sandals", problems: ["foot_floating", "pose_not_applied"]}, ...]
wearable_refit(item="Laura", fix=true)       # repairs each piece that is not ok
```

Run it after loading any clothes from another generation, before posing and
rendering: an unconverted piece can look right in the default pose and only
go wrong when the arms or legs move. For every piece (tops, pants, belts,
helmets, shoes) it reports:

- `rig`: how much of the item hangs from bones the figure has
  (`matched_share`). Under half (`not_converted`): it is still rigged to the
  old generation's bones (`l_upperarm` on a Genesis 8 figure, `chestUpper` on
  Genesis 9), so it keeps the old body's shape and stays put when she moves.
  This happens to the pieces whose Auto-Fit dialog was never answered, and to
  items fitted to other items (a belt on an overall).
- `shape`: median distance from the item to the skin, as it is and with each
  of the figure's clone shapes dialed in. Much closer with a clone
  (`other_shape`): it was rigged but not reshaped.

`fix=true` rebuilds such a piece with Daz's Transfer Utility, which is what
Auto-Fit does when it converts: the figure takes the old generation's shape
(its clone), the figure's rigging is projected onto the item, and the item is
moved to the figure's own shape. Items fitted to it (belts, zips, buttons)
are moved to the rebuilt piece and converted too. `convert=false` skips it.
Then footwear goes through the steps below.

## 3. Footwear in detail


```text
wearable_refit(item="Bardot Sandals")
```

Always run it after Auto-Fit converts shoes, boots or sandals, before any
render: the capture can look right from the front and be wrong from the side.
It changes nothing and reports:

- `feet.left` / `feet.right`: how the sole of each foot sits on the item.
  `resting` (on the sole), `floating` (more than 1.5 cm above it),
  `through_sole` (below it), `under_foot` (share of the sole that has the
  item under it at all), `median_gap_cm`.
- `lowest_cm`: lowest point of the item and of the bare feet. An item far
  below the feet is under the floor.
- `source`: the file the item came from, the generation it was `made_for`,
  and the foot `pose` that file carries, already translated to this figure's
  bone names.
- `problems` and `verdict` (`ok` or `misplaced`):

| code | what it means |
|---|---|
| `pose_not_applied` | the shoe's file poses the feet (a heel), Daz skipped it because Genesis 8 calls the bones `lFoot`, `lToe` and Genesis 9 `l_foot`, `l_toes` |
| `foot_floating` | the foot is flat above a sole made for a raised heel |
| `foot_through_sole` | the foot goes down through the sole |
| `not_under_foot` | the item is not under the foot at all (wrong place, wrong scale) |
| `below_floor` | the sole is under the floor; `fix` stands the figure on it |
| `not_converted`, `other_shape` | see above: the piece is rebuilt first |

`feet.*.heel_minus_toe_cm` tells a missing heel pose (the heel floats far
more than the toes) from a thick flat sole: boots whose insole is not
modeled leave an even 2 to 3 cm under the whole foot, reported as a note,
not a problem.

Why it happens: a heeled shoe is modeled around a foot already in the heel
pose, and its file sets that pose when it loads. On another generation the
pose is lost, so the foot stays flat: the heel pokes through the back of the
shoe, the toes float over the front, and the sole sits several cm under the
floor.

### Repair

```text
wearable_refit(item="Bardot Sandals", fix=true)
   -> done: ["weights", "pose", "keep_shape", "ground"], verdict: "ok",
      before: {...}, after: {feet: {left: {resting: 0.96, ...}}}
viewport_capture()      # from the side, close to the feet: camera_create(position=[90, 15, 30], look_at=[12, 8, 2])
```

In order, it:

1. **weights**: puts back the weights the shoe's author painted, under the
   new bone names, instead of the ones Auto-Fit projected from the skin (a
   rigid sole should move with the foot, not stretch like skin). Footwear
   only.
2. **pose**: turns the feet and toes the way the shoe's file asks.
3. **keep_shape**: adds a morph to the item ("MCP Shape Keep") so that, with
   the feet in that pose, the shoe has exactly the shape and place it was
   designed with. After that it follows the foot in any pose.
4. **ground**: lifts the figure so the soles stand where the bare feet stood
   (a 9 cm heel lifts her about 5 cm).

It is safe to run again: it starts over from what Auto-Fit made. The repair
is saved with the scene.

Options:

- `ground=false` for a figure that is sitting or lying, or already placed
  with `place_on`: the hips must not move. Check the feet against the floor
  with `fit_check(figure, floor_y=0)` instead. `floor_y=...` when the floor
  is not where the bare feet were.
- `foot_pose={"l_foot": [26, 0, 0], "l_toes": [-35, 0, 0], "r_foot": [26, 0, 0],
  "r_toes": [-35, 0, 0]}` when the file has no pose (`source.pose` missing).
  Foot X raises the heel, toes X negative bends the toes back up to the
  ground. Start from the heel height: 5 cm about 15, 8 cm about 26, 12 cm
  about 40; toes about the same angle negative, then read `after.feet` and
  adjust. Flat shoes need no pose: `foot_pose="none"`.
- `source=".../Shoes.duf"` when the file is not found by itself (the item was
  renamed, or came from a saved scene). Outfits often ship the pose as its
  own file beside the shoes ("... !FootPose.duf", "... Heels Pose.duf"): it
  is found when it is in the same folder; otherwise pass it as `source`.
- `keep_shape=false`, `weights=false` turn those steps off (to compare).

After the repair the shoe follows the foot, so a pose preset that sets the
feet (most full-body poses do) takes them out of the heel pose and tilts the
shoes with them. Run `wearable_refit(item, fix=true, ground=false)` once
more after loading a pose, or keep the feet out of it by posing with
`pose_bones`.

## 4. The rest of the outfit

Once `wearable_refit` reports a piece `ok`, what is left is cosmetic: skin
poking through and loose shapes.

- Look from two sides (`camera_set(yaw=...)`) in the pose the scene uses.
- Skin through the cloth: `wearable_adjust(item, smoothing=true,
  collision_iterations=4)`; up to 10 for tight clothes on a curvier body.
- The item's own fit dials came along: `morph_list(node=item)` and
  `morph_set` (Expand All, Loosen...).
- Long skirts and coats lose the bones that moved them (Auto-Fit keeps only
  the figure's). They hang stiff between the legs in wide poses: prefer an
  item for the right generation, or keep the pose narrow.
- Gloves and hats: `wearable_refit(item)` checks their rig and shape; look
  at a capture for the fit.
- Hair: **Accept**, then look at the hairline from the front and the side.
- Covered by clothing anyway? Hide the body part instead of fighting the last
  poke: see "Fixing poke-through" in `third-party-assets`.

## Rules

- Prefer an item made for the figure's generation when the user has one
  (`content_search(query, kind="clothing", generation=...)`). Convert when
  they ask for that item or own nothing else.
- Never leave converted footwear unchecked. `verdict: "misplaced"` before a
  render means stop and repair.
- Tell the user what was converted and repaired, and show the feet from the
  side.
- `wearable_refit` checks rig, shape and feet. It does not judge style: a shoe two sizes too
  big for a small character still reports `ok`. Look at the capture.
