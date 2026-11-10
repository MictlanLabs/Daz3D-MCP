# Stage 1 closing test

Goal: from **Claude Code** and from **Cursor**, an agent opens a scene,
describes it and returns a viewport capture, on a real Daz Studio 6.

## 1. Prepare (once)

1. Install Daz Studio 6 and the Daz Studio 6 SDK, plus Qt 6.10 and the Xcode
   command line tools (`xcode-select --install`).
2. Build the bridge (see [bridge/README.md](../bridge/README.md)).
3. Install everything:

   ```bash
   uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp setup --plugin-file build/bridge/dazmcp_bridge.dylib
   uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --client claude-code --client cursor
   ```

4. Open Daz Studio, load any scene with a figure and save it, for example as
   `~/Documents/Daz3D-MCP/test-scene.duf`. Then start a new empty scene.
5. `uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp doctor` must end with `All good.`

If the plugin does not build yet, use `setup --no-plugin` and record that in
the results.

## 2. Run in each agent

Restart the agent, then send:

> Open ~/Documents/Daz3D-MCP/test-scene.duf in Daz Studio, describe what is in
> the scene and show me a capture of the viewport.

## 3. Pass criteria

| Check | Claude Code | Cursor |
| --- | --- | --- |
| The agent calls `scene_open` and the scene appears in Daz | | |
| The description names the figures, clothing, props and lights that are really there | | |
| The agent returns an image of the viewport | | |
| The image matches what Daz shows | | |
| No dialog blocked Daz Studio | | |

Also note: Daz Studio version, macOS version, Mac chip, transport (plugin or
no-plugin), capture method reported by `viewport_capture`
(`captureImage` or `saveThumbnailImage`), and anything that failed.
