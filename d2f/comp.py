"""Emite un .comp de Fusion con un nodo por capa, sin conexiones.

Cada capa del diseño se convierte en un nodo independiente con el nombre que
tenía en Figma/Penpot/FigCraft:
  - texto  -> TextPlus (editable en Fusion)
  - gráfico -> Loader apuntando a un EXR a tamaño de frame (ya posicionado)

No se crean Merge, MediaIn ni cables: el usuario conecta lo que necesite.
"""
import os
import re
import shutil
import subprocess

GRID_COLS = 5
GRID_DX = 150
GRID_DY = 110


def lua_q(s):
    return '"' + str(s).replace("\\", "/").replace('"', '\\"') + '"'


def node_name(name, used=None):
    """Nombre válido de tool en Fusion, único dentro del comp."""
    n = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip()).strip("_") or "Nodo"
    if n[0].isdigit():
        n = "N_" + n
    if used is not None:
        base, k = n, 2
        while n in used:
            n = "%s_%d" % (base, k)
            k += 1
        used.add(n)
    return n


def tool_block(name, kind, values=None, conns=None, pos=(0, 0)):
    lines = ["\t\t%s = %s {" % (name, kind), "\t\t\tInputs = {"]
    for k, v in (values or {}).items():
        if v is None:
            continue
        if k == "Center":
            lines.append("\t\t\t\tCenter = Input { Value = { %s, %s } }," % (v[0], v[1]))
        else:
            lines.append("\t\t\t\t%s = Input { Value = %s }," % (k, v))
    for k, (src, out) in (conns or {}).items():
        lines.append("\t\t\t\t%s = Input { SourceOp = %s, Source = %s },"
                     % (k, lua_q(src), lua_q(out)))
    lines.append("\t\t\t},")
    lines.append("\t\t\tViewInfo = OperatorInfo { Pos = { %s, %s } }," % pos)
    lines.append("\t\t},")
    return "\n".join(lines)


def _hex_of(color):
    c = color or "#ffffff"
    hx = c[1:c.index("@")] if "@" in c else c.lstrip("#")
    if len(hx) == 3:
        hx = "".join(x * 2 for x in hx)
    try:
        return tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (1.0, 1.0, 1.0)


def _im():
    for exe in ("magick", "convert"):
        if shutil.which(exe):
            return exe
    return None


def full_frame_exr(png, rect, fw, fh, exr):
    """Pega el PNG en un canvas transparente del tamaño del frame y lo pasa a EXR.

    Así el Loader aparece ya en su posición sin necesitar un Transform ni Merge."""
    exe = _im()
    if not exe:
        return False
    tmp = exr + ".png"
    x, y = int(round(rect["x"])), int(round(rect["y"]))
    try:
        r = subprocess.run(
            [exe, "-size", "%dx%d" % (fw, fh), "xc:none", png,
             "-geometry", "+%d+%d" % (x, y), "-composite", tmp],
            capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.isfile(tmp):
            return False
        r = subprocess.run([exe, tmp, "-depth", "16", exr],
                           capture_output=True, timeout=180)
        return r.returncode == 0 and os.path.isfile(exr)
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def textplus_block(lay, fw, fh, name, pos=(0, 0)):
    t = lay["text"]
    size = round(float(t.get("font_size_px") or 17) / fw, 6)
    r, g, b = _hex_of(t.get("color"))
    cx, cy = lay["center_x"], lay["center_y"]
    return (
        "\t\t{name} = TextPlus {{\n\t\t\tCtrlWZoom = false,\n\t\t\tInputs = {{\n"
        "\t\t\t\tWidth = Input {{ Value = {fw}, }},\n"
        "\t\t\t\tHeight = Input {{ Value = {fh}, }},\n"
        "\t\t\t\tUseFrameFormatSettings = Input {{ Value = 1, }},\n"
        "\t\t\t\tStyledText = Input {{ Value = {txt} }},\n"
        "\t\t\t\tFont = Input {{ Value = {font} }},\n"
        "\t\t\t\tStyle = Input {{ Value = {style} }},\n"
        "\t\t\t\tSize = Input {{ Value = {size} }},\n"
        "\t\t\t\tRed1 = Input {{ Value = {r} }},\n"
        "\t\t\t\tGreen1 = Input {{ Value = {g} }},\n"
        "\t\t\t\tBlue1 = Input {{ Value = {b} }},\n"
        "\t\t\t\tAlpha1 = Input {{ Value = 1 }},\n"
        "\t\t\t\tVerticalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\t\tHorizontalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\t\tCenter = Input {{ Value = {{{cx}, {cy}}} }},\n"
        "\t\t\t\tAngle = Input {{ Value = {ang} }},\n"
        "\t\t\t}},\n"
        "\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {px}, {py} }} }},\n"
        "\t\t}},"
    ).format(name=name, fw=fw, fh=fh, txt=lua_q(t.get("content", "")),
             font=lua_q(t.get("font_family") or ""),
             style=lua_q(t.get("font_style") or ""),
             size=size, r=r, g=g, b=b,
             cx=round(cx / fw, 6), cy=round(1.0 - cy / fh, 6),
             ang=lay.get("rotation_deg") or 0,
             px=pos[0], py=pos[1])


def shape_block(lay, fw, fh, name, pos=(0, 0)):
    """Genera Background + RectangleMask (o EllipseMask) nativos de Fusion para formas."""
    s = lay["shape"]
    r, g, b = _hex_of(s.get("color"))
    opacity = float(s.get("opacity", 1.0))
    cx = round(lay["center_x"] / fw, 6)
    cy = round(1.0 - lay["center_y"] / fh, 6)
    w = round(lay["width"] / fw, 6)
    h = round(lay["height"] / fh, 6)
    angle = lay.get("rotation_deg") or 0.0
    cr = round(float(s.get("corner_radius") or 0.0) / min(lay["width"], lay["height"]) if min(lay["width"], lay["height"]) > 0 else 0.0, 4)
    cr = min(max(cr, 0.0), 0.5)

    is_ellipse = s.get("type") == "ELLIPSE"
    mask_kind = "EllipseMask" if is_ellipse else "RectangleMask"
    mask_name = name + "Mask"

    # En Fusion, un Background conectado a una Mask genera la forma vectorial con color sólido.
    # El Background lleva EffectMask conectado a la máscara.
    bg_lines = [
        "\t\t%s = Background {" % name,
        "\t\t\tCtrlWZoom = false,",
        "\t\t\tInputs = {",
        "\t\t\t\tGlobalOut = Input { Value = 149, },",
        "\t\t\t\tWidth = Input { Value = %d, }," % int(round(fw)),
        "\t\t\t\tHeight = Input { Value = %d, }," % int(round(fh)),
        "\t\t\t\tUseFrameFormatSettings = Input { Value = 1, },",
        "\t\t\t\tTopLeftRed = Input { Value = %s, }," % r,
        "\t\t\t\tTopLeftGreen = Input { Value = %s, }," % g,
        "\t\t\t\tTopLeftBlue = Input { Value = %s, }," % b,
        "\t\t\t\tTopLeftAlpha = Input { Value = %s, }," % opacity,
        "\t\t\t\tEffectMask = Input {",
        "\t\t\t\t\tSourceOp = %s," % lua_q(mask_name),
        "\t\t\t\t\tsource = \"Mask\",",
        "\t\t\t\t},",
        "\t\t\t},",
        "\t\t\tViewInfo = OperatorInfo { Pos = { %s, %s } }," % pos,
        "\t\t},",
    ]

    mask_lines = [
        "\t\t%s = %s {" % (mask_name, mask_kind),
        "\t\t\tCtrlWZoom = false,",
        "\t\t\tInputs = {",
        "\t\t\t\tCenter = Input { Value = { %s, %s } }," % (cx, cy),
        "\t\t\t\tWidth = Input { Value = %s, }," % w,
        "\t\t\t\tHeight = Input { Value = %s, }," % h,
        "\t\t\t\tAngle = Input { Value = %s, }," % angle,
    ]
    if not is_ellipse and cr > 0:
        mask_lines.append("\t\t\t\tCornerRadius = Input { Value = %s }," % cr)

    # Posicionamos la máscara un poco a la izquierda o arriba del background en el nodo flow
    mask_pos = (pos[0] - 80, pos[1])
    mask_lines.extend([
        "\t\t\t},",
        "\t\t\tViewInfo = OperatorInfo { Pos = { %s, %s } }," % mask_pos,
        "\t\t},",
    ])

    return "\n".join(bg_lines + mask_lines)
    t = lay["text"]
    size = round(float(t.get("font_size_px") or 17) / fw, 6)
    r, g, b = _hex_of(t.get("color"))
    cx, cy = lay["center_x"], lay["center_y"]
    return (
        "\t\t{name} = TextPlus {{\n\t\t\tCtrlWZoom = false,\n\t\t\tInputs = {{\n"
        "\t\t\t\tWidth = Input {{ Value = {fw}, }},\n"
        "\t\t\t\tHeight = Input {{ Value = {fh}, }},\n"
        "\t\t\t\tUseFrameFormatSettings = Input {{ Value = 1, }},\n"
        "\t\t\t\tStyledText = Input {{ Value = {txt} }},\n"
        "\t\t\t\tFont = Input {{ Value = {font} }},\n"
        "\t\t\t\tStyle = Input {{ Value = {style} }},\n"
        "\t\t\t\tSize = Input {{ Value = {size} }},\n"
        "\t\t\t\tRed1 = Input {{ Value = {r} }},\n"
        "\t\t\t\tGreen1 = Input {{ Value = {g} }},\n"
        "\t\t\t\tBlue1 = Input {{ Value = {b} }},\n"
        "\t\t\t\tAlpha1 = Input {{ Value = 1 }},\n"
        "\t\t\t\tVerticalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\t\tHorizontalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\t\tCenter = Input {{ Value = {{{cx}, {cy}}} }},\n"
        "\t\t\t\tAngle = Input {{ Value = {ang} }},\n"
        "\t\t\t}},\n"
        "\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {px}, {py} }} }},\n"
        "\t\t}},"
    ).format(name=name, fw=fw, fh=fh, txt=lua_q(t.get("content", "")),
             font=lua_q(t.get("font_family") or ""),
             style=lua_q(t.get("font_style") or ""),
             size=size, r=r, g=g, b=b,
             cx=round(cx / fw, 6), cy=round(1.0 - cy / fh, 6),
             ang=lay.get("rotation_deg") or 0,
             px=pos[0], py=pos[1])


# -----------------------------------------------------------------------------
# Presets de texto tomados de Reactor
#
# No se redistribuyen las macros: se leen del equipo donde el usuario ya las
# instaló con Reactor (o desde la carpeta de macros de Resolve) y se inyecta su
# GroupOperator en el .comp, con los valores de la capa. Así el texto llega con
# animación de entrada y una página "Controls" ordenada.
# -----------------------------------------------------------------------------
TEXT_ANIM_PRESETS = {
    "scale-in": "Scale In",
    "letter-slide": "Letter Slide Up + Fade Bounce",
}

MACRO_DIRS = (
    "~/.local/share/DaVinciResolve/Fusion/Macros",
    "~/Reactor/Deploy/Macros",
    "~/Reactor/Atoms",
    "/opt/resolve/Fusion/Macros",
)


def find_macro(preset):
    """Ruta del .setting del preset, o None si no está instalado."""
    fname = TEXT_ANIM_PRESETS.get(preset)
    if not fname:
        return None
    for d in MACRO_DIRS:
        root = os.path.expanduser(d)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if fname + ".setting" in files:
                return os.path.join(dirpath, fname + ".setting")
    return None


def _span(s, start):
    """(ini, fin) del bloque {...} que abre en/después de start."""
    i = s.index("{", start)
    depth = 0
    for k in range(i, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                return i, k + 1
    raise ValueError("llave sin cerrar")


def _tool_span(s, kind, name):
    """(ini, fin) del tool `name = kind { ... }` dentro del grupo."""
    m = re.search(r"(?m)^[ \t]*(%s = %s \{)" % (re.escape(name), kind), s)
    if not m:
        return None
    return m.start(1), _span(s, m.start(1))[1]


def _upsert_input(tool, key, expr):
    """Reemplaza `key = Input {...}` o lo agrega a la tabla Inputs del tool."""
    m = re.search(r"(?m)^([ \t]*)%s = Input \{" % re.escape(key), tool)
    if m:
        j = _span(tool, m.start())[1]
        tail = j + 1 if tool[j:j + 1] == "," else j
        return (tool[:m.start()]
                + "%s%s = Input { %s }," % (m.group(1), key, expr)
                + tool[tail:])
    im = re.search(r"(?m)^([ \t]*)Inputs = \{", tool)
    if not im:
        return tool
    close = _span(tool, im.start())[1] - 1
    line = tool.rfind("\n", 0, close) + 1
    # el input anterior puede ser el último y no llevar coma: se la agregamos
    prev_end = line - 1
    prev_start = tool.rfind("\n", 0, prev_end) + 1
    if (not tool[prev_start:prev_end].rstrip().endswith(",")
            and prev_start > im.start()):
        tool = tool[:prev_end] + "," + tool[prev_end:]
        line += 1
    indent = im.group(1) + "\t"
    return (tool[:line] + "%s%s = Input { %s },\n" % (indent, key, expr)
            + tool[line:])


def _drop_input(tool, key):
    m = re.search(r"(?m)^[ \t]*%s = Input \{" % re.escape(key), tool)
    if not m:
        return tool
    j = _span(tool, m.start())[1]
    if tool[j:j + 1] == ",":
        j += 1
    return tool[:m.start()] + tool[tool.index("\n", j) + 1:]


def anim_text_block(preset, lay, fw, fh, name):
    """GroupOperator del preset con los valores de la capa, o None."""
    path = find_macro(preset)
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"(?m)^([ \t]*)([A-Za-z_]\w* = GroupOperator \{)", src)
    if not m:
        return None
    indent = m.group(1)
    group = src[m.start(2):_span(src, m.start(2))[1]]
    # los tools internos viven en el ámbito del grupo: solo cambia su nombre
    group = indent + name + group[group.index(" ="):]

    ts = _tool_span(group, "TextPlus", "Template")
    if not ts:
        return None
    tool = group[ts[0]:ts[1]]

    t = lay["text"]
    size = round(float(t.get("font_size_px") or 17) / fw, 6)
    r, g, b = _hex_of(t.get("color"))
    cx = round(lay["center_x"] / fw, 6)
    cy = round(1.0 - lay["center_y"] / fh, 6)

    tool = _upsert_input(tool, "Width", "Value = %d" % int(round(fw)))
    tool = _upsert_input(tool, "Height", "Value = %d" % int(round(fh)))
    tool = _upsert_input(tool, "UseFrameFormatSettings", "Value = 1")
    tool = _drop_input(tool, "GlobalOut")
    tool = _upsert_input(tool, "Font",
                         "Value = " + lua_q(t.get("font_family") or "Open Sans"))
    tool = _upsert_input(tool, "Style",
                         "Value = " + lua_q(t.get("font_style") or "Bold"))
    tool = _upsert_input(tool, "Size", "Value = %s" % size)
    tool = _upsert_input(tool, "Center", "Value = { %s, %s }" % (cx, cy))
    for k, v in (("Red1", r), ("Green1", g), ("Blue1", b), ("Alpha1", 1)):
        tool = _upsert_input(tool, k, "Value = %s" % v)

    if preset == "letter-slide":
        # StyledText está cableado desde el Follower: el texto va ahí
        fs = _tool_span(group, "StyledTextFollower", "FollowerLetterAnimation")
        if not fs:
            return None
        follower = group[fs[0]:fs[1]]
        follower = _upsert_input(follower, "Text",
                                 "Value = " + lua_q(t.get("content", "")))
        group = group[:fs[0]] + follower + group[fs[1]:]
    else:
        tool = _upsert_input(tool, "StyledText",
                             "Value = " + lua_q(t.get("content", "")))

    return group[:ts[0]] + tool + group[ts[1]:] + ","


def generate_comp(manifest, outdir, log=print, text_anim="none"):
    """Escribe <outdir>/fusion/<frame>.comp con nodos sueltos (sin cables)."""
    fw = float(manifest["frame"]["width"])
    fh = float(manifest["frame"]["height"])
    fdir = os.path.join(outdir, "fusion")
    os.makedirs(fdir, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", manifest["source"]["frame_name"]) or "comp"
    comp_path = os.path.join(fdir, safe + ".comp")

    tools, used, created = [], set(), []
    anim_warned = False
    for i, lay in enumerate(manifest["layers"]):
        name = node_name(lay.get("name"), used)
        pos = ((i % GRID_COLS) * GRID_DX, (i // GRID_COLS) * GRID_DY)
        if lay.get("text"):
            block = None
            if text_anim not in (None, "", "none"):
                block = anim_text_block(text_anim, lay, fw, fh, name)
                if block is None and not anim_warned:
                    log("  aviso: preset de texto %r no está instalado en Resolve/"
                        "Reactor; uso TextPlus pelado" % text_anim)
                    anim_warned = True
            tools.append(block or textplus_block(lay, fw, fh, name, pos=pos))
            created.append(name)
            continue
        if lay.get("shape"):
            tools.append(shape_block(lay, fw, fh, name, pos=pos))
            created.append(name)
            continue
        png = os.path.join(outdir, lay["png"])
        exr = os.path.join(fdir, os.path.basename(png)[:-4] + ".exr")
        if not full_frame_exr(png, lay["png_rect"], int(fw), int(fh), exr):
            log("  aviso: no pude preparar %s como EXR; la capa %r queda fuera"
                % (png, lay.get("name")))
            continue
        tools.append(tool_block(name, "Loader", {
            "Filename": lua_q(os.path.abspath(exr)),
            "FormatID": lua_q("OpenEXRFormat"),
            "MissingFrames": lua_q("Next Frames"),
        }, pos=pos))
        created.append(name)

    comp = "{\n\tTools = ordered() {\n" + "\n".join(tools) + \
        "\n\t},\n\tActiveTool = " + lua_q(created[0] if created else "") + "\n}\n"
    with open(comp_path, "w") as f:
        f.write(comp)
    return comp_path
