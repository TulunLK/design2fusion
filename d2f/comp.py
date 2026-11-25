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


def generate_comp(manifest, outdir, log=print):
    """Escribe <outdir>/fusion/<frame>.comp con nodos sueltos (sin cables)."""
    fw = float(manifest["frame"]["width"])
    fh = float(manifest["frame"]["height"])
    fdir = os.path.join(outdir, "fusion")
    os.makedirs(fdir, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", manifest["source"]["frame_name"]) or "comp"
    comp_path = os.path.join(fdir, safe + ".comp")

    tools, used, created = [], set(), []
    for i, lay in enumerate(manifest["layers"]):
        name = node_name(lay.get("name"), used)
        pos = ((i % GRID_COLS) * GRID_DX, (i // GRID_COLS) * GRID_DY)
        if lay.get("text"):
            tools.append(textplus_block(lay, fw, fh, name, pos=pos))
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
