"""De un frame de FigCraft a manifest.json + capas PNG (esquema figma2fusion)."""
import json
import os
import re

CONTAINERS = {"FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "SECTION"}


def slug(name, used):
    base = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")[:48] or "capa"
    if base not in used:
        used.add(base)
        return base
    i = 2
    while "%s_%d" % (base, i) in used:
        i += 1
    out = "%s_%d" % (base, i)
    used.add(out)
    return out


def subtree_has_text(node):
    if node.get("type") == "TEXT":
        return True
    return any(subtree_has_text(c) for c in node.get("children") or [])


def visible_fills(node):
    return [f for f in (node.get("fills") or []) if f.get("visible", True)]


def glass_effect(node):
    for e in node.get("effects") or []:
        if e.get("visible", True) and e.get("type") in ("backgroundBlur", "glass"):
            return e
    return None


def image_fills(node):
    return [f for f in visible_fills(node) if f.get("type") == "image"]


def collect_units(m, frame_id):
    """Ids de los nodos que serán una capa.

    Cada hijo del frame es una unidad. Si un contenedor tiene texto dentro, se
    explota: se conserva el contenedor (si aporta relleno o efectos) y se baja a
    sus hijos para que los textos queden separados y editables en Fusion.
    """
    tree = m.call("get_node", id=frame_id, depth=20)
    units = []

    def walk(node):
        for child in node.get("children") or []:
            if child.get("visible") is False:
                continue
            has_text = subtree_has_text(child)
            if has_text and child.get("type") in CONTAINERS:
                full = m.call("get_node", id=child["id"], depth=0)
                if visible_fills(full) or full.get("effects") or full.get("strokes"):
                    units.append(child["id"])
                walk(child)
            else:
                units.append(child["id"])

    walk(tree)
    return units


def _hex(color, default="#FFFFFF"):
    if not color:
        return default
    if isinstance(color, str):
        return color.upper() if color.startswith("#") else "#" + color.upper()
    if isinstance(color, dict):
        def ch(k):
            return max(0, min(255, round(float(color.get(k, 0)) * 255)))
        return "#%02X%02X%02X" % (ch("r"), ch("g"), ch("b"))
    return default


def _color_at(fills):
    """El color del primer fill sólido visible, como #RRGGBB@NN%."""
    for f in fills:
        if f.get("type") == "solid":
            opacity = f.get("opacity", 1)
            return "%s@%d%%" % (_hex(f.get("color")), round(float(opacity) * 100))
    return None


def _num(value, default=None):
    try:
        return float(str(value).replace("px", "").strip())
    except (TypeError, ValueError):
        return default


def _line_height(node):
    lh = node.get("lineHeight")
    size = _num(node.get("fontSize"), 16.0)
    if isinstance(lh, (int, float)):
        return float(lh)
    n = _num(lh)
    if n:
        return n
    return round(size * 1.2, 2)


def export_layer(m, node_id, dest, scale):
    r = m.call("export", ids=[node_id], format="png", scale=scale,
               includeBoundingBox=True, path=dest)
    if isinstance(r, str):
        raise RuntimeError("export de %s falló: %s" % (node_id, r))
    return r


def _set(m, node_id, fills, effects=None, strokes=None):
    props = {"fills": fills}
    props["effects"] = effects or []
    props["strokes"] = strokes or []
    m.call("set_properties", ids=[node_id], props=props)


def export_glass(m, node, dest, mask_dest, scale):
    """Exporta el vidrio sin el fondo horneado, más su silueta opaca.

    FigCraft hornea el backdrop al exportar una capa con backgroundBlur/glass.
    Limpiando fills/efectos/strokes la misma geometría sale como silueta limpia:
    se usa para el Bitmap que enmascara el Blur del comp.
    """
    fills = visible_fills(node)
    color = "#FFFFFF"
    opacity = 0.15
    for f in fills:
        if f.get("type") == "solid":
            color = _hex(f.get("color"))
            opacity = float(f.get("opacity", 1))
            break
    _set(m, node["id"], [{"type": "solid", "color": "#FFFFFF", "opacity": 1, "visible": True}])
    export_layer(m, node["id"], mask_dest, scale)
    m.call("undo")
    _set(m, node["id"], [{"type": "solid", "color": color, "opacity": opacity, "visible": True}])
    export_layer(m, node["id"], dest, scale)
    m.call("undo")
    return {"radius": float((glass_effect(node) or {}).get("radius") or 8.0),
            "mask": mask_dest,
            "fill": color,
            "opacity": opacity,
            "figma_glass_effect": any(e.get("type") == "glass"
                                      for e in node.get("effects") or [])}


def build_manifest(m, src, frame, outdir, scale=1.0):
    fw, fh = float(frame["width"]), float(frame["height"])
    capas = os.path.join(outdir, "capas")
    os.makedirs(capas, exist_ok=True)

    m.call("open_file", path=src)
    frame_node = m.call("get_node", id=frame["id"], depth=0)
    doc = m.call("inspect_document", depth=0)
    doc_images = doc.get("images", 0) if isinstance(doc, dict) else 0
    units = collect_units(m, frame["id"])

    layers, warnings = [], []
    used = set()
    for z, nid in enumerate(units):
        node = m.call("get_node", id=nid, depth=0)
        if node.get("visible") is False:
            continue
        if image_fills(node) and not doc_images:
            raise RuntimeError(
                "La capa %r usa una imagen pero el documento no tiene ninguna "
                "embebida: FigCraft exportaría un placeholder de rayas grises.\n"
                "Convertí de nuevo incluyendo la carpeta images/ junto al JSON."
                % node.get("name"))
        b = node["absoluteBounds"]
        name = slug(node.get("name"), used)
        png_rel = "capas/%02d_%s.png" % (z + 1, name)
        png_abs = os.path.join(outdir, png_rel)
        entry = {
            "name": node.get("name"),
            "figma_id": str(node["id"]),
            "figma_type": node.get("type"),
            "z": z,
            "opacity": node.get("opacity", 1) or 1,
            "width": b["width"],
            "height": b["height"],
            "center_x": b["x"] + b["width"] / 2.0,
            "center_y": b["y"] + b["height"] / 2.0,
            "rotation_deg": node.get("rotation", 0) or 0,
            "blend_mode": node.get("blendMode") or "normal",
            "png": png_rel,
            "png_rect": {"x": b["x"], "y": b["y"], "w": b["width"], "h": b["height"]},
        }

        glass = glass_effect(node)
        if glass:
            mask_rel = "capas/%02d_%s_mask.png" % (z + 1, name)
            g = export_glass(m, node, png_abs, os.path.join(outdir, mask_rel), scale)
            g["mask"] = mask_rel
            entry["glass"] = g
        else:
            export_layer(m, node["id"], png_abs, scale)

        cr = node.get("cornerRadius")
        if cr:
            entry["corner_radius"] = cr

        if node.get("type") == "TEXT":
            fills = visible_fills(node)
            entry["text"] = {
                "content": node.get("characters") or "",
                "font_family": node.get("fontFamily") or "",
                "font_style": node.get("fontStyle") or "Regular",
                "font_size_px": _num(node.get("fontSize"), 16.0),
                "color": _color_at(fills) or "#FFFFFF@100%",
                "align_h": (node.get("textAlign") or "left").lower(),
                "align_v": (node.get("textAlignVertical") or "top").lower(),
                "line_height_px": _line_height(node),
                "letter_spacing": _num(node.get("letterSpacing"), 0.0),
            }

        effects = [e for e in (node.get("effects") or [])
                   if e.get("type") not in ("backgroundBlur", "glass")]
        if effects:
            entry["effects"] = effects
        layers.append(entry)

    bg = None
    for f in visible_fills(frame_node):
        if f.get("type") == "solid":
            bg = _hex(f.get("color"), "#FFFFFF")
            break
    manifest = {
        "source": {
            "file_key": os.path.basename(src),
            "frame_id": str(frame["id"]),
            "frame_name": frame["name"],
        },
        "frame": {"width": fw, "height": fh, "background_fill": bg},
        "layers": layers,
    }
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    export_layer(m, frame["id"], os.path.join(outdir, "referencia.png"), scale)
    return manifest, warnings
