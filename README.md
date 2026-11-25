# design2fusion

Convierte diseños de **Figma, Penpot y FigCraft** en **nodos de Fusion (DaVinci Resolve)**:
un nodo por elemento, con el nombre que le diste en el diseño, ya posicionado y **sin
conexiones** — las armás vos según la animación.

El texto no se hornea: se convierte en un **Text+ editable** con su contenido, fuente,
tamaño, color y posición. Las formas e imágenes salen como **Loader** con la capa a frame
completo, así al conectarlas aparecen en su lugar sin Transform ni Merge.

Estado: **v0.2.0** — probado con FigCraft 0.18.1 y DaVinci Resolve 21.

## Requisitos

| Pieza | Para qué | Obligatorio |
| --- | --- | --- |
| Python 3.10+ | correr el script | sí |
| [`figcraft-cli`](https://github.com/storytold/figcraft) | leer `.figcraft`, `.penpot`, `.fig` y JSON REST | sí (salvo URLs de Figma) |
| ImageMagick (`convert` o `magick`) | convertir las capas PNG a EXR — el `Loader` de Fusion solo lee EXR | sí |
| [`figma2fusion`](https://github.com/TulunLK/figma2fusion) | resolver URLs / file keys de Figma por la API REST | solo para Figma por URL |
| DaVinci Resolve 18+ | usar el `.comp` y el kit | para la salida |

## Instalación

```bash
git clone https://github.com/TulunLK/design2fusion.git
cd design2fusion
ln -s "$PWD/design2fusion" ~/.local/bin/design2fusion   # o copiá el archivo a ~/.local/bin
```

No tiene dependencias de Python fuera de la biblioteca estándar.

## Uso

```bash
# un archivo local, el frame principal
design2fusion slide.figcraft

# elegir frame y exportar a 2x
design2fusion lowerthird.penpot --frame "Lower Third" --scale 2

# carpeta de salida concreta
design2fusion figma_file.json -o ./salida

# Figma por URL o file key (delega en figma2fusion)
design2fusion "https://www.figma.com/design/KEY/Nombre?node-id=3-1"

# interfaz web local (arrastrar y soltar)
design2fusion --ui            # http://127.0.0.1:8765
```

| Flag | Qué hace |
| --- | --- |
| `--frame NOMBRE\|ID` | elige el frame a exportar (por defecto, el primero) |
| `--page NOMBRE` | elige la página |
| `-o, --out DIR` | carpeta de salida (por defecto `~/Documentos/MotionGraphic/design2fusion/<frame>`) |
| `--scale N` | escala de las capas PNG (1 por defecto; `--scale 2` para 2x) |
| `--no-comp` | no genera el `.comp` |
| `--no-kit` | no genera el kit de `.setting` |
| `--json` | imprime el resultado como JSON (útil para scripts) |
| `--ui` / `--port N` | levanta la interfaz web local |
| `--version` | versión |

## Qué genera

```
<frame>/
├── manifest.json                 geometría, texto, vidrio y efectos de cada capa
├── referencia.png                el frame completo renderizado (para comparar)
├── capas/
│   ├── 01_Panel.png              capa con su caja exacta (alpha real)
│   └── 01_Panel_mask.png         silueta limpia del vidrio (para tu Blur)
├── fusion/
│   ├── Slide.comp                un nodo por capa, sin conexiones
│   └── 01_Panel.exr              cada capa a frame completo (1920×1080, 16-bit)
└── kit/
    ├── MediaIn.setting
    ├── TextPlus_Montserrat_Bold.setting
    ├── TextPlus_Inter_Bold.setting
    ├── Blur.setting
    ├── Merge.setting
    └── SoftGlow.setting
```

Los nombres de nodo son los de tus capas, con espacios reemplazados por `_`
(`Text 1` → `Text_1`), porque Fusion usa el nombre como identificador.

## En Resolve

1. Poné tu video o imagen de fondo en **V1**.
2. Clic derecho sobre el clip → **Fusion Clip**.
3. En la página Fusion: **Fusion → Import Comp** → elegí `fusion/<frame>.comp`.
4. Aparecen los nodos sueltos, ya nombrados y posicionados: los `TextPlus` con tu texto
   editable y los `Loader` con la capa en su lugar.
5. Conectá lo que necesites. No hay MediaIn ni Merge: la base es tuya.

## Formatos de entrada

| Formato | Cómo entra | Notas |
| --- | --- | --- |
| `.figcraft` | directo | el más fiel |
| `.penpot` | `figcraft-cli convert` | se pierden glass, ruido y texturas (Penpot no los tiene) |
| `.json` (REST de Figma) | `figcraft-cli convert` | **exige la carpeta `images/` al lado**, si no FigCraft exporta un placeholder gris sin avisar |
| `.fig` | `figcraft-cli convert` | experimental |
| URL / file key de Figma | delega en `figma2fusion` | renderiza por la API REST, siempre 1x |

## Límites conocidos

- **El borde del vidrio** (stroke con gradiente) no se exporta como capa: el nodo trae el
  tinte del panel y la silueta queda en `capas/_mask.png` para que armes el Blur en Fusion.
- **Text+ asume texto centrado** en su caja. Si el diseño tiene el texto alineado a la
  izquierda en una caja más ancha, ajustá la justificación en Fusion.
- **Un frame con fill de imagen** no entra como capa (es el fondo): usá `referencia.png`
  como plate o conectá tu propio fondo.
- **Figma por URL sale a 1x** (`--scale` se ignora en esa ruta).
- Depende de **FigCraft en runtime** para leer los archivos locales.
- FigCraft **hornea el fondo** en las capas que tienen `backgroundBlur`; el script lo
  detecta, limpia los efectos antes de exportar y por eso genera `_mask.png` + el tinte
  por separado.
- Los EXR van a frame completo, así que pesan ~16 MB por capa a 1080p.

## Cómo funciona

```
.figcraft ─┐
.penpot  ──┤ figcraft-cli convert ─┐
.fig     ──┤                      ├─ MCP (FigCraft) ─ export por capa ─ manifest.json
.json    ──┘                      │                                      │
URL Figma ─ figma2fusion ─────────┘                                      ├─ comp.py ─ .comp (nodos sueltos)
                                                                         └─ settings.py ─ kit
```

El cliente MCP habla con `figcraft-cli mcp` por stdio y usa `export` con
`includeBoundingBox: true`, así cada PNG mide exactamente lo que mide el nodo (sin el
padding de las sombras). Después `comp.py` compone cada capa sobre un lienzo transparente
del tamaño del frame y la convierte a EXR: de ahí que el nodo quede posicionado sin
necesidad de cables.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Licencia

MIT — ver [LICENSE](LICENSE).
