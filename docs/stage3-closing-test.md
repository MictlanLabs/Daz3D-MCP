# Stage 3 closing test

Goal: an agent uses, **in one scene**, a **package from another store (.zip)**
and a **loose FBX**, on a real Daz Studio 6.

Stage 3 passes its closing test in simulation
(`tests/test_stage3_closing.py`, against `tests/fake_daz`). The simulation
follows the public DazScript API reference (DzContentMgr, DzImportMgr,
DzFileIOSettings, DzTransferUtility and the Daz samples "Silent OBJ Import"
and "Silent FBX Import"), but it is not Daz Studio: the checks below are what
only a real Daz Studio can confirm.

## 1. Prepare

1. Stages 1 and 2 must pass first ([stage1-closing-test.md](stage1-closing-test.md),
   [stage2-closing-test.md](stage2-closing-test.md)), with Genesis 9 Starter
   Essentials installed.
2. Download, into `~/Downloads`:
   - **A .zip from another store** made for Genesis 9: a free outfit or
     accessory from Renderosity (free stuff section) or ShareCG. Prefer one
     whose zip has a wrapper folder or a `Content` folder inside, which is the
     case the tool is for.
   - **A loose FBX** of clothing or an accessory you can wear, for example a
     cape or a hat. The easiest reliable source is Daz itself: load Genesis 9,
     load a hat or a simple top, select only that item and use
     *File > Export* to FBX, then delete it from the scene. That FBX lines up
     with Genesis 9 exactly. A free model from Sketchfab also works but may
     need moving and scaling first.
   - Optional: any free OBJ prop (a chair or a sword).
3. Update the agent (`uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --client claude-code`)
   and restart it so it picks up the new tools and the `third-party-assets` skill.
4. Start Daz Studio with an empty scene.

## 2. Run in the agent

> In Daz Studio, load a Genesis 9 figure called Ana. Install the zip
> ~/Downloads/<package>.zip and dress Ana with what it contains. Then import
> ~/Downloads/<model>.fbx, make it clothing that follows Ana, give her a pose,
> frame her with a camera and render a 1280x720 test with at most 2 minutes
> of render time.

Optional second prompt: *"Import ~/Downloads/<prop>.obj, put it on the floor
next to Ana"* (or *"in her right hand"*).

## 3. Pass criteria

| Check | Result |
| --- | --- |
| `package_inspect` finds the right content root and lists the loadable files | |
| `package_install` copies only the content (no promo images, no `__MACOSX`) into Third Party Library | |
| Daz Studio shows Third Party Library in *Content Library* and keeps it after a restart | |
| The package's item loads on Ana and is fitted (no missing-file dialog) | |
| `import_mesh` brings the FBX in at the right size, with no dialog | |
| `wearable_from_mesh` turns it into clothing fitted to Ana | |
| After posing Ana, both items follow the pose | |
| The render shows both items on Ana | |
| No dialog blocked Daz Studio | |

Also note: what `package_inspect` reported, the import size and units,
anything the agent had to do with `run_script`, and how the converted
garment looks (poke-through, stretching).

## 4. What only a real Daz Studio can confirm

| Area | Assumption | Where |
| --- | --- | --- |
| Libraries | `ContentMgr.addContentDirectory(path, true)` adds and saves a library; `addPoserDirectory` for Poser format | `content_add_library.dsa` |
| Libraries | A .duf in Third Party Library finds its `data/` files once the library is mapped | `package_install` |
| Import | `ImportMgr.findImporterByClassName("DzObjImporter" / "DzFbxImporter")`, `getDefaultOptions`, `readFile(path, settings)` returns a DzError (0 = ok) | `import_mesh.dsa` |
| Import | OBJ settings `Preset`, `Scale` (cm per unit; "Custom" preset keeps it), `LatAxis`/`VertAxis`/`DepthAxis`, `InvertDepth`, `IncludeVT`/`IncludeG`/`IncludeUsemtl`/`IncludeMtllib`; `RunSilent = 1` shows no dialog | `import_mesh.dsa` |
| Import | The FBX importer converts the file's unit (`UnitScaleFactor`) to centimeters by itself, and shows no dialog with `RunSilent = 1` | `import_mesh.dsa`, `meshes.py` |
| Import | A Z-up OBJ is fixed with `VertAxis = Z`, `DepthAxis = Y`, `InvertDepth = true` | `import_mesh.dsa` |
| Import | A rigged FBX imports as a `DzFigure` with its own bones | `import_mesh.dsa` |
| Transfer | `new DzTransferUtility()`, `setSource(figure)`, `setTarget(node)`, `setTransferBinding`, `setTransferMorphs`, `setTransferSourceMorphs(DzTransferUtility.ShapingAndPoseType)`, `setFitToFigure`, `setParentToFigure`, `setRemoveOriginalTarget`, `setAddSmoothModifier`, `setContentType("Follower/Wardrobe")`, `doTransfer()`, `getTargetOutputFigure()` | `wearable_from_mesh.dsa` |
| Transfer | The projection works on world positions, so the mesh must sit on the unposed figure | `wearable_from_mesh.dsa` |
| Transfer | `setSilentImporters(true)` keeps it from opening dialogs | `wearable_from_mesh.dsa` |
| Fit | Mesh smoothing properties are labeled "Enable Smoothing", "Smoothing Iterations", "Collision Item", "Collision Iterations" and live on the node, its object or a modifier | `wearable_adjust.dsa` |
| Parenting | `addNodeChild(child, true)` / `removeNodeChild(child, true)` keep the world position | `node_set.dsa` |
| Packages | Real store zips: names with accents, cp437 names from Windows zip tools, very large packages (the 20 GB limit) | `packages.py` |
