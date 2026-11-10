# Daz3D-MCP

Let AI agents (Claude Code, Codex, Cursor, Antigravity, Gemini CLI, Claude
Desktop, VS Code and any other MCP client) control **Daz Studio**: open and
save scenes, describe what is in them, look at the viewport and run DazScript.

> Independent open source project. Not affiliated with or endorsed by Daz 3D.
> [Leer en español](README.es.md)

**Status: v0.1 (stage 1 of 4).** Scenes, viewport capture and scripting work.
Characters, content loading, third-party assets and animation come in the next
stages.

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
| `run_script` | Runs DazScript for anything else (can be disabled) |
| `daz_guide` | Returns the skills as text for agents without skills support |

Try it: *"Open ~/Documents/scene.duf in Daz, describe the scene and show me a capture."*

## Settings

`~/.daz3d-mcp/settings.json` (created by `setup`):

| Key | Default | Meaning |
| --- | --- | --- |
| `allow_run_script` | `true` | Allow the free-form `run_script` tool |
| `transport` | `"auto"` | `auto`, `http` (plugin only) or `file` (no-plugin mode) |
| `daz_executable` | detected | Daz Studio binary, for no-plugin mode |
| `timeout` | `600` | Seconds to wait for one request |

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
