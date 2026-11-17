---
name: realistic-renders
description: How to make Daz Studio renders look like photographs instead of plastic 3D with the daz3d MCP tools - skin that stacks two specular layers, imported props with one flat sheen, flat lighting, a clean digital image - and how to fix each with surface_realism, light_rig (low-key portrait on black, soft studio, window light, neon), camera and render settings, and render_postwork (film tone curve, split toning, local contrast, grain, vignette). Use when the user says a render looks plastic, fake, CG, like a video game, too clean or too shiny, asks for a realistic or cinematic look, a portrait on a black background, or asks how other artists make their renders look real.
---

# Renders that look real, not plastic

Read `rendering` first. A raw Iray render is physically lit but still reads as
3D. Five things cause most of it, in this order of impact:

1. **Materials**: skin with two shiny layers, props with one flat sheen.
2. **Light**: even, frontal light with no shape, no rim, no dark side.
3. **Camera**: wide lens, everything sharp, eye-level framing of a mannequin pose.
4. **The image itself**: perfectly clean, linear tones, saturated colors.
5. **Assets**: low-resolution textures (512 px car interiors, game models).

Fix them in that order; postwork alone cannot save plastic skin.

## 1. Materials: surface_realism

```text
surface_realism(node="Ana")                       # skin: one soft specular
surface_realism(node="Ana", skin="matte")         # powdered, no shine
surface_realism(node="BMW", children=true)        # an imported car: every part
surface_realism(node="Ana", dry_run=true)         # only report
```

- **Skin.** Many character presets set both the Glossy layer and the Dual
  Lobe Specular on Face, Torso, Arms, Legs (Glossy Layered Weight 0.25 plus
  Dual Lobe 0.55 is common). Two stacked speculars read as wet plastic under
  studio lights. `skin="natural"` keeps one soft dual lobe (weight 0.4,
  roughness 0.55 / 0.38) and nearly drops the glossy layer. `oily` for sweat,
  rain or a night club; `matte` for a powdered or cold look.
- **Imported props** (FBX, OBJ, Sketchfab, game models) come in with Daz's small
  "Physically Based Rendering" shader: base color, metal, roughness, normal
  map, nothing else. Every surface gets the same flat sheen. `upgrade=true`
  rebuilds each one as Iray Uber, keeping its textures, with the finish its
  name suggests: leather (soft gloss), cloth / headliner (matte), plastic
  (satin), chrome (mirror), car paint (clear top coat), rubber, glass
  (refraction), wood, metal. Look at the result: a surface with a vague name
  ("standard1", "Object12") gets a generic finish, set it with `material_set`.
- Clothing that looks like rubber: `material_set(node, {"Glossy Layered
  Weight": 0.05, "Glossy Roughness": 0.85})` for cotton, denim, wool.
- Hair that looks like plastic is usually a dual-lobe hair seen in the viewport
  only: check a render before changing it.

## 2. Light: light_rig

```text
light_rig(subject="Ana", preset="low_key")                 # portrait on black
light_rig(subject="Ana", preset="soft_studio", side="right")
light_rig(subject="Ana", camera="Bus Window", preset="window")
light_rig(subject="Ana", preset="neon", power_scale=1.3)
```

It places photometric soft boxes from the camera's point of view (so they land
right whatever the camera angle), labels them "Rig Key", "Rig Rim Cool"...,
replaces the previous rig, switches off the other lights (`solo=false` keeps
them), and sets the background and exposure the preset needs.

| preset | for | lights | background, EV |
|---|---|---|---|
| `low_key` | dramatic portrait, character sheets | key 55° to the side and above, cool rim and warm rim from behind, very little fill | black, scene only, EV 10 |
| `soft_studio` | catalog, clean character turnarounds | big soft key 40°, fill, hair light | light grey, dim dome, EV 11 |
| `window` | interiors: a bus, a room, a car | warm daylight from the side, cool fill | keeps the HDRI and set |
| `neon` | night, clubs, cyberpunk | dim warm key, cyan and magenta rims | near black, EV 10 |

What makes light look real (when building lights by hand with `light_create`):

- **One dominant light.** The key is 4 to 10 times the fill. Even light from
  everywhere is what looks fake.
- **Light from the side, a little above** the eyes: the far cheek falls into
  shadow and the face gets shape.
- **Rim light from behind** separates the subject from a dark background and
  outlines hair and shoulders.
- **Big sources are soft** (Light Geometry Rectangle, 60 to 120 cm); a small
  spot gives hard shadows (sun, street lamp).
- **Warm against cool**: warm key, cool rim or fill (or the reverse at night).
- Photometric spot lights stop at 10000 lm: move a light closer instead of
  asking for more. A sun through a window: a spot 1.5 to 2.5 m outside, aimed
  at the face, warm (#ffb36b), 25 to 35 degree spread.
- In an interior lit by an HDRI, add a soft light near the camera side at low
  power so the face is not a silhouette against the window.

## 3. Camera

- **Lens**: 50 to 85 mm for portraits and dialogue (`camera_shot` picks one),
  24 to 35 mm only for rooms and establishing shots. A wide lens close to a face
  distorts it.
- **Depth of field** sells scale. With `run_script`, on the camera node: the
  "Depth of Field" property on, "Focal Distance" = distance from the camera to
  the eyes in cm (`head bone getWSPos()` minus the camera's), "F/Stop" 2.8 to
  5.6 for portraits, 8 for interiors. A chrome rail
  in the blurred foreground makes a bright bokeh disc: raise the F/Stop.
- **Height**: slightly above the eyes for a neutral look, below for power.
- Do not put a seat back or a rail between the camera and the hands or face.

## 4. Pose (see `characters` and `furniture-poses`)

A mannequin pose is as fake as plastic skin. Weight on one leg, arms not in the
A-pose (shoulder bend Z at the limit brings them down), elbows and fingers a
little bent (Fingers Fist 0.2 to 0.35), head turned a few degrees, eyes at
something (`eyes_look_at`). Reset hand controls left from an earlier pose
(Hand Fist, Hand Grasp drive the fingers too). For a waist-up shot, hide pants
whose waist pokes through the shirt (`node_set(visible=false)`).

## 5. Render settings

- `render_settings(exposure=...)` to match the rig (`light_rig` sets it).
- Tone mapping: Burn Highlights 0.25 to 0.35 (keeps skies and highlights from
  clipping), Crush Blacks 0.15 to 0.2.
- Final images: 1920x1080 or more, `max_time` 300 to 600 s, or until the noise
  is gone; test renders at half size and 30 to 60 s.
- Save the scene before a long render (`scene_save`): a crash loses it.
- A render with nothing drawn behind the subject (no backdrop, dome not drawn)
  is a PNG with a transparent background. Good for a visual-novel sprite;
  `render_postwork(background=...)` fills it with a color.

## 6. Postwork: render_postwork

This is what most realistic Daz artists do after the render (Photoshop,
Lightroom, Affinity). The tool does it with ffmpeg (Daz Studio ships one):

```text
render(camera="Portrait", max_time=400, postwork="film")      # writes <name>-post.png too
render_postwork(image="C:/.../render.png", look="soft", strength=0.8)
render_postwork(image="...", look="film", background=null)  # keep transparency (sprites)
```

- **film** (default): lifted blacks, soft highlight roll-off, cool shadows and
  warm highlights, 10 % less saturation, local contrast (clarity), lens
  sharpening, fine grain, vignette.
- **soft**: gentler, for faces and bright scenes. **punchy**: more contrast for
  night, action, neon. **neutral**: keeps the colors, only fills the
  background, sharpens and adds grain.
- `strength` scales the look (0.5 subtle, 1.5 strong); `grain`, `vignette`,
  `sharpen` override one part. The raw render is never overwritten.
- For a visual novel, use the same look and strength on every image of a
  scene so the shots match.

## 7. Assets: what tools cannot fix

- Texture resolution sets the ceiling: 4096 px skins and props hold a close-up;
  512 to 1024 px (game models, old FBX cars) look like a video game up close.
  Frame them smaller, blur them with depth of field, or recommend a store item
  with Iray materials and 2K to 4K maps.
- HD characters (HD morphs, 4K skin with normal and bump maps), strand or
  fibre hair and dForce clothing make the biggest jump in realism.

## A full pass

```text
surface_realism(node="Ana")                          # skin
surface_realism(node="Bus", children=true)           # imported set or vehicle
light_rig(subject="Ana", preset="low_key")           # or window / soft_studio
camera_shot(subject="Ana", shot="medium_close_up")   # 50-85 mm, then depth of field
scene_save()
render(camera="Shot", width=1440, height=1800, max_time=400, postwork="film")
```

Show the user the raw and the post version the first time, so they can choose
the look; then keep it for the whole project.
