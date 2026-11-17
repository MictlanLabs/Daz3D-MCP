---
name: character-design
description: How to turn a description in words into a unique Daz Studio character and keep it as an editable character sheet with the daz3d MCP tools (character_create, character_load, character_update, character_list) - body build, height, weight, bust, muscle, age, and every detail of the face (face shape, forehead, brows, eyes, eyelids, lashes, irises, pupils, nose, cheeks, lips, philtrum, jaw, chin, ears, teeth, gums, fangs, wrinkles, asymmetry), skin tone and marks, eye and sclera color, hair, eyebrows, facial hair, nails, clothes and fantasy add-ons, on Genesis 9, 8.1 and 8. Use when the user describes a character (for a visual novel, comic or story) to create, save, reuse in other scenes, keep distinct from the rest of a cast, or change later.
---

# Character design and character sheets

Read `characters` first (figures, clothing, hair, poses) and `faces` (eye
color, skin tone, hair color shaders).

A **character sheet** is a JSON file that describes one character in words
that do not depend on the Genesis generation: **traits** from -1 to 1
(`nose_width: 0.4`), plus skin, eyes, colors, hair, eyebrows, facial hair,
clothes and add-ons. Each time a sheet is applied, the traits are mapped to the
dials **installed** on that figure, so one sheet works on Genesis 9, 8.1 and 8.
Next to it is a Daz character preset (`.duf`: shape and materials) that the
user can also apply by hand in Daz. Sheets live in
`~/.daz3d-mcp/characters/<name>.json` (setting `characters_dir`).

## The tools

```text
character_create(name, description, notes, generation | base_figure | figure, character_preset,
                 traits, dials, height_cm, skin, eyes, hair, brows, facial_hair, colors,
                 clothing, extras, presets, materials, position, overwrite)
character_load(name, figure=None, label=None, position=None, use_preset=true, steps=None)
character_update(name, figure=None, <any field of create>, add_clothing, remove_clothing, refresh)
character_list(include_traits=false, name=None)
```

- `character_create` loads the base figure (Genesis 9 unless told), labels it
  with the name, applies everything, saves the sheet and the preset.
  `figure="Label"` turns a figure already in the scene into the character.
  `overwrite=true` replaces a saved character of the same name.
- `character_load` adds the character to the open scene; `figure="Label"`
  applies the sheet to a figure already there (any generation); `label=` names
  a second copy.
- `character_update` changes only what it is given. A trait set to 0 or null
  goes back to the base figure; `dials={"X": null}` removes a dial;
  `height_cm=0` removes the exact height; `clothing=[...]`, `extras=[...]`,
  `presets=[...]` and `materials=[...]` replace those lists, while
  `add_clothing` / `remove_clothing` edit the outfit. If the character is in
  the scene (a figure labeled with its name, or `figure=`), the figure changes
  too, items that leave the sheet are deleted, and the preset is saved again.
  `refresh=true` applies the whole sheet again (after hand edits).
- `character_list()` lists saved characters; `character_list(name=X)` shows a
  whole sheet; `include_traits=true` lists every trait with what +1 and -1 mean.
- If a step stops on a Daz dialog (Auto-Fit), the result says `stopped` and
  lists `remaining_steps`: answer with `daz_dialog`, then
  `character_load(name, figure=<label>, steps=<remaining_steps>)`.
- Before `character_create` or `character_update` saves the preset, clear any
  test expression (`face_expression(figure, "neutral")`), or the preset may
  keep it.

## 1. Ask, then assume

A visual-novel author may give two lines. Do not ask twenty questions and do not
invent silently.

- Ask at most 3 to 5 short questions, in one message, only about what defines
  the character and is not given: body base (feminine / masculine, Genesis 9 or
  8.1), age range, skin tone or ancestry, hair style and color, eye color,
  build and height, and one signature feature ("what should people remember
  about their face?").
- Fill everything else with sensible defaults, write the assumptions in
  `notes`, and list them in your reply. If the user says "just do it", ask
  nothing and state the assumptions.

## 2. Feature checklist

Go through every line for every character, in this order (silhouette first,
details last). Each line lists the traits that cover it and the other way to
get the rest (material, item, preset).

1. **Base**: Genesis 9 + `feminine` or `masculine` 1 (a 0.1-0.3 cross blend
   gives an androgynous or tough look); Genesis 8.1 Female / Male when the
   user's clothes are for 8.1 or the look needs 8.1-only dials (elf ears);
   `base_figure` for the Genesis 9 anime bases; `character_preset` to start
   from a finished character.
2. **Age**: `age`, `wrinkles`, `eye_bags`, `jowls`, `nasolabial`,
   `double_chin`; without those dials see "Age without dials".
3. **Height and build**: `height_cm` (exact), `weight`, `muscle`, `bust`,
   `breast_shape`, `areola_size`, `nipple_projection`, `nipples_detail`, `chest_width`, `shoulders`, `waist`, `belly`, `hips`,
   `glutes`, `thighs`, `calves`, `upper_arms`, `forearms`, `legs_length`,
   `arms_length`, `torso_length`, `neck_length`, `neck_width`, `adams_apple`,
   `head_size`, `hands_size`, `fingers_length`, `feet_size`, `nails_length`.
4. **Head and face shape**: `face_width`, `face_length`, `face_round`,
   `face_square`, `face_heart`, `skull_back`, `temples`, `asymmetry`.
5. **Forehead and brows**: `forehead_height`, `forehead_width`,
   `forehead_slope`, `brow_height`, `brow_ridge` (bone); the brow **hair**
   (thickness, arch, color) is the eyebrow item: `brows`.
6. **Eyes**: `eyes_size`, `eyes_width`, `eyes_height`, `eyes_spacing`,
   `eyes_position`, `eyes_deep`, `eyes_tilt`, `eyes_inner_corner`,
   `eyelids_heavy`, `eyelids_lower`, `eyelid_crease`, `iris_size`,
   `pupils_slit`, `cornea_bulge`; colors: `eyes.color` / `eyes.iris`,
   `eyes.left` / `eyes.right`, `eyes.sclera`.
7. **Lashes**: `eyelashes_length`, `eyelashes_curl`, `lashes_volume`,
   `lashes_flare`, `lashes_natural`, `lashes_sparse`.
8. **Nose**: `nose_size`, `nose_width`, `nose_length`, `nose_bridge`,
   `nose_bridge_width`, `nose_hump`, `nose_projection`, `nose_tip_up`,
   `nose_tip_size`, `nostrils_width`, `nostrils_height`, `septum`,
   `nose_crooked`.
9. **Cheeks**: `cheekbones`, `cheekbone_width`, `cheeks_fullness`, `dimples`,
   `nasolabial`.
10. **Mouth and lips**: `lips_fullness`, `lip_upper`, `lip_lower`,
    `lower_lip_pout`, `lips_protrusion`, `cupid_bow`, `philtrum`,
    `mouth_width`, `mouth_corners`; lip color: `colors.lips` (Genesis 8 / 8.1)
    or a lipstick preset.
11. **Jaw and chin**: `jaw_width`, `jaw_definition`, `jaw_angle`,
    `jaw_shift`, `chin_length`, `chin_width`, `chin_forward`, `chin_cleft`,
    `double_chin`, `jowls`.
12. **Ears**: `ears_size`, `ears_out`, `ears_height`, `ears_angle`,
    `earlobes`, `ears_pointed`; one-sided ear shapes in `dials` (section 6).
13. **Teeth** (seen when smiling or talking): `teeth_size`, `teeth_length`,
    `teeth_width`, `teeth_taper`, `teeth_gap`, `teeth_crooked`, `bite`,
    `gums_hidden`, `fangs`, `fangs_lower`; colors: `colors.teeth`,
    `colors.gums`.
14. **Skin**: `skin.preset` (depth and texture), `skin.tone` (undertone),
    freckles, moles, scars, tattoos, makeup in `presets` and `skin.details`;
    fantasy colors and finish in `materials`.
15. **Hair, eyebrows, facial hair**: `hair`, `brows`, `facial_hair` (items,
    `color`, `tip_color`).
16. **Hands and nails**: `hands_size`, `fingers_length`, `nails_length`,
    `colors.nails`.
17. **Outfit and add-ons**: `clothing` (shoes too); `extras` for horns, tail,
    wings, animal ears; `anatomy` for genital geografts (section 9b).
18. **Signature feature**: pick one thing people will remember and give it
    0.4 to 0.6 (a nose hump, gap teeth, high cheekbones, ears that stick out,
    heterochromia, a scar).

## 3. From words to traits

Strength: 0.2 subtle, 0.4 clear, 0.7 strong, 1 the most the dial gives. Most
real faces need 0.15 to 0.5; several traits near 1 look like a caricature.
One-way traits (0 to 1 only): `feminine`, `masculine`, `pupils_slit`,
`chin_cleft`, `nose_hump`, `ears_pointed`, `teeth_gap`, `gums_hidden`, `fangs`,
`fangs_lower`, `wrinkles`, `eye_bags`, `jowls`, `double_chin`, `dimples`,
`nasolabial`, `adams_apple`, `nipples_detail`, `eyelashes_length`, `lashes_volume`,
`lashes_sparse`, `lashes_natural`, `asymmetry`.

**Body**

| The user says | Traits |
|---|---|
| very tall / short | `height_cm` (exact), or `height` 0.5 / -0.5 |
| heavy, chubby / slim, skinny | `weight` 0.5 / -0.4 |
| athletic, muscular / soft | `muscle` 0.5 / -0.3 |
| curvy | `hips` 0.4, `bust` 0.3, `waist` -0.2 |
| pear-shaped | `hips` 0.5, `thighs` 0.3 |
| beer belly / flat stomach | `belly` 0.6, `weight` 0.2 / `belly` -0.3 |
| thick thighs / skinny legs | `thighs` 0.5 / `thighs` -0.4, `calves` -0.3 |
| big arms / skinny arms | `upper_arms` 0.5, `forearms` 0.3 / `upper_arms` -0.4 |
| big rear / flat rear | `glutes` 0.4 / -0.3 |
| perky / natural breasts | `breast_shape` 0.4 / -0.4 |
| large / small areolas | `areola_size` 0.5 / -0.4 (the color is the skin image: see section 9) |
| prominent / flat nipples | `nipple_projection` 0.5 / -0.4, `nipples_detail` 0.6 |
| broad shoulders | `shoulders` 0.5, `chest_width` 0.3 |
| long legs / long arms, lanky | `legs_length` 0.4 / `arms_length` 0.4 |
| long torso / short-waisted | `torso_length` 0.3 / -0.3 |
| swan neck / short neck / bull neck | `neck_length` 0.4 / -0.3 / `neck_width` 0.5 |
| Adam's apple | `adams_apple` 0.5 |
| big head (childlike, chibi) / small head | `head_size` 0.3 / -0.3 |
| big hands / dainty hands, long fingers | `hands_size` ±0.4, `fingers_length` 0.4 |
| big / small feet | `feet_size` ±0.4 |
| long nails | `nails_length` 0.5 |
| old, middle-aged / youthful | `age` 0.7 / 0.3 / -0.4 (see "Age without dials") |

**Head, forehead, brows**

| The user says | Traits |
|---|---|
| round / square / heart / long face | `face_round`, `face_square`, `face_heart`, `face_length` 0.4 |
| wide / narrow face | `face_width` ±0.4 |
| big, high forehead / sloping forehead | `forehead_height` 0.4 / `forehead_slope` 0.4 |
| hollow temples (gaunt) | `temples` -0.5 |
| heavy brow, stern | `brow_ridge` 0.5, `brow_height` -0.3 |
| high, surprised-looking brows | `brow_height` 0.4 |

**Eyes and lashes**

| The user says | Traits |
|---|---|
| big eyes / small eyes | `eyes_size` 0.3 / -0.3, `iris_size` 0.3 |
| almond eyes | `eyes_width` 0.4, `eyes_tilt` 0.2 |
| round, open eyes / narrow, squinty eyes | `eyes_height` 0.4 / -0.4 |
| upturned, cat-like / sad, downturned | `eyes_tilt` 0.5 / -0.4 |
| hooded or sleepy eyes | `eyelids_heavy` 0.5 |
| tired eyes, droopy lower lids | `eyelids_lower` 0.4, `eye_bags` 0.4 |
| monolid | `eyelid_crease` -0.6, `eyelids_heavy` 0.3, `eyes_inner_corner` 0.4 |
| deep-set eyes | `eyes_deep` 0.5 |
| wide-set / close-set eyes | `eyes_spacing` 0.4 / -0.4 |
| eyes set high / low | `eyes_position` 0.3 / -0.3 |
| slit pupils (cat, reptile, demon) | `pupils_slit` 1 |
| lively, glassy eyes | `cornea_bulge` 0.4 |
| long, curled lashes / doll-like lashes | `eyelashes_length` 0.6, `eyelashes_curl` 0.5 / + `lashes_volume` 0.5, `lashes_flare` 0.4 |
| natural, uneven lashes / no lashes | `lashes_natural` 0.5 / `lashes_sparse` 1 |

**Nose**

| The user says | Traits |
|---|---|
| big nose / button nose | `nose_size` 0.4 / -0.4, `nose_tip_up` 0.4 |
| wide, flat nose | `nose_width` 0.5, `nose_bridge` -0.4, `nostrils_width` 0.4 |
| thin, straight (Greek) nose | `nose_width` -0.3, `nose_bridge` 0.4, `nose_bridge_width` -0.3 |
| aquiline, hooked nose | `nose_hump` 0.6, `nose_bridge` 0.4, `nose_tip_up` -0.3 |
| upturned / drooping nose tip | `nose_tip_up` 0.5 / -0.4, `septum` 0.3 |
| long / short nose | `nose_length` 0.4 / -0.4 |
| prominent / flat nose in profile | `nose_projection` 0.4 / -0.4 |
| bulbous / fine pointed tip | `nose_tip_size` 0.5 / -0.4 |
| flared nostrils | `nostrils_width` 0.5 |
| broken boxer's nose | `nose_crooked` 0.5, `nose_bridge_width` 0.3, `nose_hump` 0.3 |

**Cheeks, mouth, lips**

| The user says | Traits |
|---|---|
| high cheekbones / wide cheekbones | `cheekbones` 0.5 / `cheekbone_width` 0.4 |
| chubby cheeks / hollow cheeks | `cheeks_fullness` 0.5 / -0.5 |
| dimples / laugh lines | `dimples` 0.6 / `nasolabial` 0.4 |
| full lips / thin lips | `lips_fullness` 0.6 / -0.5 (`lip_upper`, `lip_lower` for one) |
| pouty lips | `lower_lip_pout` 0.5, `lip_lower` 0.3 |
| lips that stick out / set back | `lips_protrusion` 0.4 / -0.3 |
| cupid's bow | `cupid_bow` 0.5 |
| long upper lip (older look) / short | `philtrum` 0.4 / -0.3 |
| wide / small mouth | `mouth_width` 0.4 / -0.4 |
| always seems to smile / grumpy mouth | `mouth_corners` 0.4 / -0.4 |

**Jaw, chin, ears**

| The user says | Traits |
|---|---|
| strong, sharp jaw | `jaw_definition` 0.6, `jaw_width` 0.3, `jaw_angle` 0.4 |
| soft, round jaw | `jaw_definition` -0.4, `jaw_angle` -0.4 |
| delicate jaw, pointed chin | `jaw_width` -0.4, `chin_width` -0.4 |
| long / short chin | `chin_length` 0.4 / -0.4 |
| prominent / receding chin | `chin_forward` 0.5 / -0.5 |
| cleft chin | `chin_cleft` 0.7 |
| crooked jaw | `jaw_shift` 0.5 |
| double chin, jowls | `double_chin` 0.5, `jowls` 0.4 |
| big / sticking-out ears | `ears_size` 0.4, `ears_out` 0.5 |
| ears set high / low, tilted back | `ears_height` ±0.3, `ears_angle` 0.4 |
| big earlobes / attached lobes | `earlobes` 0.5 / -0.4 |
| elf ears | `ears_pointed` 0.8 (see "Fantasy features") |

**Teeth**

| The user says | Traits and colors |
|---|---|
| big teeth / small teeth | `teeth_size` 0.4 / -0.4 |
| long, horsey teeth / short teeth | `teeth_length` 0.5 / -0.4 |
| broad / narrow teeth | `teeth_width` ±0.4 |
| gap between the front teeth | `teeth_gap` 0.6 |
| crooked, bad teeth | `teeth_crooked` 0.6, `colors.teeth` "#e0d0a0" |
| yellowed teeth | `colors.teeth` "#e8dcb0" |
| sharp, predatory teeth / shark teeth | `teeth_taper` 0.6, `teeth_length` 0.3 / `teeth_taper` 0.9 + `fangs` 0.5 |
| buck teeth, overbite / underbite | `bite` 0.5, `teeth_length` 0.3 / `bite` -0.5, `chin_forward` 0.3 |
| gummy smile / no gums show | `gums_hidden` 0 / 0.6 |
| vampire fangs / orc tusks | `fangs` 0.8 / `fangs_lower` 0.8 |
| gold teeth | `materials`: `{"on": "mouth", "surfaces": ["Teeth"], "properties": {"Base Color": "#d4a020", "Metallic Weight": 1}}` (all teeth: a single gold tooth needs a product) |

**Mood words** (when the user gives an impression instead of features)

| The user says | Traits |
|---|---|
| rugged | `jaw_definition` 0.4, `brow_ridge` 0.3, `cheeks_fullness` -0.2, `nose_bridge_width` 0.2 |
| gentle, kind | `face_round` 0.3, `mouth_corners` 0.2, `eyes_tilt` -0.1, `brow_height` 0.1 |
| menacing | `brow_height` -0.3, `eyes_deep` 0.4, `cheeks_fullness` -0.3, `mouth_corners` -0.2 |
| cute | `eyes_size` 0.3, `nose_size` -0.3, `face_round` 0.3, `cheeks_fullness` 0.2 |
| elegant | `neck_length` 0.3, `cheekbones` 0.4, `nose_width` -0.2, `jaw_width` -0.2 |
| gaunt, sickly | `temples` -0.5, `cheeks_fullness` -0.5, `eye_bags` 0.4, `weight` -0.4 |

Ancestry shapes eyelids, nose bridge, lips and skin. Start from a fitting skin
preset and character head blend, change `eyelid_crease`, `eyes_inner_corner`,
`nose_bridge` and `lips_fullness` moderately, avoid caricature, and confirm
the look with the user.

For anything with no trait, find an installed dial with `morph_list(figure,
query="...")` (or on `"Genesis 9 Mouth"` / `"Genesis 9 Eyes"`) and put it in
`dials` by its exact label, with `mouth:` or `eyes:` in front for those parts.

## 4. What works with only the starter content

Most users have only the dials that come with the base figures. Say what to
expect before promising a look:

| | Genesis 9 (starter) | Genesis 8.1 Female (starter) |
|---|---|---|
| Works | proportions (height, legs, arms, torso, neck, head, hands, feet, shoulders, chest), `feminine` / `masculine`, face shape, brows, eye spacing, tilt, height, depth, eyelids, crease, cheeks, lips, mouth corners, cupid's bow, nostrils, ear height, `jaw_shift`, `nose_crooked`, `asymmetry` (all through the paired asymmetry dials), all teeth traits except bite, `iris_size`, `pupils_slit`, lashes | `weight` down (Emaciated), `hips` (Pear Figure), `muscle` (Bodybuilder), `ears_pointed` (Ears Elf Long), `nails_length`, lashes, `cornea_bulge` |
| Approximated | `bust` (chest scale), `nose_width` (nostrils), `eyes_size` (eyeball only), `fangs` / `fangs_lower` (toon canines) | `bust`, `head_size`, hands, feet (scales), `height` (figure scale) |
| Missing | `weight`, `muscle`, `age`, `wrinkles`, waist, hips, belly, thighs, nose size, length, bridge, hump, tip, jaw width and definition, chin, ears size and shape, forehead, temples, philtrum, dimples, `bite` | almost every face trait |

`morph_generate` (section 4b) makes 24 of the missing dials on Genesis 9 and
on Genesis 8 / 8.1 (weight, muscle, belly, age, nose size, length, bridge,
tip, chin, jaw, cheekbones, temples, eye bags, philtrum, lips, ears). The full
Head and Body Morphs packs turn most "missing" lines into "works"; the
traits stay in the sheet, so `character_update(name, refresh=true)` applies
them once the packs are installed. An elf on starter content is easier on
Genesis 8.1 Female (Ears Elf Long).

## 4b. Making the missing dials

`morph_generate(figure)` lists the dials it can make for that figure. On
Genesis 9 and Genesis 8 / 8.1 (Female and Male): `nose_width`, `nose_size`,
`nose_length`, `nose_bridge`, `nose_tip_up`, `philtrum`, `temples`, `eye_bags`,
`cheekbones`, `chin_length`, `chin_forward`, `jaw_width`, `jaw_definition`,
`lips_fullness`, `ears_size`, `ears_out`, `age` (eye bags, sagging lower
cheeks, hollow temples, lower brows and mouth corners, thinner lips), `weight`,
`muscle` (bulk on arms, shoulders, chest and legs, a slimmer waist), `belly`,
`bust`, `breast_shape`, `areola_size` and `nipple_projection`. `morph_generate(figure, traits=[...])` makes them from the figure's
own mesh, its face and body bone weights and points found on the face (nose
tip, outer brow, ears), labels them "MCP <name>" (group Daz3D-MCP), saves them
in Daz's first content library (`data/<figure>/Morphs/Daz3D-MCP/Generated`),
so every new figure of that generation has them, and makes what the figure
wears (clothing, hair, brows, lashes, eyes, mouth) follow them. Do it once per
install and generation, before `character_create`; traits then find the new
dials (`how: "generated"`).

- Ask the user before making them the first time: they are written into their
  Daz library. `save=false` keeps them in the scene only.
- They are simpler than Daz's own morph packs: keep them at 0.6 or less and
  check a render (section 8). At 1 each moves the skin about as far as a
  clear but natural change (0.2-0.7 cm on the face, a few cm for weight and
  belly). A dial from an installed pack, and the paired Genesis 9 asymmetry
  dials, win over an MCP dial with the same meaning; an MCP dial wins over an
  approximated substitute.
- Items loaded later follow them after `character_load` / `character_update`
  (the `follow` step) or `morph_generate(figure, traits=[...], save=false)`.

**Shapes no recipe makes: sculpt them in Blender.** For a specific nose,
breast shape, ear or anything else the user can describe better with a brush:

1. `morph_export(figure, path="C:/.../g9_base.obj", units="m")` writes the base
   mesh (no morphs, default pose, base resolution).
2. In Blender: File > Import > Wavefront (.obj) with the default axes, sculpt
   with the sculpt brushes only (no Remesh, Dyntopo, Decimate or applied
   Subdivision: the vertex count and order must stay the same), don't move or
   scale the object, then File > Export > Wavefront (.obj) with "Selected only"
   and no modifiers.
3. `morph_import(figure, obj="C:/.../sculpt.obj", label="Hooked Nose",
   group="/Actor/Head/Face/Nose")` makes the dial "MCP Hooked Nose": size and
   Y-up / Z-up axes are matched automatically, `fit.median_offset_cm` shows how
   well it lined up, it is saved in the library and worn items follow it. Put
   it in a sheet with `dials={"MCP Hooked Nose": 0.8}`.

ZBrush or any modeler works the same way through OBJ.

## 5. What the result says

- `traits`: each trait, the dials it set and how: `dial` / `found` (a dial made
  for it), `generated` (an "MCP" dial from `morph_generate`), `pair` (the Genesis 9 left and right asymmetry dials set together,
  so both sides change evenly), `scale` (no height dial: the figure was
  scaled), `base figure` (`feminine` on a Female figure). `approximated: true`
  marks a near substitute: tell the user.
- `missing`: traits with no installed dial. Tell the user which details could
  not be made, and the options (`morph_generate` for the ones it can make,
  install the morph packs, pick a character preset close to the look, mix
  character heads, below).
- `followers`: worn items made to follow generated dials.
- `dials_not_found`: names in `dials` this figure lacks (often another
  generation's); `similar` suggests close names.
- `unknown_traits`: names in a hand-edited sheet that are not traits (typos).
- `notes`: things only partly done (iris images on Genesis 8, lip color on
  Genesis 9...). `height_cm`: the measured height.

## 6. Making a face unique with few dials

- **Character head and body blends** (Genesis 9): `morph_list(figure,
  query="people")` lists them (Laura, Kat, Amala, Ty, Matt, Fabrice, Base
  Anime...). `dials={"Laura Head": 0.35, "Amala Head": 0.25, "Kat Body": 0.3}`
  makes a face that is none of them. Rules: keep each blend's sum near 1 or
  less; head and body blends are separate; do not mix the Base Anime head with
  realistic heads unless on purpose; a 0.1-0.2 head of the other sex adds
  character; after a blend, lower trait values (0.15-0.3) since the blend
  already moves the face; body blends change height, so give `height_cm`.
- **One-sided asymmetry** looks natural: `asymmetry` 0.5-1 sets a small,
  fixed mix of one-sided dials; or set single dials, e.g.
  `{"Asymmetry Brow Height Left": 0.1}` (a value in `dials` adds to what a
  trait sets on the same dial). Genesis 9 asymmetry dials by feature: Brow
  Height / Size; Eyes Angle, Position Width / Height / Depth, Eyelids Upper /
  Lower Relax, Eyelids Crease Height; Nose Wing Size / Height Position, Nose
  Tip Balance, Nose Rotate, Nose Bridge Horizontal, Nose Base Twist / Horizontal;
  Cheek Size; Jaw Horizontal Balance; Mouth Angle, Mouth Mid Curve; Lip Upper /
  Lower Thickness; Face Round / Square / Heart; Ears 01 / 02 / 03 (three ear
  shapes, 0 to 1) and Ears Position Height. Each has Left and Right ("one
  droopy eyelid" = `{"Asymmetry Eyelids Upper Relax Left": 0.3}`; "ears with
  their own shape" = `{"Asymmetry Ears 02 Left": 0.5, "Asymmetry Ears 02
  Right": 0.5}`).
- Teeth (`Genesis 9 Mouth`) and irises and pupils (`Genesis 9 Eyes`) have
  their own dials; traits find them, and `dials` reaches them with `mouth:` /
  `eyes:` (and an anatomy geograft's with `anatomy:`). Never set "Mouth Width / Height / Depth / Size" on the Mouth figure
  by hand: they only follow head morphs and move the teeth, not the lips.

## 7. Keep the cast distinct

With few dials every face is a mix of the same heads, so a cast can look like
siblings.

1. Before creating, `character_list()` and `character_list(name=X)` for each
   cast member: compare blends and key traits.
2. Give each character a different dominant head blend and ratio; never reuse
   the same two top heads with weights within 0.1.
3. Make each differ from every other in at least 3 of: silhouette
   (`height_cm` by 8 cm or more, build), face shape, eye shape or tilt, nose,
   mouth, hair shape and color, iris color.
4. Give each one signature feature at 0.4-0.6, a different skin preset where
   possible, and a different one-sided asymmetry.
5. Line them all up and render one wide shot plus face close-ups with the same
   camera; if two are easy to confuse, push their signature traits apart.

## 8. Check it

- Test renders, not the viewport (it washes faces out): small size (800 x
  1000), `max_time` 20-30 s (`rendering`). Light: a soft spot near the camera.
- Shots: `camera_shot(subject, "close_up")` front; the same with `angle` 35-45
  (three-quarter); a profile (`angle` 90) for the nose, chin, brow, forehead,
  ears and deep-set eyes; teeth with `face_expression(figure, "big_smile")` or
  `"mouth_open"`, then `"neutral"` again; the whole body front and side for
  the silhouette. Hide hair (`node_set(visible=false)`) to check ears.
- Change at most 2-3 traits per `character_update`, and compare with the
  previous render.
- `eyes_size` on starter content scales only the eyeball: keep it at 0.3 or
  less and check that the lids do not cut into it. Check fangs with the mouth
  open: if the toon canines float or cut through the lip, lower them or use
  `teeth_taper` 0.6 + `teeth_length` 0.3.

## 9. Looks

**Skin depth and undertone.** Pick the skin preset by depth first
(`content_thumbnail` on G9 Feminine / Masculine Skin 01-04 MAT or a character's
Skin MAT; for deep or brown skin choose a dark preset, never darken a light one,
it looks grey). Then `skin.tone` near white for the undertone: warm or golden
`#f2e0c8`, pink or cool `#f2dcdc`, olive `#e6e2c6`, tan `#e8d0b4`.

**Skin details.** Freckles, moles, beauty marks, scars, tattoos, birthmarks,
vitiligo, makeup, blush, body hair are skin images, not dials:
`content_search(query="freckles" | "moles" | "scar" | "tattoo" | "makeup" |
"birthmark" | "vitiligo" | "body hair", kind="material", generation=...)`, put
them in `presets`, and write what the user asked in `skin.details`. If nothing
is installed, say so. Skin finish (oily, matte, weathered): `material_list`
on the figure, then lower or raise the glossy/specular roughness and the
detail strength on all skin surfaces in `materials`; judge it in a render.

**Fantasy skin** (orc, alien, demon): `skin.tone` the saturated color (orc
`#8fb070`, blue `#7a9ad8`, demon `#c05050`, ashen `#b0b0b0`), then in
`materials` set the translucency / subsurface colors that `material_list`
shows near the same hue, on all skin surfaces, or the red glow under the skin
turns blue skin purple. Render to check.

**Eyes.** `eyes.color` + `eyes.iris` (Genesis 9 iris images, see `faces`);
heterochromia: `eyes.left` / `eyes.right`, each `{color, iris}` (Genesis 9
only); `eyes.sclera` colors the whites (`#b02020` bloodshot or vampire,
`#202020` demon black, `#e8d8a0` jaundiced): it multiplies them, the iris keeps
its color. Glowing eyes: `materials` with Emission Color on the iris surface
(Genesis 8 "Irises"; on Genesis 9 the whole "Eye Left" / "Eye Right" glows,
so keep it low) and check in a render. Cat or reptile eyes: `pupils_slit` 1 +
`iris` 6 (gold) or a green color.

**Hair, eyebrows, facial hair.** `content_search(kind="hair", query=<word>,
generation=...)` with ponytail, braid, bun, bob, pixie, afro, curly,
dreadlocks, buzz cut, long; bald = no hair item. `hair`, `brows` and
`facial_hair` each take `items`, `color` (root) and `tip_color` (ombre, dyed
ends, grey tips). Genesis 9 eyebrows are items (Fiber looks best in
close-ups, Card renders faster); thick, thin, arched or straight brows come
from choosing another eyebrow item, not from dials, and their color is
separate from the hair (grey brows on dark hair). Genesis 8.1 eyebrows are
painted in the skin: change them with the skin preset. Beards: query "beard",
"mustache", "goatee", "stubble"; strand beards follow jaw and chin traits,
rigid prop beards may not: check a close-up. Iray Uber hair (a hair image)
only darkens with a color; use the hair's own color presets
(`content_search(kind="material", query=<hair name>)`) and load them on the
hair item, not on the figure.

**Areolas and nipples.** Their color and outline are painted in the skin
image: `areola_size` and `nipple_projection` change the shape only. For another
color or size of the painted areola use a skin preset or a nipple detail preset
(`content_search(query="nipples", kind="material", generation=...)`, e.g. the
Genesis 9 anime nipple presets), in `presets`.

**Teeth, gums, nails, lips.** `colors.teeth`, `colors.gums`, `colors.nails`
(polish on finger and toe nails), `colors.lips` (Genesis 8 / 8.1 Lips surface;
on Genesis 9 lips are part of the head: use a lipstick or makeup preset).

**Fantasy features and add-ons.** Horns, tail, wings, cat ears, tusks,
third eye: `content_search(query="horns" | "tail" | "wings" | "cat ears",
generation=...)`, put them in `extras` (worn like clothing, kept when the
outfit changes). Geografts merge with the skin: match their surfaces to the
skin in `materials`, or a seam shows. Elf ears and fangs on Genesis 9 starter
content: elf ears are missing (build on Genesis 8.1 Female, or search an
"elf" product); fangs use the toon canines (check them, above). Anything else
the user asks for that is not installed: record it in `notes` and say so.

## 9b. Anatomy geografts

Genitals are not part of the base mesh: Daz adds them as geografts, separate
figures that merge into the body (Genesis 9 Anatomical Elements; for
Genesis 8 / 8.1 Daz's or third-party products). They carry their own dials.

- `character_list(include_anatomy="Genesis 9")` lists the installed ones; if
  the list is empty, tell the user none is installed for that generation. Do
  not install products without the user's approval (`third-party-assets`).
- `anatomy=["auto"]` in `character_create` / `character_update` picks the
  installed one that matches the body (`feminine` / `masculine`, or the Female /
  Male figure); `anatomy=[path]` names one; `anatomy=[]` removes it. A note
  says when none is installed; the sheet keeps the request, so it applies after
  installing one and loading the character again.
- Their dials: `morph_list("<geograft label>")`, then `dials={"anatomy:<dial>":
  value}` in the sheet. Generated "MCP" dials follow onto the geograft like
  onto clothing.
- Geografts use the skin's materials: if a seam shows, match their surfaces to
  the skin preset or tone in `materials`.

## 10. Age without dials

When `age` and `wrinkles` come back missing: older = grey or white hair
(`hair.color` `#b8b4ae`, a darker `color` with a grey `tip_color` for salt and
pepper), a skin preset with aged texture if installed (query "aged",
"mature", "elderly"), `cheeks_fullness` -0.2, `eyelids_heavy` 0.3,
`mouth_corners` -0.15, `philtrum` 0.2 where installed, an older head blend if
there is one, a slight hunch in the pose. Youthful adult = `cheeks_fullness`
0.2, `eyes_size` 0.15, a smooth skin preset. Real wrinkles need morph packs or
aged skin textures: say so.

## 11. Genesis 9, 8.1 and 8

- Genesis 9 is one figure for every body: `feminine` / `masculine` choose it.
  Genesis 8 and 8.1 have separate Female and Male figures.
- Dial names differ between generations (Genesis 9 "Proportion Height" vs a
  Genesis 8 "Height"; teeth on the Mouth figure on Genesis 9, on the body on
  Genesis 8). Use traits, never copy dial names between generations; keep
  `dials` for the sheet's own generation.
- Iris images and one iris per eye exist on Genesis 9 only; on 8 / 8.1 only
  the color is used (a note says so).
- Clothing, hair and add-ons are for one generation: loading a sheet onto
  another generation brings Auto-Fit dialogs (`cross-generation-clothing`).
  The saved `.duf` preset is applied only to a figure of its own generation.

## 12. Using the character in scenes

- `character_load(name, position=[...])` in each scene. The figure's label is
  the name: use it in `face_expression`, `eyes_look_at`, `camera_shot`,
  `render_shots` (`dialogue-scenes`).
- The sheet holds the look, not the moment: expression, gaze, pose and place
  are set per scene after loading. A resting look that is part of the character
  (a permanent smirk) is a shape trait (`mouth_corners`), not an expression.
- After a sheet change, scenes saved earlier keep the old figure: reload it with
  `character_load(name, figure=<label>)`.

## 13. Editing a sheet by hand

The JSON can be edited in a text editor. Each trait goes in the bucket of its
category, `body` or `face` (`character_list(include_traits=true)` shows it):

```json
{
  "format": "daz3d-mcp-character", "version": 1,
  "name": "Ana", "description": "...", "notes": "assumed: 24 years old",
  "figure": {"generation": "Genesis 9", "base": "People/Genesis 9/Genesis 9.duf", "character": null},
  "body": {"feminine": 1, "muscle": 0.3},
  "face": {"lips_fullness": 0.6, "eyes_tilt": 0.4, "teeth_gap": 0.5, "asymmetry": 0.6},
  "height_cm": 165, "dials": {"Laura Head": 0.3, "mouth:Teeth Size Lower": 0.2},
  "skin": {"preset": "People/Genesis 9/Materials/...", "tone": "#f2e0c8", "details": "freckles on the nose"},
  "eyes": {"color": "#3f8f4a", "iris": 15, "left": null, "right": null, "sclera": null},
  "hair": {"items": ["People/Genesis 9/Hair/..."], "color": "#2a1a12", "tip_color": null},
  "brows": {"items": [], "color": null, "tip_color": null},
  "facial_hair": {"items": [], "color": null, "tip_color": null},
  "colors": {"teeth": null, "gums": null, "nails": "#802030", "lips": null},
  "anatomy": [], "clothing": ["People/Genesis 9/Clothing/..."], "extras": [], "presets": [],
  "materials": [{"on": "figure", "surfaces": ["Head"], "properties": {"Glossy Roughness": 0.5}}]
}
```

`applied` (written by the tools) records which dials were really set, what was
missing and which scene items came from which file. After hand edits, put the
character in the scene (`character_load`) and call
`character_update(name, refresh=true)`: it applies the whole sheet and saves a
new `.duf` preset. Until then `character_load` leaves the old preset out
(`preset_skipped`) and builds the character from the sheet alone. Check that
the result has no `unknown_traits` (typos are skipped).
