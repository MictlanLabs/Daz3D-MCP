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

## Dialogs (bridge 0.2+, `"features": ["dialogs"]` in status)

Some Daz calls ask the user with a modal dialog and the script waits until a
button is pressed. The dialog runs its own event loop, so the bridge keeps
answering `/v1/status` and the two calls below while `/v1/execute` waits.

`POST /v1/execute` may carry rules answered without the agent:

```json
{"code": "...", "args": "{}", "dialogs": [{"match": "already exists", "button": "Yes", "check": ["Don't ask again"]}]}
```

`match` is a case-insensitive regex over the dialog's title and text. Dialogs
already open when the request starts are never answered by rule. Dialogs seen
during the request are added to its response:
`"dialogs": [{"id", "title", "text", "buttons", "options", "answered", "answered_by": "rule" | "agent"}]`.

`GET /v1/dialogs` lists open modal windows (the active one first):

```json
{"ok": true, "result": {"busy": true, "dialogs": [{"id": "1f2e3d4c", "title": "File Already Exists",
  "class": "QMessageBox", "text": "The file ... Do you want to overwrite it?", "buttons": ["Yes", "No"],
  "options": [{"label": "Don't ask again", "kind": "checkbox", "checked": false}]}], "seen": []}}
```

Progress windows have `"progress": true` and need no answer.

`POST /v1/dialogs/answer` with `{"button": "Yes", "check": [...], "uncheck": [...], "id": "optional"}`
sets the options, then presses the button (case and `&` ignored; a unique
prefix also works; `"escape"` rejects the dialog). The press happens after the
answer is sent. Errors: `404 no_dialog`, `400 no_button` / `no_option` (the
message lists what exists).

The MCP polls `/v1/dialogs` while a request runs. A dialog open for more than
a second makes the tool fail with `dialog_open`; the request stays pending and
`daz_dialog` answers it and returns its result.

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
