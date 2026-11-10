# Bridge plugin

A small Daz Studio plugin that starts a local HTTP server when Daz Studio
opens. The MCP server sends it DazScript programs; the plugin runs them on the
main thread and returns their JSON result. Protocol: [../docs/protocol.md](../docs/protocol.md).

It does nothing else on purpose: every feature lives in the DazScript library
(`../scripts`), so most fixes never need a new build.

## Build for Daz Studio 6

Requirements:

- Daz Studio 6 (Pro beta or later) installed.
- The [Daz Studio 6 SDK](https://www.daz3d.com/daz-studio-6-sdk) (free, installed
  with DazCentral, DIM or by hand).
- Qt 6.10 for your platform (the Qt version Daz Studio 6 uses), from the
  [Qt online installer](https://www.qt.io/download-qt-installer-oss).
- CMake 3.21+ and a compiler: Xcode command line tools on macOS, Visual Studio
  2022 on Windows.

```bash
cmake -S bridge -B build/bridge \
  -DDAZ_SDK_DIR="/path/to/DAZStudio6 SDK" \
  -DCMAKE_PREFIX_PATH="/path/to/Qt/6.10.x/macos"   # Windows: .../msvc2022_64
cmake --build build/bridge --config Release
```

On macOS build for the same architecture as Daz Studio (check with
`file "/Applications/DAZ 3D/<Daz folder>/DAZStudio.app/Contents/MacOS/DAZStudio"`);
add `-DCMAKE_OSX_ARCHITECTURES=arm64` or `x86_64` if needed.

Install it:

```bash
uvx daz3d-mcp setup --plugin-file build/bridge/dazmcp_bridge.dylib   # or .dll on Windows
```

Then restart Daz Studio. The log (Help > Troubleshooting > View Log File)
should show `Daz3D-MCP bridge 0.1.0 listening on 127.0.0.1:18640`, and
`uvx daz3d-mcp doctor` should report that Daz Studio answers.

## First build checklist

The plugin was written against the public SDK API and its Qt side is compiled
and tested in CI against a stub of the SDK (`tests/sdk_stub`). The Daz-specific
parts still need confirming on the first build with the real Daz Studio 6 SDK:

1. `DZ_PLUGIN_DEFINITION`, `DZ_PLUGIN_CLASS_GUID` and the other macros in `src/plugin.cpp`.
2. The `DzAction(text, description)` constructor and `executeAction()`.
3. `DzScript::setCode`, `call`, `result`, `errorMessage` and `errorLine`.
4. That Daz Studio ships the `QtNetwork` library the plugin links to.
5. That the static initializer in `plugin.cpp` starts the server (otherwise use
   the "Restart Daz3D-MCP Bridge" action, or move the start into a `DzPlugin`
   subclass's `startup()`).

Report the result in an issue so the next person does not have to repeat it.

## Settings

- `DAZ3D_MCP_PORT`: first port to try (default 18640; tries the next 9 if busy).
- `DAZ3D_MCP_HOME`: folder for `token` and `bridge.json` (default `~/.daz3d-mcp`).

## Daz Studio 4.24

Daz Studio 4.x uses Qt 4.8, which has no `QJsonDocument`, `QSaveFile` or
`QRandomGenerator`. A 4.x build needs small replacements for those and is
planned after stage 4; until then 4.24 users can try no-plugin mode
(`uvx daz3d-mcp setup --no-plugin`).
