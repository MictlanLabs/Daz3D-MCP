# Daz3D-MCP

Permite que agentes de IA (Claude Code, Codex, Cursor, Antigravity, Gemini CLI,
Claude Desktop, VS Code y cualquier cliente MCP) controlen **Daz Studio**:
abrir y guardar escenas, buscar el contenido instalado, crear personajes
(forma, ropa, pelo, poses), preparar cámaras, luces y materiales, renderizar con
Iray, instalar contenido de otras tiendas, importar modelos OBJ y FBX, animar
figuras (keyframes, presets, FBX de Mixamo y BVH de captura de movimiento) y
ejecutar DazScript.

> Proyecto open source independiente. No está afiliado ni respaldado por Daz 3D.
> [Read in English](README.md)

**Estado: v0.4 (etapa 4 de 4).** Funcionan escenas, biblioteca de contenido,
personajes, cámaras, luces, materiales, render, assets de terceros (paquetes
de otras tiendas, importar OBJ/FBX y convertir mallas importadas en ropa) y
animación (keyframes, presets, importar BVH y FBX con mapa de huesos, reubicar
y cambiar el ritmo). Las cuatro etapas están probadas contra un Daz Studio
simulado; sus pruebas de cierre en un Daz Studio 6 real siguen pendientes.

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
| `package_inspect` / `package_install` | Revisa un .zip de otra tienda e instala su contenido en una biblioteca |
| `package_list` / `package_uninstall` | Lista los paquetes instalados / borra exactamente los archivos que instaló uno |
| `content_add_library` | Agrega una carpeta a las bibliotecas de contenido de Daz Studio |
| `mesh_inspect` / `import_mesh` | Lee un OBJ o FBX (tamaño, unidades, texturas) / lo importa al tamaño correcto, sin diálogos |
| `wearable_from_mesh` | Convierte una prenda importada en ropa que sigue a una figura (Transfer Utility) |
| `wearable_adjust` | Suavizado y colisión de la ropa (corrige la piel que atraviesa la tela) |
| `anim_timeline` | Fotogramas por segundo, rango, frame actual y qué está animado |
| `anim_keys_set` / `anim_keys_get` / `anim_keys_delete` | Keyframes en huesos, cadera, nodos, morphs y cualquier propiedad numérica |
| `anim_key_pose` | Pone keys de la pose actual (de `pose_bones` o un preset de pose) en unos frames |
| `anim_sample` | Posición en el mundo de los huesos en unos frames, para revisar un movimiento |
| `anim_preview` | Imágenes del viewport de varios frames |
| `anim_foot_contact` | Detecta pies que atraviesan el piso, flotan o resbalan; puede corregir la altura de la cadera |
| `anim_retime` / `anim_offset` | Más rápido, más lento o a una duración / más tarde, movido, girado o en un punto |
| `anim_preset_list` / `anim_preset_save` / `anim_preset_apply` | Presets de animación: incluidos, propios (en bucle, repetidos) y .duf comprados |
| `anim_file_inspect` / `anim_import` | Lee un BVH o FBX binario (Mixamo, CMU...) y lo adapta a una figura Genesis con un mapa de huesos |
| `camera_create` / `camera_set` | Crea o cambia una cámara; puede encuadrar nodos sola |
| `light_create` / `light_set` | Crea o cambia luces spot, point y distant |
| `environment_set` | Domo de Iray, HDRI y sol-cielo |
| `material_list` / `material_set` | Lee y cambia superficies (colores, rugosidad, texturas) |
| `render_settings` | Tamaño de imagen y límites de Iray |
| `render` | Renderiza a un archivo y devuelve la imagen |
| `render_animation` | Renderiza cada cuadro de la animación y los une en un MP4 o GIF |
| `run_script` | Ejecuta DazScript para todo lo demás (se puede desactivar) |
| `daz_guide` | Devuelve las skills como texto para agentes sin soporte de skills |

Skills: `daz-basics`, `scene-building`, `characters`, `rendering`, `third-party-assets`, `animation`.

Pruébalo: *"Abre ~/Documents/escena.duf en Daz, describe la escena y muéstrame una captura."*
O: *"Monta una escena con dos personajes Genesis 9, vestidos y posados,
conversando, y renderízala."*
O: *"Instala ~/Downloads/chaqueta.zip, viste a Ana con ella, luego importa
~/Downloads/capa.fbx y conviértela en ropa que la siga."*
O: *"Haz que Ana camine cuatro pasos hacia la cámara y luego pon en Leo
~/Downloads/Dancing.fbx de Mixamo desde el frame 60."*

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
| `ffmpeg` | detectado | ffmpeg que usa `render_animation` para los vídeos (PATH, luego el que trae Daz Studio) |
| `content_libraries` | `[]` | Carpetas de biblioteca extra para buscar |
| `content_index_max_age_hours` | `24` | Cada cuánto se reconstruye el índice de contenido |
| `install_library` | `~/Documents/DAZ 3D/Third Party Library` | Dónde instala `package_install` los paquetes |
| `max_package_gb` | `20` | Paquete más grande (descomprimido) que acepta `package_install` |
| `rotation_convention` | medida | Cómo gira Daz los huesos; el primer `anim_import` la mide y la guarda en `~/.daz3d-mcp/animation.json` |

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
