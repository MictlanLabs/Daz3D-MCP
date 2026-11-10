# Daz3D-MCP

Permite que agentes de IA (Claude Code, Codex, Cursor, Antigravity, Gemini CLI,
Claude Desktop, VS Code y cualquier cliente MCP) controlen **Daz Studio**:
abrir y guardar escenas, buscar el contenido instalado, crear personajes
(forma, ropa, pelo, poses), preparar cámaras, luces y materiales, renderizar con
Iray y ejecutar DazScript.

> Proyecto open source independiente. No está afiliado ni respaldado por Daz 3D.
> [Read in English](README.md)

**Estado: v0.2 (etapa 2 de 4).** Funcionan escenas, biblioteca de contenido,
personajes, cámaras, luces, materiales y render. Los assets de terceros y la
animación llegan en las siguientes etapas. Las etapas 1 y 2 están probadas
contra un Daz Studio simulado; sus pruebas de cierre en un Daz Studio 6 real
siguen pendientes.

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
| `content_libraries` | Lista las bibliotecas de contenido y cuántos archivos tiene el índice |
| `content_search` | Busca figuras, personajes, ropa, pelo, poses, materiales, props y luces instalados |
| `content_thumbnail` | Muestra la miniatura de un archivo de contenido |
| `content_load` | Carga contenido; ajusta ropa y pelo, aplica poses, personajes y materiales a un objetivo |
| `node_set` | Mueve, rota, escala, muestra/oculta, renombra o selecciona un nodo |
| `node_delete` | Borra nodos (y lo que lleva puesto una figura) |
| `figure_info` | Generación, altura, ropa, morphs en uso, huesos posados y superficies de una figura |
| `morph_list` / `morph_set` | Busca y ajusta diales de forma |
| `pose_bones` / `pose_reset` | Rota huesos / vuelve a la pose por defecto |
| `wearable_fit` | Ajusta ropa o pelo a una figura, o lo desajusta |
| `camera_create` / `camera_set` | Crea o cambia una cámara; puede encuadrar nodos sola |
| `light_create` / `light_set` | Crea o cambia luces spot, point y distant |
| `environment_set` | Domo de Iray, HDRI y sol-cielo |
| `material_list` / `material_set` | Lee y cambia superficies (colores, rugosidad, texturas) |
| `render_settings` | Tamaño de imagen y límites de Iray |
| `render` | Renderiza a un archivo y devuelve la imagen |
| `run_script` | Ejecuta DazScript para todo lo demás (se puede desactivar) |
| `daz_guide` | Devuelve las skills como texto para agentes sin soporte de skills |

Skills: `daz-basics`, `scene-building`, `characters`, `rendering`.

Pruébalo: *"Abre ~/Documents/escena.duf en Daz, describe la escena y muéstrame una captura."*
O: *"Monta una escena con dos personajes Genesis 9, vestidos y posados,
conversando, y renderízala."*

La búsqueda de contenido corre en el servidor MCP sobre un índice de los
archivos de la biblioteca (`~/.daz3d-mcp/content-index.json`, se reconstruye
cada 24 horas o con `refresh_index=true`), así que una búsqueda nunca congela
Daz Studio.

## Configuración

`~/.daz3d-mcp/settings.json` (lo crea `setup`):

| Clave | Por defecto | Significado |
| --- | --- | --- |
| `allow_run_script` | `true` | Permite la herramienta libre `run_script` |
| `transport` | `"auto"` | `auto`, `http` (solo plugin) o `file` (modo sin plugin) |
| `daz_executable` | detectado | Ejecutable de Daz Studio, para el modo sin plugin |
| `timeout` | `600` | Segundos de espera por petición |
| `render_timeout` | `3600` | Segundos de espera por render |
| `render_dir` | `~/.daz3d-mcp/renders` | Dónde van los renders sin ruta |
| `content_libraries` | `[]` | Carpetas de biblioteca extra para buscar |
| `content_index_max_age_hours` | `24` | Cada cuánto se reconstruye el índice de contenido |

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
