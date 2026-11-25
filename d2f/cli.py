"""CLI y pipeline: entrada -> manifest + capas -> .comp + kit."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Imports compatibles con pyinstaller (standalone) y módulo normal
try:
    from . import __version__
    from .comp import generate_comp
    from .convert import info, normalize, pick_frame
    from .mcp import MCP
    from .model import build_manifest
    from .settings import OUT_BASE, write_kit
except ImportError:
    # Modo standalone (pyinstaller)
    import d2f
    __version__ = d2f.__version__
    from d2f.comp import generate_comp
    from d2f.convert import info, normalize, pick_frame
    from d2f.mcp import MCP
    from d2f.model import build_manifest
    from d2f.settings import OUT_BASE, write_kit


def _safe(name):
    return re.sub(r"[^\w\-]+", "_", name or "").strip("_") or "frame"


FIGMA_URL = re.compile(r"^https?://(www\.)?figma\.(com|site)/")


def looks_like_figma(src):
    """URL de Figma o un file key suelto (22 chars alfanuméricos)."""
    return bool(FIGMA_URL.match(src)) or (
        re.fullmatch(r"[A-Za-z0-9]{20,24}", src) is not None)


def _figma(src, frame, out, scale, make_comp, make_kit, log):
    """Delega en figma2fusion (API REST de Figma) y emite comp/kit propios."""
    exe = shutil.which("figma2fusion") or os.path.expanduser("~/.local/bin/figma2fusion")
    if not os.path.exists(exe):
        raise RuntimeError(
            "Para Figma por URL hace falta figma2fusion "
            "(~/.local/bin/figma2fusion). Alternativa: exportá el JSON de Figma "
            "+ la carpeta images/ y pasá el .json.")
    if float(scale or 1.0) != 1.0:
        log("aviso: en Figma REST las capas se piden a 1x; --scale se ignora")
    with tempfile.TemporaryDirectory(prefix="d2f-figma-") as tmp:
        cmd = [exe, src] + (["--frame", str(frame)] if frame else []) + ["-o", tmp]
        log("delegando en figma2fusion (%s) …" % src)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("figma2fusion falló:\n" + (r.stderr or r.stdout).strip())
        mpath = os.path.join(tmp, "manifest.json")
        if not os.path.isfile(mpath):
            raise RuntimeError("figma2fusion no generó manifest.json")
        with open(mpath) as f:
            manifest = json.load(f)
        name = manifest["source"].get("frame_name") or "frame"
        outdir = os.path.abspath(out or os.path.join(OUT_BASE, _safe(name)))
        shutil.copytree(tmp, outdir, dirs_exist_ok=True)

    comp = generate_comp(manifest, outdir, log=log) if make_comp else None
    kit = write_kit(outdir) if make_kit else []
    fr = manifest["frame"]
    return {
        "ok": True,
        "outdir": outdir,
        "frame": {"name": name, "id": manifest["source"].get("frame_id"),
                  "width": fr["width"], "height": fr["height"]},
        "layers": len(manifest["layers"]),
        "glass_layers": sum(1 for l in manifest["layers"] if l.get("glass")),
        "text_layers": sum(1 for l in manifest["layers"] if l.get("text")),
        "manifest": os.path.join(outdir, "manifest.json"),
        "referencia": None,
        "comp": comp,
        "kit": kit,
        "warnings": [],
    }


def convert(src, frame=None, page=None, out=None, scale=1.0,
            make_comp=True, make_kit=True, log=None):
    """Convierte un archivo de diseño en capas + manifest + comp + kit."""
    log = log or (lambda m: None)
    if looks_like_figma(src):
        return _figma(src, frame, out, scale, make_comp, make_kit, log)
    with tempfile.TemporaryDirectory(prefix="d2f-") as tmp:
        log("normalizando %s" % src)
        path, _label = normalize(src, tmp)
        meta = info(path)
        fid = str(frame) if frame and str(frame).isdigit() else None
        fr = pick_frame(meta, name=None if fid else frame, frame_id=fid, page=page)
        outdir = os.path.abspath(out or os.path.join(OUT_BASE, _safe(fr["name"])))
        os.makedirs(outdir, exist_ok=True)
        if meta.get("missingFonts"):
            log("aviso: fuentes faltantes: %s" % ", ".join(meta["missingFonts"]))

        with MCP() as m:
            manifest, warnings = build_manifest(m, path, fr, outdir, scale=scale)

        comp = generate_comp(manifest, outdir, log=log) if make_comp else None
        kit = write_kit(outdir) if make_kit else []
        return {
            "ok": True,
            "outdir": outdir,
            "frame": {"name": fr["name"], "id": fr["id"],
                      "width": fr["width"], "height": fr["height"]},
            "layers": len(manifest["layers"]),
            "glass_layers": sum(1 for l in manifest["layers"] if l.get("glass")),
            "text_layers": sum(1 for l in manifest["layers"] if l.get("text")),
            "manifest": os.path.join(outdir, "manifest.json"),
            "referencia": os.path.join(outdir, "referencia.png"),
            "comp": comp,
            "kit": kit,
            "warnings": warnings,
        }


def _print(res):
    print("frame   : %s (%sx%s)" % (res["frame"]["name"],
                                    res["frame"]["width"], res["frame"]["height"]))
    print("salida  : %s" % res["outdir"])
    print("capas   : %d (%d de vidrio, %d de texto)"
          % (res["layers"], res["glass_layers"], res["text_layers"]))
    print("manifest: %s" % res["manifest"])
    print("comp    : %s" % (res["comp"] or "no generado"))
    print("kit     : %d .setting en %s" % (len(res["kit"]), os.path.join(res["outdir"], "kit")))
    for w in res["warnings"]:
        print("aviso   : %s" % w)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="design2fusion",
        description="Convierte diseños de Figma, Penpot y FigCraft en capas, "
                    "un .comp de Fusion y un kit de macros .setting.")
    ap.add_argument("src", nargs="?",
                    help=".figcraft, .penpot, .fig, .json REST (con images/ al lado), "
                         "URL de Figma o file key")
    ap.add_argument("--frame", help="nombre o id del frame (si hay varios)")
    ap.add_argument("--page", help="página del documento")
    ap.add_argument("-o", "--out", help="carpeta de salida")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="escala de los PNG (1 = tamaño del diseño)")
    ap.add_argument("--no-comp", action="store_true", help="no generar el .comp")
    ap.add_argument("--no-kit", action="store_true", help="no generar el kit de .setting")
    ap.add_argument("--json", action="store_true", help="resumen en JSON")
    ap.add_argument("--desktop", action="store_true", help="abrir la app de escritorio nativa (GTK4)")
    ap.add_argument("--version", action="version", version="design2fusion " + __version__)
    if argv is not None:
        a = ap.parse_args(argv)
    else:
        a = ap.parse_args()

    if a.desktop:
        try:
            from .desktop_ui import main
        except ImportError:
            from d2f.desktop_ui import main
        return main()
    if not a.src:
        ap.error("falta el archivo de entrada")

    try:
        res = convert(a.src, a.frame, a.page, a.out, a.scale,
                      not a.no_comp, not a.no_kit,
                      log=lambda m: print(m, file=sys.stderr))
    except (RuntimeError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        _print(res)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
