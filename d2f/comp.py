"""Emite el .comp de Fusion (y el Text+ alternativo) desde el manifest."""
import os
import re
import shutil
import subprocess


def lua_q(s):
    return '"' + str(s).replace("\\", "/").replace('"', '\\"') + '"'


def exr_of(png, exr):
    """PNG con alpha -> EXR: el Loader de Resolve solo lee EXR."""
    for cmd in (["magick", png, exr], ["convert", png, exr],
                ["ffmpeg", "-y", "-i", png, exr]):
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode == 0 and os.path.isfile(exr):
                return True
        except Exception:
            continue
    return False


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


def textplus_block(lay, fw, fh):
    t = lay["text"]
    size = round(float(t.get("font_size_px") or 17) / fw, 6)
    r, g, b = _hex_of(t.get("color"))
    cx, cy = lay["center_x"], lay["center_y"]
    name = "TextPlus_%s" % str(lay["figma_id"]).replace(":", "_")
    return (
        "{} = TextPlus {{\n\t\tCtrlWZoom = false,\n\t\tInputs = {{\n"
        "\t\t\tWidth = Input {{ Value = {fw}, }},\n"
        "\t\t\tHeight = Input {{ Value = {fh}, }},\n"
        "\t\t\tUseFrameFormatSettings = Input {{ Value = 1, }},\n"
        "\t\t\tStyledText = Input {{ Value = {txt} }},\n"
        "\t\t\tFont = Input {{ Value = {font} }},\n"
        "\t\t\tStyle = Input {{ Value = {style} }},\n"
        "\t\t\tSize = Input {{ Value = {size} }},\n"
        "\t\t\tRed1 = Input {{ Value = {r} }},\n"
        "\t\t\tGreen1 = Input {{ Value = {g} }},\n"
        "\t\t\tBlue1 = Input {{ Value = {b} }},\n"
        "\t\t\tAlpha1 = Input {{ Value = 1 }},\n"
        "\t\t\tVerticalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\tHorizontalJustificationNew = Input {{ Value = 3 }},\n"
        "\t\t\tCenter = Input {{ Value = {{{cx}, {cy}}} }},\n"
        "\t\t\tAngle = Input {{ Value = {ang} }},\n"
        "\t\t}},\n\t}}"
    ).format(name, fw=fw, fh=fh, txt=lua_q(t.get("content", "")),
             font=lua_q(t.get("font_family") or ""),
             style=lua_q(t.get("font_style") or ""),
             size=size, r=r, g=g, b=b,
             cx=round(cx / fw, 6), cy=round(1.0 - cy / fh, 6),
             ang=lay.get("rotation_deg") or 0)


def generate_comp(manifest, outdir, log=print):
    fw = float(manifest["frame"]["width"])
    fh = float(manifest["frame"]["height"])
    fdir = os.path.join(outdir, "fusion")
    os.makedirs(fdir, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", manifest["source"]["frame_name"]) or "comp"
    comp_path = os.path.join(fdir, safe + ".comp")

    tools = [tool_block("MediaIn1", "MediaIn", {
        "GlobalIn": "1", "GlobalOut": "1000"}, pos=(0, 0))]
    loaders = {}
    for i, lay in enumerate(manifest["layers"]):
        png = os.path.join(outdir, lay["png"])
        exr = os.path.join(fdir, os.path.basename(png)[:-4] + ".exr")
        if not exr_of(png, exr):
            log("  aviso: no pude convertir %s a EXR; la capa %r queda fuera del comp"
                % (png, lay.get("name")))
            continue
        lname = "Loader%02d" % i
        loaders[lay["figma_id"]] = lname
        tools.append(tool_block(lname, "Loader", {
            "Filename": lua_q(os.path.abspath(exr)),
            "FormatID": lua_q("OpenEXRFormat"),
            "MissingFrames": lua_q("Next Frames"),
        }, pos=(0, 80 + i * 60)))

    def center_of(lay):
        r = lay["png_rect"]
        cx, cy = r["x"] + r["w"] / 2.0, r["y"] + r["h"] / 2.0
        return round(cx / fw, 6), round(1.0 - cy / fh, 6)

    stack = "MediaIn1"
    glass_i = merge_i = 0
    order = []
    for i, lay in enumerate(manifest["layers"]):
        lid = lay["figma_id"]
        if lid not in loaders:
            continue
        if lay.get("glass"):
            glass_i += 1
            mask_rel = (lay["glass"] or {}).get("mask")
            mask_exr = None
            if mask_rel:
                mask_png = os.path.join(outdir, mask_rel)
                mask_exr = os.path.join(fdir, os.path.basename(mask_png)[:-4] + ".exr")
                if not exr_of(mask_png, mask_exr):
                    mask_exr = None
            bm = "BitmapGlass%d" % glass_i
            ml = "LoaderMask%d" % glass_i
            if mask_exr:
                tools.append(tool_block(ml, "Loader", {
                    "Filename": lua_q(os.path.abspath(mask_exr)),
                    "FormatID": lua_q("OpenEXRFormat"),
                    "MissingFrames": lua_q("Next Frames"),
                }, pos=(-200, 80 + i * 60)))
                tools.append(tool_block(bm, "Bitmap", {},
                                        {"Input": (ml, "Output")},
                                        pos=(-200, 140 + i * 60)))
            else:
                tools.append(tool_block(bm, "Bitmap", {},
                                        {"Input": (loaders[lid], "Output")},
                                        pos=(-200, 140 + i * 60)))
            radius = float((lay["glass"] or {}).get("radius") or 8.0)
            bl = "BlurGlass%d" % glass_i
            tools.append(tool_block(bl, "Blur", {
                "XBlurSize": radius * 2.0, "YBlurSize": radius * 2.0,
                "BlurType": "0"}, {"Input": (stack, "Output"), "Mask": (bm, "Mask")},
                pos=(140, 80 + i * 60)))
            stack = bl
            order.append(bl)
        merge_i += 1
        mg = "Merge%02d" % merge_i
        tools.append(tool_block(mg, "Merge", {
            "Center": center_of(lay), "Angle": lay.get("rotation_deg") or 0,
            "Size": "1.0", "Blend": "1.0"},
            {"Background": (stack, "Output"),
             "Foreground": (loaders[lid], "Output")},
            pos=(320, 80 + i * 60)))
        stack = mg
        order.append(mg)

    comp = "{\n\tTools = ordered() {\n" + "\n".join(tools) + \
        "\n\t},\n\tActiveTool = " + lua_q(order[-1] if order else "MediaIn1") + "\n}\n"
    with open(comp_path, "w") as f:
        f.write(comp)

    snippets = [textplus_block(lay, fw, fh) for lay in manifest["layers"] if lay.get("text")]
    if snippets:
        with open(os.path.join(fdir, "textplus_alternativo.txt"), "w") as f:
            f.write("\n\n".join(snippets))
    return comp_path
