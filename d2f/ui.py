"""Interfaz web local mínima: subir un archivo y ver el resultado."""
import html
import json
import os
import re
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .cli import OUT_BASE, convert

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>design2fusion</title>
<style>
 :root { color-scheme: dark; }
 body { font: 15px/1.5 system-ui, sans-serif; background: #11151c; color: #e6e9ef;
        max-width: 860px; margin: 40px auto; padding: 0 20px; }
 h1 { font-size: 22px; margin: 0 0 4px; }
 p.sub { color: #8b95a7; margin: 0 0 24px; }
 form { border: 1px dashed #2a3342; border-radius: 12px; padding: 24px; background: #161c25; }
 label { display: block; font-size: 13px; color: #9aa5b8; margin: 14px 0 6px; }
 input[type=text], input[type=number] { width: 100%; padding: 9px 10px; border-radius: 8px;
   border: 1px solid #2a3342; background: #0e131a; color: #e6e9ef; }
 .row { display: flex; gap: 12px; } .row > div { flex: 1; }
 button { margin-top: 18px; padding: 10px 18px; border-radius: 8px; border: 0;
   background: #e8452c; color: #fff; font-weight: 600; cursor: pointer; }
 button:disabled { opacity: .5; cursor: progress; }
 pre { background: #0e131a; border: 1px solid #2a3342; border-radius: 10px;
   padding: 14px; overflow: auto; font-size: 12.5px; }
 img { max-width: 100%; border-radius: 10px; border: 1px solid #2a3342; margin-top: 10px; }
 .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
 .err { color: #ff8a7a; }
 code { background: #0e131a; padding: 2px 5px; border-radius: 4px; }
</style></head><body>
<h1>design2fusion</h1>
<p class="sub">Figma · Penpot · FigCraft → capas, <code>.comp</code> y kit de <code>.setting</code> para DaVinci Resolve.
Salida en <code>{{OUT}}</code>.</p>
<form id="f">
  <label>Archivo (.figcraft, .penpot, .fig o .json de Figma con la carpeta images/)</label>
  <input type="file" name="file" id="file">
  <label>…o una ruta del equipo</label>
  <input type="text" name="path" placeholder="/home/alan/Descargas/diseño.figcraft">
  <div class="row">
    <div><label>Frame (nombre o id, opcional)</label><input type="text" name="frame"></div>
    <div><label>Escala PNG</label><input type="number" name="scale" value="1" step="0.5" min="0.1" max="8"></div>
  </div>
  <button id="go">Convertir</button>
</form>
<div id="out"></div>
<script>
const f = document.getElementById('f'), go = document.getElementById('go'), out = document.getElementById('out');
f.addEventListener('submit', async (e) => {
  e.preventDefault(); out.innerHTML = ''; go.disabled = true;
  try {
    const r = await fetch('/convert', { method: 'POST', body: new FormData(f) });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'falló');
    out.innerHTML = `<h2>Listo</h2><pre>${JSON.stringify(j, null, 1)}</pre>`;
    if (j.referencia) out.innerHTML += `<img src="/preview?p=${encodeURIComponent(j.referencia)}">`;
    if (j.capas && j.capas.length) {
      out.innerHTML += '<div class="grid">' + j.capas.map(c =>
        `<img src="/preview?p=${encodeURIComponent(c)}" title="${c}">`).join('') + '</div>';
    }
  } catch (err) { out.innerHTML = `<pre class="err">${err.message}</pre>`; }
  finally { go.disabled = false; }
});
</script></body></html>
"""


def parse_multipart(body, ctype):
    m = re.search(r'boundary="?([^";]+)"?', ctype or "")
    if not m:
        raise ValueError("petición sin boundary multipart")
    boundary = m.group(1).encode()
    fields, files = {}, {}
    for part in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        raw_head, data = part.split(b"\r\n\r\n", 1)
        head = raw_head.decode("utf-8", "replace")
        if 'name="' not in head:
            continue
        name = re.search(r'name="([^"]*)"', head).group(1)
        fn = re.search(r'filename="([^"]*)"', head)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        if fn and fn.group(1):
            files[name] = (os.path.basename(fn.group(1)), data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE.replace("{{OUT}}", html.escape(OUT_BASE)))
        if u.path == "/preview":
            p = parse_qs(u.query).get("p", [""])[0]
            real = os.path.realpath(p)
            if not real.startswith(os.path.realpath(OUT_BASE)) or not os.path.isfile(real):
                return self._send(404, "no encontrado")
            ext = os.path.splitext(real)[1].lower()
            ctype = {".png": "image/png", ".jpg": "image/jpeg",
                     ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            with open(real, "rb") as f:
                return self._send(200, f.read(), ctype)
        return self._send(404, "no encontrado")

    def do_POST(self):
        if urlparse(self.path).path != "/convert":
            return self._json(404, {"ok": False, "error": "ruta desconocida"})
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        try:
            fields, files = parse_multipart(body, self.headers.get("Content-Type"))
        except Exception as e:
            return self._json(400, {"ok": False, "error": str(e)})

        tmpdir = None
        try:
            src = (fields.get("path") or "").strip()
            if "file" in files:
                fname, data = files["file"]
                ext = os.path.splitext(fname)[1].lower()
                if not ext:
                    fname += ".figcraft"
                tmpdir = tempfile.mkdtemp(prefix="d2f-ui-")
                src = os.path.join(tmpdir, fname)
                with open(src, "wb") as f:
                    f.write(data)
            if not src:
                return self._json(400, {"ok": False, "error": "falta el archivo"})
            try:
                scale = float(fields.get("scale") or 1)
            except ValueError:
                scale = 1.0
            res = convert(src.rstrip("\r\n"), fields.get("frame") or None,
                          None, None, scale, True, True)
            capas_dir = os.path.join(res["outdir"], "capas")
            res["capas"] = sorted(os.path.join(capas_dir, f)
                                  for f in os.listdir(capas_dir)) if os.path.isdir(capas_dir) else []
            return self._json(200, res)
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": str(e)})
        finally:
            if tmpdir:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)


def serve(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("design2fusion UI → http://127.0.0.1:%d  (Ctrl+C para salir)" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
