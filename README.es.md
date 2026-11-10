# Daz3D-MCP

Permite que agentes de IA (Claude Code, Codex, Cursor, Antigravity, Gemini CLI,
Claude Desktop, VS Code y cualquier cliente MCP) controlen **Daz Studio**:
abrir y guardar escenas, describir lo que contienen, ver el viewport y ejecutar
DazScript.

> Proyecto open source independiente. No está afiliado ni respaldado por Daz 3D.
> [Read in English](README.md)

**Estado: v0.1 (etapa 1 de 4).** Funcionan escenas, captura del viewport y
scripts. Personajes, carga de contenido, assets de terceros y animación llegan
en las siguientes etapas.

## Cómo funciona

```
Agente ──MCP (stdio)──> daz3d-mcp (Python) ──HTTP 127.0.0.1 + token──> plugin puente ──> DazScript en Daz Studio
```

- **Plugin puente** (`bridge/`, C++): un servidor mínimo dentro de Daz Studio.
  Solo escucha en `127.0.0.1`, exige un token y ejecuta DazScript en el hilo
  principal.
- **Biblioteca DazScript** (`scripts/`): un script por herramienta; hace el trabajo real.
- **Servidor MCP** (`src/daz3d_mcp/`, Python): las herramientas que usa el agente.
- **Skills** (`skills/`): guías `SKILL.md` que enseñan al agente a usar Daz. Los
  agentes sin soporte de skills reciben el mismo texto por el MCP (herramienta
  `daz_guide`, prompts y resources).

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/getting-started/installation/) y
Daz Studio 6 (el soporte de 4.24 llega después).

```bash
uvx daz3d-mcp setup           # copia el plugin puente a Daz Studio
uvx daz3d-mcp install --all   # registra el MCP y las skills en los agentes instalados
uvx daz3d-mcp doctor          # revisa todo y dice qué arreglar
```

Después reinicia Daz Studio y tus agentes.

Hasta la primera versión en PyPI, usa los mismos comandos desde GitHub:

```bash
uvx --from git+https://github.com/MictlanLabs/Daz3D-MCP daz3d-mcp install --all
```

`install` configura los agentes para que ejecuten ese mismo código.

**Un solo agente:** `uvx daz3d-mcp install --client cursor` (también
`claude-code`, `codex`, `antigravity`, `gemini-cli`, `claude-desktop`,
`windsurf`, `vscode`). `uvx daz3d-mcp uninstall` quita todo lo que agregó.

**Otro cliente MCP:** agrega este servidor a su configuración:

```json
{ "mcpServers": { "daz3d": { "command": "uvx", "args": ["daz3d-mcp"] } } }
```

**¿Aún no tienes el plugin compilado?** `uvx daz3d-mcp setup --no-plugin` usa un
modo experimental que le pide al Daz Studio abierto que ejecute archivos de
script. Es más lento pero no necesita compilar nada.

## Herramientas

| Herramienta | Qué hace |
| --- | --- |
| `daz_status` | Comprueba la conexión; versión de Daz y escena abierta |
| `scene_info` | Figuras, ropa, props, cámaras y luces con posición, rotación y tamaño |
| `scene_new` | Vacía la escena (no pierde cambios sin guardar salvo que se pida) |
| `scene_open` | Abre o fusiona una escena `.duf` |
| `scene_save` | Guarda en `.duf` (no sobrescribe otro archivo salvo que se pida) |
| `viewport_capture` | Devuelve un PNG del viewport, opcionalmente desde una cámara o frame |
| `run_script` | Ejecuta DazScript para todo lo demás (se puede desactivar) |
| `daz_guide` | Devuelve las skills como texto para agentes sin soporte de skills |

Pruébalo: *"Abre ~/Documents/escena.duf en Daz, describe la escena y muéstrame una captura."*

## Configuración

`~/.daz3d-mcp/settings.json` (lo crea `setup`):

| Clave | Por defecto | Significado |
| --- | --- | --- |
| `allow_run_script` | `true` | Permite la herramienta libre `run_script` |
| `transport` | `"auto"` | `auto`, `http` (solo plugin) o `file` (modo sin plugin) |
| `daz_executable` | detectado | Ejecutable de Daz Studio, para el modo sin plugin |
| `timeout` | `600` | Segundos de espera por petición |

## Seguridad

El puente solo escucha en `127.0.0.1`, exige el token aleatorio guardado en
`~/.daz3d-mcp/token` (solo tú puedes leerlo) y rechaza peticiones de
navegadores. `run_script` le da al agente el mismo poder que un DazScript que
ejecutes tú; pon `allow_run_script` en `false` si no lo quieres.

## Desarrollo

```bash
uv run --group dev pytest            # pruebas de Python y DazScript (Node.js ejecuta los scripts contra un Daz simulado)
npm install --prefix tests/fake_daz  # una vez, para revisar la sintaxis ES5
```

Compilar el puente: ver [bridge/README.md](bridge/README.md).
El protocolo del puente está en [docs/protocol.md](docs/protocol.md).

## Licencia

Apache 2.0. Ver [LICENSE](LICENSE). El SDK de Daz Studio no se incluye.
