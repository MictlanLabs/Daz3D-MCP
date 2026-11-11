---
name: dialogue-scenes
description: How to render a conversation between Daz Studio characters as a series of shots for a visual novel, comic or storyboard with the daz3d MCP tools - the same place and characters seen from a new camera angle on the faces at each line of dialogue (close-ups, shot and reverse shot, over the shoulder, two shots), with expressions and gazes that follow the talk. Use when the user wants dialogue scenes, visual-novel backgrounds or CGs, a conversation told in images, or several angles of one scene.
---

# Dialogue scenes (visual novels)

Read `faces` (expressions, gaze) and `rendering` first. The goal: many images
of ONE moment in ONE place, cut like a film conversation, so the reader feels
the talk move forward. What changes between images is the camera, the faces
and the eyes; what stays is the set, the light and where the people are.

## Tools

- `camera_shot(subject, partner, shot)` frames a shot from the subject's own
  face (eye position, head size), so it works for any figure, seated or
  standing, tall or short:
  - `extreme_close_up` (eyes and mouth: shock, a secret, a tear),
    `close_up` (the head: the default for a line of dialogue),
    `medium_close_up` (chest up: calmer lines, gestures),
    `medium` (waist up: hands, props, posture),
    `over_the_shoulder` (past the partner's head at the subject: ties the two
    together), `two_shot` (both in profile-ish: the establishing shot).
  - `side="auto"` keeps the camera on one side of the line between the two
    (the 180 degree rule): if A looks screen left, B looks screen right, in
    every shot, so cuts read as two people facing each other. The result
    says `looks`; it must alternate between the two figures and never flip
    for the same figure. Pass `side` only to cross the line on purpose (a
    turn in the scene), and keep the new side from then on.
  - `angle` (degrees off the eyeline): 30 is the default close-up; 10 to 15
    feels intimate or confrontational (almost into the eyes); 60 to 90 is
    distant, a profile. `height` +10 to +20 looks down on someone (small,
    vulnerable); -10 to -15 looks up (strong, threatening). Keep 0 for
    neutral lines.
  - `lead_room` (0.12) moves the face away from the side it looks to, so it
    has room to look into. `max_distance` keeps the camera inside a small
    room (a wider lens keeps the framing).
  - `blocked_by` names heads in front of the face: raise `angle`, use
    `over_the_shoulder`, or move the figure. Walls and furniture are not
    checked: look at the image.
- `render_shots(beats=[...])` renders a whole conversation: each beat sets
  `faces` ({figure: expression or {expression, strength, values}}), `gaze`
  ({figure: target or {target, head}}; `"camera"` looks into the lens), frames
  `camera_shot` with the beat's shot fields and renders `NN_<name>.png`.
  Faces and gazes not named in a beat stay as they were, so name only what
  changes. It writes `shots.json` (beat, file, line, shot, camera) for the
  game engine. `resume=true` (default) skips images already there, and
  `only=[3]` redoes one beat while still setting the earlier faces.

## The method

1. **Stage the set once.** Place the characters where they talk, 80 to 150 cm
   apart, turned toward each other (cheat them 10 to 20 degrees toward the
   room's open side, the side the cameras will use). Seated figures:
   `furniture-poses`. Pose the bodies now; dialogue beats change only faces,
   eyes and the head turn.
2. **Light once, for every angle.** A key light on each face from the open
   side, a soft fill, and the room's own light (windows, lamps). Lights
   that move with the camera make the cut jump. Check that both faces are lit
   in a close-up from each side before rendering the whole scene.
3. **Save the scene** under a new name before the batch (`scene_save`).
4. **Write the beats from the script.** One beat per line of dialogue or
   reaction. A good rhythm:
   - open on a `two_shot` (where we are, who is there),
   - then alternate `close_up` on the speaker and `over_the_shoulder` or
     `close_up` on the listener (shot / reverse shot),
   - a reaction shot (the listener's face, no line) after an important line,
   - get closer as the talk gets more intense (medium_close_up -> close_up ->
     extreme_close_up), wider when it relaxes or ends (back to a two_shot),
   - do not cut between two shots of the same person with the same size and
     angle: change the shot size or the angle by 20 degrees or more.
5. **Faces and eyes per beat.** The speaker looks at the partner
   (`gaze: {"A": "B"}`); looking away (a point on the floor, out a window)
   reads as shame, sadness or a lie; looking into the camera breaks the fourth
   wall (only for a narrator moment). Use `strength` 0.5-0.8: full
   expressions look like masks in a close-up. Blink (`eyes_closed` 0.3) or a
   small brow dial (`values`) make two shots of the same line differ.
6. **Test first.** Render 2 or 3 beats small and fast (`width` 640, `height`
   360, `max_time` 10) and check: faces lit, nothing in front of a face, the
   `looks` alternate, the gazes meet. Then render the rest at the game's size
   (1920x1080 is common for visual novels; match the game's aspect) with more
   time. Ask the user before a long render: it takes about beats x max_time.
7. **Deliver** the folder and `shots.json`.

## Notes

- The tool frames from the eyes in world up/down, so it suits upright heads
  (standing, sitting). For a figure lying down, place the camera with
  `camera_create` instead, above the face.
- Change the render size before framing, or call `camera_shot` again after:
  the framing depends on the picture's aspect ratio.
- An over the shoulder shot of a seated subject from a standing partner looks
  down at them (and the reverse looks up); that is right for the scene, but
  for an even eyeline use `close_up`.
- Expressions and head turns carry over between beats: a `gaze` with `head`
  turns the head from where it is now, so a later beat with `head` 0 keeps it
  turned. Reset a face with `neutral` when a beat needs a clean start.
- `eyes_look_at` reports eyes that hit their limit (about 30 degrees);
  `render_shots` lists them in `warnings`. Give that gaze `head` 0.3 to 0.6.
- Tested on Daz Studio 6.26 with a seated Genesis 9 and a standing Genesis
  8.1 Male about 90 cm apart: close-up, reverse close-up, both over the
  shoulder shots and a two shot cut on the same side of the line.
  `max_distance` 110 kept the two shot inside a small attic.
