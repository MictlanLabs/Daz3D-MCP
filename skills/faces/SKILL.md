---
name: faces
description: How to edit a Daz Studio character's face and looks with the daz3d MCP tools - facial expressions, where the eyes look, eye (iris) color, skin tone, hair, eyebrow and beard color, makeup. Use when the user asks for an expression or gesture, a smile, a wink, to look at the camera or at someone, or to change eye, skin or hair color.
---

# Faces: expressions, gaze and colors

Read `characters` first. Check the generation with `figure_info(figure).generation`:
the names below were verified on a real Genesis 9 (Laura) and Genesis 8.1 Male.

## Expressions

- `face_expression(figure, expression, strength)` clears the face, then sets a
  named expression: `smile`, `big_smile`, `smirk`, `sad`, `angry`, `surprised`,
  `afraid`, `disgusted`, `pain`, `wink`, `eyes_closed`, `mouth_open`, `kiss`;
  `neutral` only clears. Left/right (smirk, wink) are the figure's own.
- `strength` 0.5 is subtle, 1 full, up to 1.5 exaggerated. Add single dials on
  top with `values`, e.g. `{"Brow Inner Up Left": 0.4}`, and `reset=false` to
  build on the current face instead of clearing it.
- Expression pose presets also work: `content_search(query="expressions",
  generation=...)` (Genesis 9 has "CDI SVE G9F Mad", "Scream"...). Load them with
  `content_load(path, target=figure)`.
- Genesis 8.1 also has whole-face dials under "Pose Controls/Head/Expressions 8.1":
  Surprised, Smile Full Face, Smile Open Full Face, Shock, Frown, Flirting,
  Angry, Afraid (set them with `morph_set`).
- Face dials are FACS dials. Many are controls of the figure node, not morphs
  (Eye Blink, Brow Up, Jaw Open on 8.1); `morph_list(node, query="pose controls
  head")` lists them all, marked `control: true`. Shared names: Mouth Smile,
  Mouth Frown, Brow Up, Brow Inner Up, Brow Down, Eye Blink, Eye Wide, Eye
  Squint, Cheek Squint, Nose Sneer, Mouth Upper Up, Mouth Lower Down, Mouth
  Stretch, Mouth Press. Jaw Open is `facs_bs_JawOpen` on Genesis 9 and
  `facs_jnt_JawOpen` on 8.1. Visemes (Vis AA, Vis EE...) shape speech.
- Render a close-up to judge: a camera 40-60 cm in front of the eyes, 85-135 mm,
  and a soft spot light near the camera. Faces are small in wide shots.

## Where the eyes look

- `eyes_look_at(figure, target)`: target is a camera (look into the lens),
  another figure (its eyes), a node or `[x, y, z]`. Each eye aims on its own,
  so they converge on near targets.
- The eyes turn about 30 degrees at most. If the result lists `limited`, turn
  the head too: `head=0.3`-`0.6` turns that share of the way first.
- It clears the "Eye Look" dials and sets the eye bones (`l_eye`/`r_eye` on
  Genesis 9, `lEye`/`rEye` on Genesis 8). Call it again after moving the figure,
  the head or the target. `face_expression` does not move the eyes.

## Eye color

- `eye_color(figure, color="#3a7bd5")` tints only the iris; the whites stay
  white. On Genesis 9 it first switches to light grey iris 3 so the tint shows
  true (`keep_iris=true` tints the current iris). `strength` (default 0.85)
  softens it.
- Genesis 9 real irises: `iris=1..16` (1 hazel, 2 grey-brown, 3 light grey,
  4 amber, 5 dark brown, 6 gold, 7 pale grey-blue, 8 hazel-gold, 9 grey-green,
  10 blue-grey, 11 violet fantasy, 12 blue with gold, 13 blue, 14 grey
  freckled, 15 green, 16 light brown). Natural eyes: pick an iris, no color.
- `eyes="left"` / `"right"` colors one eye (heterochromia, Genesis 9 only).
  `remove=true` takes the tint off.
- Genesis 8 / 8.1 has one "Irises" surface for both eyes; only `color` works.
- Character eye presets: `content_search(query="eyes", kind="material",
  generation=...)`, e.g. "Laura G9 Eyes".

## Skin

- Best: a skin material preset (`G9 Feminine Skin 01-04 MAT`, `G9 Masculine Skin
  01-04 MAT`, each character's "Skin MAT"), loaded on the figure.
- Fine-tune with `material_set(figure, {"Base Color": "#e8d0c0"}, surfaces=[...])`
  on ALL skin surfaces at once, or seams show. Genesis 9 (PBRSkin): Head, Body,
  Arms, Legs, Fingernails, Toenails. Genesis 8.1 (Iray Uber): Face, Head, Lips,
  Ears, Body, Arms, Legs, EyeSocket, Fingernails, Toenails.
- Base Color multiplies the skin image: it can only darken or shift the tone,
  never lighten. Stay close to white (#e0c8b8 is already a clear change).

## Hair, eyebrows, beard

- Look at the shader in `material_list(item)`:
  - **Blended Dual Lobe Hair**: set Hair Root Color, Hair Tip Color, Hair Root
    Highlight and Hair Tip Highlight on every Hair surface (this darkened a beard
    as expected). If the hair still looks lighter than asked, also darken Root/Tip
    Transmission Color and the HairCap surface's Base Color, and judge it in a
    render with enough samples: a quick noisy render makes dark hair look lighter.
    For a big change, the hair's own color presets are more reliable.
  - **Iray Uber** with a hair image (Eirgrid): Base Color multiplies the image, so
    it only darkens. For another color use the hair's own presets:
    `content_search(query="eirgrid", kind="material")` (Blonde, Black, Red,
    Grey, Blue...).
- Genesis 9 eyebrows: presets "G9 Eyebrows Color Black/Blond/Brown/Red/Grey..."
  (Eyebrows Fiber or Card, matching the eyebrows worn), or Base Color on
  Eyebrows_Primary / Eyebrows_Secondary. Genesis 8.1 eyebrows are painted in the
  skin.

## Makeup

- Genesis 9 PBRSkin has Makeup Enable / Makeup Base Color / Makeup Weight, but
  without a mask image it covers the whole surface. Use makeup presets
  (`content_search(query="makeup")`); if only "Remove" presets are installed,
  tell the user makeup needs a makeup product.
