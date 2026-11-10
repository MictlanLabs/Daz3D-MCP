---
name: third-party-assets
description: How to bring content from outside the Daz store into Daz Studio with the daz3d MCP tools - install .zip packages from Renderosity, RuntimeDNA, CGBytes or free sites, import loose OBJ and FBX models, turn imported garments into clothing that follows a figure, and attach props to hands or heads. Use when the user has a downloaded zip, an .obj or .fbx, or a model from Sketchfab, CGTrader or Blender.
---

# Third-party assets in Daz Studio

Read `daz-basics` and `scene-building` first. Content bought in the Daz store
is installed by Daz Install Manager or Daz Central; everything else comes as a
file the user downloaded. There are two kinds:

- **A Daz content package** (.zip with `data`, `People`, `Props`, `Runtime`...
  folders somewhere inside): install it with `package_install`, then use it
  like any installed content (`content_search`, `content_load`).
- **A 3D model** (.obj, .fbx, or a zip with only those): import it with
  `import_mesh`. A garment modeled for a figure then needs
  `wearable_from_mesh` to follow that figure.

Only use files the user gave you or that are on their disk. Ask for the path
when they say "the zip I downloaded"; look in `~/Downloads` only after asking.

## Installing a package (.zip)

```text
package_inspect(path="/Users/me/Downloads/LeatherJacket_G9.zip")
   -> layout, content_root, loadable files, meshes, warnings
package_install(path=...)            -> items (paths for content_load), meshes
content_load(path=items[0].path, target="Ana")
```

- Always `package_inspect` first and tell the user what is inside if it is not
  what they expect (wrong generation, only textures, Poser-only content,
  warnings).
- `layout`:
  - `daz`: Daz Studio content. Load the `items` as usual.
  - `poser`: Poser format (`Runtime/libraries`, .pz2/.cr2). It loads in Daz,
    but materials are older; prefer a Daz version when one exists.
  - `meshes`: no Daz content, only models. They are unpacked aside; use
    `import_mesh` on the paths in `meshes`.
- By default packages go into **Third Party Library**
  (`~/Documents/DAZ 3D/Third Party Library`), which is added to Daz's content
  libraries automatically. Pass `library=` only if the user wants another one.
- Files from another package with the same path but different contents are
  never replaced silently: the install stops and lists them. Ask before
  `overwrite=true`.
- Content often needs a base product (for example a character that needs the
  Genesis 9 Starter Essentials, or a texture add-on that needs the original
  outfit). The readme in `extras` usually says so. If a load reports missing
  files, tell the user which product is probably missing.
- Only .zip and folders are read. Ask the user to unpack .rar or .7z files
  (double click in Finder) and pass the folder.
- `package_list` shows what was installed; `package_uninstall` removes exactly
  those files. Ask first.
- A folder that already holds content (an old library, an external drive):
  `content_add_library(path)`.

## Importing an OBJ or FBX

```text
mesh_inspect(path)        -> size in file units, suggested_units, surfaces, textures, rigged
import_mesh(path, label="Tavern Table", drop_to_floor=true, position=[120, 0, 0])
viewport_capture()
```

- Daz works in centimeters. OBJ files have no units: `units="auto"` guesses
  from the size (a 1.8-unit-tall person is in meters). FBX stores its units
  and the importer converts them. If `import_mesh` warns that the size is
  wrong, or the model is clearly too big or small in the capture, import again
  with `units=` (`m`, `cm`, `mm`, `in`, `ft`) or `height=` in cm.
- Model downloads from Blender or 3ds Max may be Z-up: if an OBJ imports lying
  down, delete it and import with `up_axis="Z"`.
- `drop_to_floor=true` for props and furniture. **Never** for clothing modeled
  around a figure: its height is what lines it up with the body.
- `missing_textures` means the model will look grey or wrong. Tell the user;
  textures must sit where the .mtl / .fbx says (usually next to it).
- Daz only imports .obj and .fbx. For .glb, .gltf, .blend, .dae or .stl ask
  the user to convert (Blender: File > Export > FBX).
- A **rigged FBX** (it has its own skeleton) imports as a figure with its own
  bones. It is not a Genesis figure: Genesis poses, morphs and clothing do not
  apply to it.

## Making an imported garment follow a figure

Clothing, hats, armor or hair modeled around a Genesis figure (exported from
Daz, made in Blender or Marvelous Designer over a Genesis base) become real
clothing with the Transfer Utility:

```text
pose_reset(figure="Ana")                        # if she is posed
import_mesh(path="/Users/me/Downloads/Hero Cape.fbx", label="Cape")
viewport_capture()                              # the cape must sit on her body
wearable_from_mesh(item="Cape", figure="Ana")   -> fitted_to: "Ana"
content_load(pose, target="Ana")                # pose again: the cape follows
```

- The mesh must line up with the figure **in its default pose and shape**,
  at the same place (usually the figure at the origin, no rotation). If the
  figure was moved, move it back to [0, 0, 0] first, convert, then move it.
  `wearable_from_mesh` refuses meshes that do not touch the figure, and
  posed figures (`figure_posed`): reset the pose, convert, pose again.
- `shape="current"` when the garment was made around a character's shape
  (a character preset or morphs dialed in) instead of the base figure.
- `kind="hair"` for hair, so Daz files it as hair.
- It also re-rigs clothing made for another generation that `content_load`
  could not fit: `wearable_from_mesh(item="Old Jacket", figure="Ana")`.
- Results depend on the mesh. Always check from two angles
  (`camera_set(yaw=...)`) after posing.

## Fixing poke-through and fit

- `wearable_adjust(item, collision_iterations=4)`: more collision pushes the
  cloth out of the skin. Items made with `wearable_from_mesh` have mesh
  smoothing and collision with their figure; `wearable_adjust(item)` alone
  reports the values.
- `smoothing_iterations` (2-6) smooths jagged folds.
- Many store outfits have fit dials: `morph_list(node=item, query="loose")`
  then `morph_set`.
- Last resort: hide the body under it with `material_set(node=figure,
  surfaces=[...], properties={"Cutout Opacity": 0})` only if the user agrees.

## Props in a hand or on a head

A sword, phone, cup or hat that is not clothing is a prop attached to a bone:

```text
import_mesh(path=".../Sword.obj", label="Sword")
node_set(node="Sword", position=[...], rotation=[...])   # put it in the hand
node_set(node="Sword", parent="Ana", parent_bone="r_hand")
```

It keeps its place when attached and moves with the bone after that.
`parent=""` detaches it. Genesis 9 bones: `r_hand`, `l_hand`, `head`; Genesis
8: `rHand`, `lHand`, `head`.

## What to tell the user

- What the package or model contains, where it was installed, and what you
  loaded.
- Anything that looks off in the capture (scale, missing textures, poke-through)
  and what you did about it.
- Third-party content keeps its own license; do not redistribute it.
