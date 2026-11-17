# Registro de cambios

> [Read in English](CHANGELOG.md)

Los cambios importantes del paquete de Python `daz3d-mcp` (servidor MCP,
biblioteca de DazScript y skills). El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones
siguen [Versionado Semántico](https://semver.org/lang/es/) como se explica en
[Versiones](README.es.md#versiones).

El plugin puente (`bridge/`) tiene su propia versión en `bridge/src/version.h`,
que se anota abajo cuando cambia.

## [Sin publicar]

### Añadido

- `contact_bake`: la mano de la propia figura que presiona un pecho lo deforma de verdad. En cada fotograma mide dónde entran la palma y cada dedo en la malla posada, empuja la piel hasta la superficie de la mano, abulta el tejido alrededor y añade inercia de resorte (retraso, rebote al soltar y asentamiento), horneado como un morph por fotograma.
- Dials de contacto para animación: `morph_generate` crea `bust_press_left` / `bust_press_right` ("MCP Bust Press Left/Right") en Genesis 9 y 8 / 8.1, un hundimiento bajo la palma que presiona con el tejido de alrededor abultándose, para animarlos sincronizados con una mano. No son rasgos de personaje, así que las fichas de personaje no los usan.

## [1.1.0] - 2026-11-16

### Agregado

- Fichas de personaje para crear personajes únicos a partir de una descripción y reutilizarlos: `character_create` crea un personaje (figura base, cuerpo, estatura, cada detalle de la cara, piel, ojos, pelo, ropa) y lo guarda como ficha JSON editable más un preset de personaje de Daz (`.duf`); `character_load` lo pone en cualquier escena, o sobre una figura que ya esté en ella; `character_update` cambia solo lo que se pide (un rasgo, el pelo, una prenda) y deja lo demás; `character_list` lista los personajes guardados y el vocabulario de rasgos.
- Unos 115 rasgos de -1 a 1 cubren la complexión (estatura, peso, músculo, edad, busto, panza, caderas, muslos, brazos, proporciones) y cada parte de la cara: forma de la cara y del cráneo, frente, sienes, cejas, ojos, párpados, pliegue epicántico, pestañas, iris, pupilas, nariz (puente, joroba, punta, fosas, septum, torcida), mejillas, hoyuelos, labios, filtrum, boca, mandíbula (ángulo, desviación, papada, doble mentón), barbilla, orejas (lóbulos, ángulo, puntiagudas), dientes (tamaño, largo, forma afilada, separación, chuecos, mordida, encías, colmillos, colmillos inferiores), arrugas y asimetría natural. Cada vez que se aplica una ficha, los rasgos se traducen a los diales instalados en la figura, así que una misma ficha sirve en Genesis 9, 8.1 y 8; los rasgos sin un dial instalado se reportan, y los sustitutos cercanos se marcan como aproximados. En Genesis 9, los diales de asimetría izquierdo y derecho en pareja dan forma a labios, inclinación de los ojos, párpados, mejillas, cejas y forma de la cara aun sin los paquetes de morphs.
- Las fichas también guardan heterocromía (un iris por ojo), el color de lo blanco de los ojos, cejas y vello facial con sus propios colores (raíz y punta), colores de dientes, encías, uñas y labios, añadidos como cuernos o cola, y cualquier otro cambio de material; `dials` llega a la Boca y los Ojos de Genesis 9 con `mouth:` y `eyes:`.
- `morph_generate` crea diales de forma nuevos para rasgos sin morph instalado (20 diales en Genesis 9 y Genesis 8 / 8.1: ancho, tamaño, largo, puente y punta de la nariz, filtrum, sienes, ojeras, pómulos, largo y proyección de la barbilla, ancho y definición de la mandíbula, labios carnosos, tamaño y ángulo de las orejas, edad, peso, músculo y panza), a partir de la malla de la figura, los pesos de los huesos de su cara y su cuerpo y puntos que encuentra en la cara. Los guarda como morphs en una biblioteca de contenido, así que las figuras nuevas los cargan, y los proyecta sobre lo que la figura lleva puesto (ropa, pelo, cejas, pestañas, ojos, boca), enlazados para que los sigan. Las fichas de personaje los encuentran por rasgo, y al cargar o actualizar un personaje la ropa nueva también los sigue.
- `morph_generate` también crea diales de busto, forma del busto, tamaño de areolas y proyección de pezones. `morph_export` exporta la malla base de una figura como OBJ para esculpirla en Blender, y `morph_import` convierte la escultura en un dial: ajusta el tamaño y los ejes Y-up / Z-up, lo guarda en una biblioteca de contenido y lo que lleva puesto la figura lo sigue.
- Las fichas de personaje aceptan geoinjertos anatómicos (`anatomy`, o `["auto"]` para el instalado que corresponde al cuerpo), con sus diales como `anatomy:<dial>`; `character_list(include_anatomy=...)` lista los instalados y el resultado avisa cuando no hay ninguno.
- `eye_color(sclera=...)` cambia el color de lo blanco de los ojos (rojo, negro, amarillo) sin tocar el iris.
- Un skill `character-design`: cuándo preguntar y qué suponer, una lista ordenada de cada rasgo, una tabla de frases a rasgos para cuerpo, cara, ojos, nariz, boca, mandíbula, orejas y dientes, qué funciona solo con el contenido inicial, cómo hacer caras únicas con pocos diales y mantener distinto a un elenco, cómo revisar el resultado con renders, piel, ojos, pelo y rasgos de fantasía, y las diferencias entre Genesis 9, 8.1 y 8.
- Ajuste `characters_dir` para dónde se guardan las fichas y los presets (por defecto `~/.daz3d-mcp/characters`).

## [1.0.3] - 2026-11-16

### Corregido

- `render_settings(exposure=...)` y las propiedades del tone mapper no hacían nada en una escena nueva, que no tiene nodo Tonemapper Options hasta que el panel Render Settings o un render lo crean; ahora el nodo se crea cuando hace falta.
- `eyes_look_at` con `head > 0` sumaba giro de cabeza en cada llamada; ahora la cabeza toma la parte indicada del giro completo, así que repetir la llamada la deja donde estaba.
- `face_expression("angry")` casi no se notaba en Genesis 8.1, que no tiene el dial Brow Squeeze; ahora usa el dial de expresión Angry propio de la figura, con la boca más cerrada.
- `light_set(on=true)` ponía la Illumination de una luz Iray en "Diffuse Only" en vez de "On".

### Cambiado

- El README (inglés y español) muestra el logo del proyecto, un diagrama de arquitectura y una sección de ejemplos con renders hechos con las herramientas: expresiones faciales, iluminación, planos de diálogo y un GIF de animación. Las imágenes están en `docs/images/` y se enlazan con URLs absolutas para que también se vean en PyPI.

## [1.0.2] - 2026-11-16

### Corregido

- `install` y `doctor` encuentran la configuración de Claude Desktop en `%LOCALAPPDATA%\Claude-Data\<carpeta>\claude_desktop_config.json`, donde la guardan las versiones recientes de Windows (la app de Microsoft Store), en vez de `%APPDATA%\Claude`.

## [1.0.1] - 2026-11-16

### Corregido

- `setup` no copiaba el plugin después de que Windows daba el permiso de administrador cuando la carpeta de plugins de Daz Studio ya existía (siempre, en una instalación normal).

## [1.0.0] - 2026-11-16

Primer lanzamiento público: en PyPI (`uvx daz3d-mcp`) con el plugin puente
compilado en el release de GitHub.

### Cambiado

- `setup` pide permiso de administrador a Windows (una ventana de UAC) cuando
  la carpeta de plugins de Daz Studio está protegida, en vez de fallar.
  `--no-elevate` lo desactiva.
- `setup` se detiene con un mensaje claro cuando Daz Studio está abierto y
  dejaría bloqueado el plugin anterior, y cuando el Daz Studio encontrado es la
  4.24, que no tiene plugin compilado.
- El README (inglés y español) está escrito para una primera instalación:
  requisitos, instalación, cómo agregar el servidor a mano en cada cliente,
  actualizar, desinstalar y solución de problemas. Sus enlaces funcionan en PyPI.
- El paquete indica que solo funciona en Windows.

## [0.6.0] - 2026-11-16

### Agregado

- `wearable_refit` repara cualquier prenda de otra generación de Genesis, no
  solo zapatos. Informa `rig` (cuánto de la prenda cuelga de huesos que la
  figura tiene) y `shape` (distancia a la piel con y sin cada forma clon), con
  los problemas `not_converted` y `other_shape`; `fix=true` reconstruye esa
  prenda con la Transfer Utility de Daz y el clon de su generación, y luego
  convierte lo que estaba ajustado a ella (cinturones, cierres, botones).
  Nuevo argumento `convert`.
- `wearable_refit(item=<figura>)` revisa, o con `fix=true` repara, todo lo que
  viste una figura.
- `wearable_refit` informa `below_floor` cuando una suela queda bajo el piso,
  y `feet.*.heel_minus_toe_cm`.
- `daz_dialog` informa `more_dialogs` cuando Daz abre otro diálogo justo
  después de terminar la llamada detenida (el Auto-Fit pregunta una vez por
  cada prenda de un conjunto).

### Corregido

- Las prendas de un conjunto cuyo diálogo de Auto-Fit nadie respondía se
  quedaban con los huesos y la forma de la otra generación (un overol de
  Genesis 9 en Genesis 8 dejaba los brazos abajo y no seguía la pose). Ahora
  se detectan y se reconstruyen.
- Las botas de suela gruesa sin plantilla modelada salían como
  `foot_floating`; un hueco parejo ahora es una nota.
- El encuadre de las cámaras suponía que el cuadro de 36 mm cubre el ancho de
  la imagen; Daz Studio lo reparte en el alto. `render_cull` quitaba cosas a
  los lados de una imagen ancha que sí se veían (las pestañas y los guantes
  de una figura en el borde de un plano de dos), `camera_shot` encuadraba 1.8
  veces más abierto de lo pedido en imágenes 16:9 y `camera_create(frame=...)`
  dejaba espacio de más. Los primeros planos ahora son tan cerrados como dice
  su nombre, y `extreme_close_up` deja la boca dentro de la imagen.
- `wearable_refit` medía los pies contra una prenda ajustada a otra prenda;
  ahora usa la figura que la viste.

## [0.5.1] - 2026-11-15

### Agregado

- `render_settings(exposure=...)` fija el Exposure Value de Iray; el resultado
  informa `exposure` (EV, velocidad de obturación, f-stop, ISO).
- `camera_shot(avoid_walls=true)`: encuentra por sí solo las paredes y otros
  props entre la cara y la cámara (`wall`, `wall_cm`, `pulled_in_cm`).
- `package_inspect` y `package_install` informan `requires`: los productos que
  un paquete necesita y no están instalados.

### Corregido

- `light_create` creaba las luces spot y point con Photometric Mode apagado,
  así que Iray ignoraba sus lúmenes. Ahora se crean como desde el menú Create
  de Daz, y `light_set(power=...)` enciende el modo en una luz anterior.
- Cambiar "Exposure Value" por script no cambiaba el render: Iray usa la
  velocidad de obturación, el f-stop y el ISO. Ahora el valor se convierte en
  velocidad de obturación, y cambiar esos tres mantiene el Exposure Value al día.
- `import_mesh(room=true)` tomaba como suelo la superficie horizontal más
  grande, que en un edificio de techo plano es el techo (el Wild West Saloon se
  hundía 6.9 m). Ahora el suelo es la superficie horizontal más grande que
  tiene algo encima y espacio para estar de pie (entre pisos de tamaño parecido,
  el más bajo), a la altura donde está la mayor parte. El saloon queda ahora
  sobre las tablas de la planta baja.
- `camera_shot` dejaba la cámara fuera o detrás de las paredes de un cuarto
  pequeño si no se daba `max_distance` a mano. Ahora se pone delante de la
  pared con una lente más corta que conserva el encuadre, y avisa por debajo de
  14 mm.
- `package_install` no avisaba cuando un paquete necesita una figura base (p. ej.
  Genesis 8.1 Female), el producto para el que es un paquete de morphs, o un
  paquete de morphs del cuerpo que mueven sus presets (p. ej. Vlad Gens,
  Breastacular).
- `package_inspect` podía fallar en Windows con paquetes que traen un .zip
  dentro, al borrar su carpeta temporal.

## [0.5.0] - 2026-11-15

### Agregado

- Poses en muebles: `prop_surfaces` mide dónde se puede sentar o acostar en una
  silla, sofá o cama, `place_on` pone ahí una figura ya posada y `fit_check`
  avisa de las partes del cuerpo que flotan o atraviesan el mueble; límites de
  articulaciones y puntos de referencia en `figure_info`. Nueva skill
  `furniture-poses`.
- Caras: `face_expression` (expresiones con nombre), `eyes_look_at` y
  `eye_color`. Nueva skill `faces`.
- Escenas de diálogo: `camera_shot` encuadra primeros planos, planos sobre el
  hombro y planos de dos respetando la regla de los 180 grados, y
  `render_shots` renderiza una conversación con una imagen por línea. Nueva
  skill `dialogue-scenes`.
- Diálogos de Daz Studio: `daz_dialog` lee y responde las ventanas emergentes
  que detienen una llamada (`dialog_open`), con reglas predefinidas y manejo de
  avisos de sobrescritura; la llamada continúa una vez respondido el diálogo.
- `render_animation`: renderiza los cuadros de la línea de tiempo con Iray,
  retoma renders a medias y codifica MP4 o GIF con ffmpeg; `render` puede
  renderizar un solo cuadro.
- `render_cull` deja fuera del render lo que la cámara no ve (fuera del
  encuadre, detrás de ella, ropa bajo otra ropa) sin quitar lo que ilumina la
  escena; `render`, `render_shots` y `render_animation` aceptan `cull=true`.
  Nueva skill `render-culling`.
- `wearable_refit` revisa y repara ropa y zapatos ajustados desde otra
  generación de Genesis (G8/G8.1 en G9 y al revés). Nueva skill
  `cross-generation-clothing`.
- Este registro de cambios; la versión del paquete ahora vive solo en
  `pyproject.toml`.

### Corregido

- Herramientas probadas por primera vez contra un Daz Studio 6 real.
- Retargeting de animaciones desde FBX exportados por Daz (orden de rotación,
  diales limitados, transformaciones y colocación del FBX).
- Carga del plugin en Windows con Daz Studio 6.
- `mesh_inspect` e `import_mesh` con escenarios FBX de Blender: los tamaños se
  leen como Daz los va a importar (`bbox_cm`), se da un `suggested_scale`
  cuando el tamaño no es creíble, se dejan fuera los nodos de cámara, luz y
  vacíos, y las superficies transparentes se vuelven vidrio de Iray.
- `eyes_look_at` apunta mejor cerca de los límites de las articulaciones de los
  ojos; `content_load` atiende los diálogos diferidos de Daz antes de
  terminar.
- `render_animation` ya no se cuelga cuando ffmpeg espera entrada de consola.

### Cambiado

- README: marcado como proyecto en etapa temprana y solo para Windows, y
  documentado que Iray necesita una GPU NVIDIA.
- Plugin puente 0.2.0 (manejo de diálogos). Hay que recompilarlo para usar
  `daz_dialog`.

## [0.4.0] - 2026-11-10

### Agregado

- Animación: keyframes (`anim_keys_set`, `anim_keys_get`, `anim_keys_delete`,
  `anim_key_pose`), línea de tiempo, presets incluidos y guardados, importación
  de FBX de Mixamo y BVH en figuras Genesis, cambio de tiempos,
  desplazamientos, contacto de los pies y vistas previas. Nueva skill
  `animation`.

## [0.3.0] - 2026-11-10

### Agregado

- Contenido de terceros: `package_inspect`, `package_install`, `package_list`,
  `package_uninstall`, `mesh_inspect`, `import_mesh`, `wearable_from_mesh` y
  `wearable_adjust`. Nueva skill `third-party-assets`.

## [0.2.0] - 2026-11-10

### Agregado

- Personajes (figuras, morphs, ropa con `wearable_fit`, cabello, poses,
  huesos) y herramientas de render con Iray. Nuevas skills `characters` y
  `rendering`.

## [0.1.0] - 2026-11-10

### Agregado

- Primer servidor MCP, plugin puente, herramientas de escena y los comandos
  `setup`, `install` y `doctor`.

[Sin publicar]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/MictlanLabs/Daz3D-MCP/releases/tag/v1.0.0
[0.6.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MictlanLabs/Daz3D-MCP/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MictlanLabs/Daz3D-MCP/releases/tag/v0.1.0
