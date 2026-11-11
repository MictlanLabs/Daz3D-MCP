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
uvx daz3d-mcp setup --plugin-file build/bridge/dazmcp_bridge.dylib   # Windows: build/bridge/Release/dsp_dazmcp_bridge.dll
```

Then restart Daz Studio. The log (Help > Troubleshooting > View Log File)
should show `Daz3D-MCP bridge 0.1.0 listening on 127.0.0.1:18640`, and
`uvx daz3d-mcp doctor` should report that Daz Studio answers.

## Confirmed on Daz Studio 6.26 (Windows, SDK 6.26.2026.27900 beta)

First real build: Visual Studio Build Tools 2026, CMake 4.4, Qt 6.10.3
`msvc2022_64`, generator `-G "Visual Studio 18 2026" -A x64`. What the real
SDK needed:

1. On Windows Daz only loads plugins named `dsp_*.dll`; the build names it
   `dsp_dazmcp_bridge.dll`.
2. The SDK macros export C++ (mangled) names, but Daz looks up
   `getSDKVersion` and `getPluginDefinition` by plain name, so
   `src/dazmcp_bridge.def` exports them.
3. `DZ_PLUGIN_CLASS_GUID(Class, XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)` takes the
   GUID as one token, and the version macros need `dzversion.h`.
4. `DzScript` is reference counted (protected destructor): use `new`, `ref()`
   and `unref()`.
5. `DzScript::call()` is declared but not exported by `dzcore`. The bridge uses
   `execute(args)` and appends `return <entry>(getArguments()[0]);`:
   `result()` is the value of a top-level `return` (a last bare expression
   gives `undefined`). `result()` is a `QJSValue`, so the plugin links Qt6::Qml.
6. The SDK lives in `x64/lib/dzcore.lib` under the SDK folder.

The static initializer in `plugin.cpp` starts the server, and the plugin shows
as loaded in the log. macOS is still unconfirmed.

## Settings

- `DAZ3D_MCP_PORT`: first port to try (default 18640; tries the next 9 if busy).
- `DAZ3D_MCP_HOME`: folder for `token` and `bridge.json` (default `~/.daz3d-mcp`).

## Daz Studio 4.24

Daz Studio 4.x uses Qt 4.8, which has no `QJsonDocument`, `QSaveFile` or
`QRandomGenerator`. A 4.x build needs small replacements for those and is
planned after stage 4; until then 4.24 users can try no-plugin mode
(`uvx daz3d-mcp setup --no-plugin`).
