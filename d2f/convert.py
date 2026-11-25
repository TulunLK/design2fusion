"""Normaliza la entrada: .figcraft, .penpot, .fig o .json REST -> .figcraft."""
import json
import os
import subprocess

from .mcp import find_cli

SUPPORTED = (".figcraft", ".penpot", ".fig", ".json")


def run_cli(*args):
    cli = find_cli()
    r = subprocess.run([cli, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("figcraft-cli %s falló:\n%s%s"
                           % (" ".join(args), r.stdout, r.stderr))
    return r


def info(path):
    """Metadatos del documento: páginas, frames, imágenes, fuentes faltantes."""
    return json.loads(run_cli("info", path, "--json").stdout)


def frames_of(meta, page=None):
    pages = meta.get("pages") or []
    if page:
        pages = [p for p in pages if p.get("name") == page] or pages
    out = []
    for p in pages:
        for f in p.get("frames") or []:
            out.append(dict(f, page=p.get("name")))
    return out


def pick_frame(meta, name=None, frame_id=None, page=None):
    frames = frames_of(meta, page)
    if not frames:
        raise RuntimeError("El documento no tiene frames de primer nivel.")
    if frame_id is not None:
        want = str(frame_id).split(":")[-1]
        for f in frames:
            if str(f["id"]) == want:
                return f
    if name:
        for f in frames:
            if f["name"].strip().lower() == name.strip().lower():
                return f
        for f in frames:
            if name.strip().lower() in f["name"].lower():
                return f
        raise RuntimeError("No encontré el frame %r. Disponibles: %s"
                           % (name, ", ".join(repr(f["name"]) for f in frames)))
    if len(frames) == 1:
        return frames[0]
    raise RuntimeError("El documento tiene %d frames; elegí uno con --frame: %s"
                       % (len(frames), ", ".join(repr(f["name"]) for f in frames)))


def normalize(src, workdir):
    """Devuelve (ruta al .figcraft, nombre lógico)."""
    ext = os.path.splitext(src)[1].lower()
    if ext == ".figcraft":
        return os.path.abspath(src), os.path.splitext(os.path.basename(src))[0]
    if ext not in SUPPORTED:
        raise ValueError("Formato no soportado: %s (esperaba %s)"
                         % (ext or src, ", ".join(SUPPORTED)))
    if ext == ".json":
        images = os.path.join(os.path.dirname(os.path.abspath(src)), "images")
        if not os.path.isdir(images):
            raise RuntimeError(
                "Falta la carpeta 'images/' junto a %s.\n"
                "Sin ella FigCraft exporta un placeholder de rayas grises sin avisar.\n"
                "Descargá las imágenes del archivo de Figma y volvé a intentar." % src)
    out = os.path.join(workdir, os.path.splitext(os.path.basename(src))[0] + ".figcraft")
    run_cli("convert", os.path.abspath(src), out)
    return out, os.path.splitext(os.path.basename(src))[0]
