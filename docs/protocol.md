# Bridge protocol (version 1)

The bridge plugin and the MCP server talk HTTP/1.1 over `127.0.0.1`. One
request per connection.

## Discovery

When the plugin starts it writes, in `~/.daz3d-mcp/` (or `$DAZ3D_MCP_HOME`),
with permissions `0600`:

- `token`: 64 hex characters, created once and reused.
- `bridge.json`: `{"port": 18640, "protocol": 1, "bridge_version": "0.1.0", "daz_version": "6.25...", "pid": 1234}`.

It deletes `bridge.json` when Daz Studio quits normally.

## Every request

- `Host` must be `127.0.0.1` or `localhost` (blocks DNS rebinding).
- No `Origin` header (blocks web pages).
- `Authorization: Bearer <token>`.

Otherwise the answer is `403` or `401`. Errors always have this body:

```json
{"ok": false, "error": {"code": "unauthorized", "message": "..."}}
```

## `GET /v1/status`

```json
{"ok": true, "protocol": 1, "bridge_version": "0.1.0", "daz_version": "6.25...", "busy": false}
```

## `POST /v1/execute`

Request body:

```json
{"code": "<DazScript program>", "entry": "dazmcp_entry", "args": "<JSON string>"}
```

The plugin runs `code`, calls the function `entry` with `args` (a string) as
its only argument, and returns that function's return value as the response
body. The library's `dazmcp_entry` always returns:

```json
{"ok": true, "result": <any>, "log": ["optional messages"]}
{"ok": false, "error": {"code": "unsaved_changes", "message": "...", "details": null, "line": null}}
```

If the script does not compile or throws outside `dazmcp_entry`, the plugin
answers `{"ok": false, "error": {"code": "script_error", "message": "...", "line": 12}}`.

While a request runs, another one gets `409` with code `busy`. Bodies are
limited to 64 MB.

## Programs

The MCP server builds each program as `scripts/lib/core.dsa` + one
`scripts/tools/<tool>.dsa` (which defines `dazmcpTool(args)`) +
`scripts/lib/entry.dsa`. `run_script` puts the agent's code in place of the
tool script. Programs are plain ES5 so they run on Daz Studio 4.x and 6.

## No-plugin mode

Instead of HTTP, the MCP writes the program plus a few lines that save the
result to `~/.daz3d-mcp/queue/<id>.json`, then runs
`<Daz Studio executable> <id>.dsa`. Daz Studio passes the file to the instance
already running, which executes it.
