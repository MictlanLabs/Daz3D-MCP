# Stage 2 closing test

Goal: an agent builds a scene with **two dressed and posed characters** and
**renders it**, on a real Daz Studio 6.

Stage 2 passes its closing test in simulation
(`tests/test_stage2_closing.py`, against `tests/fake_daz`). The simulation
follows the public DazScript API reference, but it is not Daz Studio: the
checks below are what only a real Daz Studio can confirm.

## 1. Prepare

1. Do the stage 1 preparation first ([stage1-closing-test.md](stage1-closing-test.md)).
   Stage 1 must pass before this test means anything.
2. Install free Genesis 9 content from Daz Central / Install Manager, which
   comes with Daz Studio: **Genesis 9 Starter Essentials** has the base figure,
   basic clothing, hair and poses. Check in Daz that you can load the figure,
   a top, pants, shoes, hair and a pose by hand.
3. Restart the agent so it picks up the new tools and skills
   (`uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --client claude-code`
   updates the skills).
4. Start Daz Studio with an empty scene.

## 2. Run in the agent

> In Daz Studio, build a scene with two Genesis 9 characters, a woman and a
> man, standing and talking to each other. Dress both completely (top,
> bottom, shoes and hair), give each a different pose, add a camera that
> frames both and studio lighting, then render it at 1280x720 with at most
> 3 minutes of render time and show me the image.

## 3. Pass criteria

| Check | Result |
| --- | --- |
| `content_search` finds the installed figure, clothing, hair and poses | |
| Two figures are in the scene with clear labels | |
| Each figure wears top, bottom, shoes and hair, and they are fitted (they follow the pose) | |
| Each figure has a different pose, and the agent fine-tuned at least one bone | |
| The camera frames both figures fully | |
| There are lights and the render is not black | |
| `render` returns the image and the file exists | |
| No dialog blocked Daz Studio | |

Also note: time spent per step, render time, `render` result (`seconds`,
`settings`), and anything that failed or that the agent had to do with
`run_script`.

## 4. What only a real Daz Studio can confirm

These are the API calls stage 2 relies on and the simulation only assumes.
If one fails, note the error message; most have a fallback in the scripts.

| Area | Assumption | Where |
| --- | --- | --- |
| Content | `App.getContentMgr().getNumContentDirectories()` / `getContentDirectoryPath(i)` list the libraries | `content_libraries.dsa` |
| Content | `ContentMgr.openFile(path, true)` merges the file and applies presets to the selected node; clothing loaded with a figure selected is auto-fitted | `content_load.dsa` |
| Content | `.duf` headers carry `asset_info.type` (`figure`, `wearable`, `preset_pose`...) | `content.py` |
| Content | Missing-file or "fit to" dialogs do not appear for matching-generation content | `content_load.dsa` |
| Nodes | `DzLight` inherits `DzCamera` (lights are checked first) | `core.dsa` `nodeType` |
| Nodes | `Scene.selectAllNodes`, `setPrimarySelection`, `removeNode`, `node.select`, `setVisible` | several |
| Figures | `getNumBones`/`getBone`, `findBone`, `getFollowTarget`, `setFollowTarget` | `core.dsa`, `wearable_fit.dsa` |
| Morphs | Shape dials are `DzMorph` modifiers with `getValueControl()`; `getPath()` is the group | `core.dsa` `morphList` |
| Poses | Bone rotation axes and signs described in the `characters` skill | `skills/characters` |
| Cameras | `new DzBasicCamera()`, "Focal Length" property, 36 mm frame width, cameras look down -Z with Y-then-X rotation | `core.dsa` `framePosition`, `aimRotation` |
| Lights | `new DzSpotLight()` etc.; Iray power is "Luminous Flux (Lumen)" (spot/point) or "Intensity" (distant); "Illumination" enum switches off | `core.dsa` `lightApply` |
| Environment | "Environment Mode", "Environment Intensity", "Environment Map", "Dome Rotation", "Draw Dome" on the render elements or the Environment Options node | `environment_set.dsa` |
| Materials | `getObject().getCurrentShape().getMaterial(i)`; `DzColorProperty.setColorValue(Color)`; `setMap(App.getImageMgr().getImage(path))` | `core.dsa` |
| Render | `RenderMgr.getRenderOptions()`, `setRenderImgToId(DzRenderOptions.DirectToFile)`, `setRenderImgFilename`, `setImageSize(Size)`; `doRender(opts)` blocks until Iray finishes; it renders through the viewport's active camera | `render.dsa` |
| Render | Iray settings "Max Samples", "Max Time (secs)", "Rendering Quality" on `getRenderElementObjects()` | `core.dsa` `applyRenderSettings` |
| Render | `new Image(path)` loads the render for the preview (if not, the full image is sent when under 8 MB) | `render.dsa` |
| Agents | The agent's own tool timeout allows a render of a few minutes (Claude Code and Cursor have per-tool limits) | `render` |
