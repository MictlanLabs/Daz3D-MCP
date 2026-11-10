# Daz3D-MCP

Let AI agents (Claude Code, Codex, Cursor, Antigravity, Gemini CLI, Claude
Desktop, VS Code and any other MCP client) control **Daz Studio**: open and
save scenes, find installed content, build characters (shape, clothing, hair,
poses), set up cameras, lights and materials, render with Iray, and run DazScript.

> Independent open source project. Not affiliated with or endorsed by Daz 3D.
> [Leer en español](README.es.md)

**Status: v0.2 (stage 2 of 4).** Scenes, content library, characters, cameras,
lights, materials and rendering work. Third-party assets and animation come in
the next stages. Stages 1 and 2 are tested against a simulated Daz Studio;
their closing tests on a real Daz Studio 6 are still pending.

## How it works

```
AI agent ──MCP (stdio)──> daz3d-mcp (Python) ──HTTP 127.0.0.1 + token──> bridge plugin ──> DazScript in Daz Studio
```

- **Bridge plugin** (`bridge/`, C++): a tiny server inside Daz Studio. It only
  listens on `127.0.0.1`, needs a token and runs DazScript on the main thread.
- **DazScript library** (`scripts/`): one script per tool; it does the real work.
- **MCP server** (`src/daz3d_mcp/`, Python): the tools agents call.
- **Skills** (`skills/`): `SKILL.md` guides that teach agents how to use Daz.
  Agents without skills support get the same text through the MCP
  (`daz_guide` tool, prompts and resources).

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Daz Studio 6 (4.24 support comes later).

```bash
uvx daz3d-mcp setup           # copies the bridge plugin into Daz Studio
uvx daz3d-mcp install --all   # registers the MCP and skills in every agent found
uvx daz3d-mcp doctor          # checks everything and says what to fix
```

Restart Daz Studio and your agents afterwards.

Until the first PyPI release, run the same commands from GitHub:

```bash
uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --all
```

`install` writes the agents' config so they run that same source.

**One agent only:** `uvx daz3d-mcp install --client cursor` (also
`claude-code`, `codex`, `antigravity`, `gemini-cli`, `claude-desktop`,
`windsurf`, `vscode`). `uvx daz3d-mcp uninstall` removes everything it added.

**Any other MCP client:** add this server to its settings:

```json
{ "mcpServers": { "daz3d": { "command": "uvx", "args": ["daz3d-mcp"] } } }
```

**No compiled plugin yet?** `uvx daz3d-mcp setup --no-plugin` uses an
experimental mode that asks the running Daz Studio to execute script files.
It is slower but needs nothing compiled.

## Tools

| Tool | What it does |
| --- | --- |
| `daz_status` | Checks the connection; Daz version and open scene |
| `scene_info` | Figures, clothing, props, cameras and lights with position, rotation, size |
| `scene_new` | Clears the scene (refuses to lose unsaved work unless told) |
| `scene_open` | Opens or merges a `.duf` scene |
| `scene_save` | Saves as `.duf` (never overwrites another file unless told) |
| `viewport_capture` | Returns a PNG of the viewport, optionally from a camera or frame |
| `content_libraries` | Lists the content libraries and how many files the index holds |
| `content_search` | Finds installed figures, characters, clothing, hair, poses, materials, props, lights |
| `content_thumbnail` | Shows a content file's thumbnail |
| `content_load` | Loads content; fits clothing and hair, applies poses, characters and materials to a target |
| `node_set` | Moves, rotates, scales, shows/hides, renames or selects a node |
| `node_delete` | Deletes nodes (and what is fitted to a figure) |
| `figure_info` | A figure's generation, height, clothing, morphs in use, posed bones and surfaces |
| `morph_list` / `morph_set` | Finds and sets shape dials |
| `pose_bones` / `pose_reset` | Rotates bones / back to the default pose |
| `wearable_fit` | Fits clothing or hair to a figure, or unfits it |
| `camera_create` / `camera_set` | Adds or changes a camera; can frame nodes automatically |
| `light_create` / `light_set` | Adds or changes spot, point and distant lights |
| `environment_set` | Iray dome, HDRI and sun-sky |
| `material_list` / `material_set` | Reads and changes surfaces (colors, roughness, texture maps) |
| `render_settings` | Image size and Iray limits |
| `render` | Renders to a file and returns the image |
| `run_script` | Runs DazScript for anything else (can be disabled) |
| `daz_guide` | Returns the skills as text for agents without skills support |

Skills: `daz-basics`, `scene-building`, `characters`, `rendering`.

Try it: *"Open ~/Documents/scene.duf in Daz, describe the scene and show me a capture."*
Or: *"Build a scene with two Genesis 9 characters, dressed and posed, talking
to each other, and render it."*

Content search runs in the MCP server on an index of the library files
(`~/.daz3d-mcp/content-index.json`, rebuilt every 24 hours or with
`refresh_index=true`), so Daz Studio is never frozen by a search.

## Settings

`~/.daz3d-mcp/settings.json` (created by `setup`):

| Key | Default | Meaning |
| --- | --- | --- |
| `allow_run_script` | `true` | Allow the free-form `run_script` tool |
| `transport` | `"auto"` | `auto`, `http` (plugin only) or `file` (no-plugin mode) |
| `daz_executable` | detected | Daz Studio binary, for no-plugin mode |
| `timeout` | `600` | Seconds to wait for one request |
| `render_timeout` | `3600` | Seconds to wait for one render |
| `render_dir` | `~/.daz3d-mcp/renders` | Where renders go when no path is given |
| `content_libraries` | `[]` | Extra library folders to search |
| `content_index_max_age_hours` | `24` | When to rebuild the content index |

## Security

The bridge listens on `127.0.0.1` only, requires the random token stored in
`~/.daz3d-mcp/token` (readable only by you) and rejects browser requests.
`run_script` gives an agent the same power as a DazScript you run yourself;
set `allow_run_script` to `false` if you do not want that.

## Development

```bash
uv run --group dev pytest            # Python + DazScript tests (Node.js runs the scripts against a fake Daz)
npm install --prefix tests/fake_daz  # once, for the ES5 syntax checks
```

Building the bridge: see [bridge/README.md](bridge/README.md).
The bridge protocol is documented in [docs/protocol.md](docs/protocol.md).

## License

Apache 2.0. See [LICENSE](LICENSE). The Daz Studio SDK is not included.
