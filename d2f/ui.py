"""Interfaz web local: arrastrar archivo → ver resultado y carpeta de salida."""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Imports compatibles con pyinstaller (standalone) y módulo normal
try:
    from . import __version__
    from .cli import OUT_BASE, convert
except ImportError:
    # Modo standalone (pyinstaller)
    import d2f
    __version__ = d2f.__version__
    from d2f.cli import OUT_BASE, convert

# En pyinstaller, __file__ apunta al directorio temporal de extracción.
# Detectamos si estamos en modo frozen y usamos el directorio real del repo si existe.
if getattr(sys, "frozen", False):
    # Modo pyinstaller: no hay .git, la actualización no aplica
    REPO_DIR = None
else:
    REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git_update():
    """git pull --ff-only en el repo. Devuelve (ok, mensaje)."""
    if not REPO_DIR:
        return False, "Actualización no disponible en modo ejecutable (pyinstaller)."
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        return False, "No es un repositorio git."
    try:
        r = subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"],
                           capture_output=True, text=True, timeout=180)
        msg = (r.stdout + r.stderr).strip() or "(sin salida)"
        return r.returncode == 0, msg
    except Exception as e:
        return False, str(e)

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>design2fusion</title>
<style>
  :root { color-scheme: dark; }
  body { font: 15px/1.5 system-ui, sans-serif; background: #11151c; color: #e6e9ef;
          max-width: 900px; margin: 0 auto; padding: 32px 20px 60px; min-height: 100vh; }
  header { text-align: center; margin-bottom: 32px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  h1 { font-size: 28px; margin: 0 0 8px; font-weight: 700; }
  .tagline { color: #8b95a7; font-size: 14px; }

  /* Version bar */
  .version-bar {
    background: rgba(232,69,44,.12); border-bottom: 1px solid #2a3342;
    padding: 8px 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .version-bar .ver { font-size: 12px; font-weight: 600; color: #c8d0e0; }
  .version-bar .btn-update {
    background: transparent; border: 1px solid #2a3342; color: #9aa5b8;
    padding: 6px 12px; border-radius: 6px; font-size: 13px; cursor: pointer;
    transition: border-color .1s, color .1s, background .1s;
  }
  .version-bar .btn-update:hover { border-color: #e8452c; color: #e8452c; background: rgba(232,69,44,.1); }

  /* DROP ZONE */
  .drop-zone {
    border: 2px dashed #2a3342; border-radius: 16px;
    background: linear-gradient(180deg, #161c25 0%, #11151c 100%);
    padding: 48px 24px; text-align: center; cursor: pointer;
    transition: border-color .15s, background .15s, box-shadow .15s;
    position: relative;
  }
  .drop-zone:hover,
  .drop-zone.drag-active {
    border-color: #e8452c;
    background: linear-gradient(180deg, #1e2530 0%, #161c25 100%);
    box-shadow: 0 0 0 1px #e8452c, 0 8px 32px rgba(232,69,44,.15);
  }
  .drop-zone input[type=file] { display: none; }
  .drop-icon { font-size: 48px; line-height: 1; margin-bottom: 12px; display: block; }
  .drop-title { font-size: 18px; font-weight: 600; margin-bottom: 6px; }
  .drop-hint { color: #8b95a7; font-size: 13px; }
  .drop-formats { margin-top: 16px; font-size: 12px; color: #6b7890; }
  .drop-formats code { background: #0e131a; padding: 2px 6px; border-radius: 4px; margin: 0 2px; }

  /* OR DIVIDER */
  .or-divider { display: flex; align-items: center; gap: 12px; margin: 24px 0; color: #5a6578; font-size: 13px; }
  .or-divider::before, .or-divider::after { content: ""; flex: 1; height: 1px; background: #2a3342; }

  /* PATH INPUT */
  .path-row { display: flex; gap: 10px; }
  .path-row input { flex: 1; padding: 12px 14px; border-radius: 10px;
    border: 1px solid #2a3342; background: #0e131a; color: #e6e9ef; font-size: 14px; }
  .path-row input:focus { outline: none; border-color: #e8452c; box-shadow: 0 0 0 2px rgba(232,69,44,.2); }

  /* OPTIONS */
  .options { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 20px; }
  .opt { }
  .opt label { display: block; font-size: 12px; color: #9aa5b8; margin-bottom: 6px; }
  .opt input { width: 100%; padding: 10px 12px; border-radius: 8px;
    border: 1px solid #2a3342; background: #0e131a; color: #e6e9ef; }

  /* BUTTON */
  .btn-row { margin-top: 24px; text-align: center; }
  button#go {
    padding: 14px 36px; border-radius: 10px; border: 0;
    background: #e8452c; color: #fff; font-weight: 600; font-size: 15px; cursor: pointer;
    transition: background .1s, transform .05s;
  }
  button#go:hover:not(:disabled) { background: #ff5a3d; }
  button#go:active:not(:disabled) { transform: scale(.98); }
  button#go:disabled { opacity: .5; cursor: progress; }

  /* OUTPUT SECTION */
  .output-section { margin-top: 36px; display: none; }
  .output-section.visible { display: block; animation: fadeIn .2s ease; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

  .out-card {
    border: 1px solid #2a3342; border-radius: 14px;
    background: linear-gradient(180deg, #161c25 0%, #11151c 100%);
    overflow: hidden;
  }
  .out-header {
    background: rgba(232,69,44,.12); border-bottom: 1px solid #2a3342;
    padding: 16px 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .out-badge { background: #e8452c; color: #fff; font-size: 11px; font-weight: 700;
    padding: 4px 10px; border-radius: 999px; text-transform: uppercase; letter-spacing: .5px; }
  .out-path { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: #c8d0e0; flex: 1; min-width: 200px; word-break: break-all; }
  .out-open { margin-left: auto; }
  .btn-link {
    background: transparent; border: 1px solid #2a3342; color: #9aa5b8;
    padding: 8px 14px; border-radius: 8px; font-size: 13px; cursor: pointer;
    transition: border-color .1s, color .1s, background .1s;
  }
  .btn-link:hover { border-color: #e8452c; color: #e8452c; background: rgba(232,69,44,.1); }
  .btn-link:disabled { opacity: .4; cursor: not-allowed; }

  .out-body { padding: 20px; display: grid; gap: 16px; }
  .out-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .thumb { position: relative; border-radius: 8px; overflow: hidden; background: #0e131a; aspect-ratio: 16/9; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb .label { position: absolute; bottom: 0; left: 0; right: 0; padding: 6px 8px;
    background: linear-gradient(0deg, rgba(0,0,0,.85), transparent); font-size: 11px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .out-json { background: #0e131a; border: 1px solid #2a3342; border-radius: 10px;
    padding: 14px; overflow: auto; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; max-height: 300px; }
  .err { color: #ff8a7a; background: #2a1010; border: 1px solid #4a1a1a; padding: 14px; border-radius: 10px; }

  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid transparent; border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; margin-right: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style></head><body>
<header>
  <h1>design2fusion</h1>
  <p class="tagline">Figma · Penpot · FigCraft → nodos de Fusion (DaVinci Resolve)</p>
  <div class="version-bar">
    <span class="ver">{{VER}}</span>
    <button class="btn-update" id="updateBtn">Actualizar</button>
  </div>
</header>

<main>
  <!-- DROP ZONE -->
  <div class="drop-zone" id="dropZone" role="button" tabindex="0" aria-label="Soltar archivo de diseño">
    <span class="drop-icon" aria-hidden="true">📁</span>
    <div class="drop-title">Arrastra tu archivo aquí</div>
    <div class="drop-hint">o haz clic para seleccionar</div>
    <div class="drop-formats">Formatos: <code>.figcraft</code> <code>.penpot</code> <code>.fig</code> <code>.json</code> (con carpeta <code>images/</code>) · URL de Figma</div>
    <input type="file" id="fileInput" name="file" accept=".figcraft,.penpot,.fig,.json">
  </div>

  <!-- OR -->
  <div class="or-divider"><span>O una ruta local</span></div>

  <!-- PATH INPUT -->
  <div class="path-row">
    <input type="text" id="pathInput" placeholder="/home/alan/Descargas/mi-diseño.figcraft" aria-label="Ruta del archivo en el equipo">
  </div>

  <!-- OPTIONS -->
  <div class="options">
    <div class="opt">
      <label>Frame (nombre o id, opcional)</label>
      <input type="text" id="frameInput" placeholder="Slide 16:9 - 1">
    </div>
    <div class="opt">
      <label>Escala PNG</label>
      <input type="number" id="scaleInput" value="1" step="0.5" min="0.1" max="8">
    </div>
  </div>

  <!-- BUTTON -->
  <div class="btn-row">
    <button id="go" type="button">Convertir</button>
  </div>

  <!-- OUTPUT -->
  <section class="output-section" id="outSection" aria-live="polite"></section>
</main>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const pathInput = document.getElementById('pathInput');
const frameInput = document.getElementById('frameInput');
const scaleInput = document.getElementById('scaleInput');
const goBtn = document.getElementById('go');
const outSection = document.getElementById('outSection');
const updateBtn = document.getElementById('updateBtn');

let currentVersion = "0.2.0";

/* Check for updates */
async function checkUpdate() {
  try {
    const [ok, msg] = await fetch('/update', { method: 'POST' }).then(r => r.json());
    if (ok) {
      currentVersion = msg.split(' ')[0];  // msg = "ok v0.2.1"
      document.querySelector('.ver').textContent = currentVersion;
      alert("Actualizado a " + currentVersion + "\n" + msg);
    } else {
      alert("Error al actualizar:\n" + msg);
    }
  } catch (e) {
    alert("Error al conectar con el servidor de actualización");
  }
}

async function convertFile() {
  const file = fileInput.files[0];
  const path = pathInput.value.trim();
  if (!file && !path) { alert('Seleccioná un archivo o poné una ruta'); return; }

  goBtn.disabled = true;
  goBtn.innerHTML = '<span class="spinner"></span>Convirtiendo…';
  outSection.classList.remove('visible');
  outSection.innerHTML = '';

  const form = new FormData();
  if (file) form.append('file', file);
  if (path) form.append('path', path);
  const frame = frameInput.value.trim();
  if (frame) form.append('frame', frame);
  form.append('scale', scaleInput.value);

  try {
    const res = await fetch('/convert', { method: 'POST', body: form });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Falló la conversión');
    renderOutput(data);
  } catch (err) {
    outSection.innerHTML = `<div class="out-card"><div class="out-body"><div class="err">${htmlEscape(err.message)}</div></div></div>`;
    outSection.classList.add('visible');
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = 'Convertir';
  }
}

function renderOutput(data) {
  const frameName = data.frame?.name || 'frame';
  const outDir = data.outdir;
  const ref = data.referencia;
  const capas = data.capas || [];
  const json = JSON.stringify(data, null, 1);

  let html = `
    <div class="out-card">
      <div class="out-header">
        <span class="out-badge">Listo</span>
        <span class="out-path" title="${htmlEscape(outDir)}">${htmlEscape(outDir)}</span>
        <button class="btn-link" id="openFolderBtn" ${!canOpenFolder() ? 'disabled' : ''}>Abrir carpeta</button>
      </div>
      <div class="out-body">`;

  if (ref) {
    html += `<img src="/preview?p=${encodeURIComponent(ref)}" alt="Referencia" style="width:100%;border-radius:10px;border:1px solid #2a3342;margin-bottom:16px;">`;
  }
  if (capas.length) {
    html += '<div class="out-grid">';
    capas.forEach(c => {
      const name = c.split('/').pop();
      html += `<div class="thumb"><img src="/preview?p=${encodeURIComponent(c)}" alt="${htmlEscape(name)}"><span class="label">${htmlEscape(name)}</span></div>`;
    });
    html += '</div>';
  }
  html += `<details style="margin-top:16px;"><summary style="cursor:pointer;color:#9aa5b8;font-size:13px;">Ver JSON completo</summary>
    <div class="out-json">${htmlEscape(json)}</div></details>`;

  html += '</div></div>';
  outSection.innerHTML = html;
  outSection.classList.add('visible');

  // Abrir carpeta (solo funciona si el navegador permite file:// o usamos un endpoint)
  document.getElementById('openFolderBtn')?.addEventListener('click', () => {
    fetch('/open-folder?p=' + encodeURIComponent(outDir))
      .then(r => r.json())
      .then(j => { if (!j.ok) alert(j.error || 'No se pudo abrir'); });
  });
}

function canOpenFolder() {
  // El endpoint /open-folder siempre existe, el botón se habilita siempre
  return true;
}

function htmlEscape(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&','<':'<','>':'>','"':'"',"'":'''})[c]);
}

goBtn.addEventListener('click', convertFile);
pathInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });
frameInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });
scaleInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });

/* Actualizar button */
updateBtn.addEventListener('click', checkUpdate);

/* On page load */
window.addEventListener('load', () => {
  document.querySelector('.ver').textContent = currentVersion;
});

  @media (max-width: 640px) {
    .options { grid-template-columns: 1fr; }
    .path-row { flex-direction: column; }
  }
</style></head><body>
<header>
  <h1>design2fusion</h1>
  <p class="tagline">Figma · Penpot · FigCraft → nodos de Fusion (DaVinci Resolve)</p>
</header>

<main>
  <!-- DROP ZONE -->
  <div class="drop-zone" id="dropZone" role="button" tabindex="0" aria-label="Soltar archivo de diseño">
    <span class="drop-icon" aria-hidden="true">📁</span>
    <div class="drop-title">Arrastra tu archivo aquí</div>
    <div class="drop-hint">o haz clic para seleccionar</div>
    <div class="drop-formats">Formatos: <code>.figcraft</code> <code>.penpot</code> <code>.fig</code> <code>.json</code> (con carpeta <code>images/</code>) · URL de Figma</div>
    <input type="file" id="fileInput" name="file" accept=".figcraft,.penpot,.fig,.json">
  </div>

  <!-- OR -->
  <div class="or-divider"><span>O una ruta local</span></div>

  <!-- PATH INPUT -->
  <div class="path-row">
    <input type="text" id="pathInput" placeholder="/home/alan/Descargas/mi-diseño.figcraft" aria-label="Ruta del archivo en el equipo">
  </div>

  <!-- OPTIONS -->
  <div class="options">
    <div class="opt">
      <label>Frame (nombre o id, opcional)</label>
      <input type="text" id="frameInput" placeholder="Slide 16:9 - 1">
    </div>
    <div class="opt">
      <label>Escala PNG</label>
      <input type="number" id="scaleInput" value="1" step="0.5" min="0.1" max="8">
    </div>
  </div>

  <!-- BUTTON -->
  <div class="btn-row">
    <button id="go" type="button">Convertir</button>
  </div>

  <!-- OUTPUT -->
  <section class="output-section" id="outSection" aria-live="polite"></section>
</main>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const pathInput = document.getElementById('pathInput');
const frameInput = document.getElementById('frameInput');
const scaleInput = document.getElementById('scaleInput');
const goBtn = document.getElementById('go');
const outSection = document.getElementById('outSection');

// Drag & drop visual
['dragenter', 'dragover'].forEach(e => dropZone.addEventListener(e, ev => {
  ev.preventDefault(); dropZone.classList.add('drag-active');
}));
['dragleave', 'drop'].forEach(e => dropZone.addEventListener(e, ev => {
  ev.preventDefault(); dropZone.classList.remove('drag-active');
}));
dropZone.addEventListener('drop', ev => {
  const f = ev.dataTransfer.files[0];
  if (f) { fileInput.files = ev.dataTransfer.files; pathInput.value = ''; updateDropLabel(f.name); }
});
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); fileInput.click(); } });
fileInput.addEventListener('change', () => { if (fileInput.files[0]) { updateDropLabel(fileInput.files[0].name); pathInput.value = ''; } });

function updateDropLabel(name) {
  const title = dropZone.querySelector('.drop-title');
  const hint = dropZone.querySelector('.drop-hint');
  title.textContent = name;
  hint.textContent = 'Listo para convertir';
  dropZone.style.borderColor = '#e8452c';
  dropZone.style.background = 'linear-gradient(180deg, #1e2530 0%, #161c25 100%)';
}

async function convertFile() {
  const file = fileInput.files[0];
  const path = pathInput.value.trim();
  if (!file && !path) { alert('Seleccioná un archivo o poné una ruta'); return; }

  goBtn.disabled = true;
  goBtn.innerHTML = '<span class="spinner"></span>Convirtiendo…';
  outSection.classList.remove('visible');
  outSection.innerHTML = '';

  const form = new FormData();
  if (file) form.append('file', file);
  if (path) form.append('path', path);
  const frame = frameInput.value.trim();
  if (frame) form.append('frame', frame);
  form.append('scale', scaleInput.value);

  try {
    const res = await fetch('/convert', { method: 'POST', body: form });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Falló la conversión');
    renderOutput(data);
  } catch (err) {
    outSection.innerHTML = `<div class="out-card"><div class="out-body"><div class="err">${htmlEscape(err.message)}</div></div></div>`;
    outSection.classList.add('visible');
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = 'Convertir';
  }
}

function renderOutput(data) {
  const frameName = data.frame?.name || 'frame';
  const outDir = data.outdir;
  const ref = data.referencia;
  const capas = data.capas || [];
  const json = JSON.stringify(data, null, 1);

  let html = `
    <div class="out-card">
      <div class="out-header">
        <span class="out-badge">Listo</span>
        <span class="out-path" title="${htmlEscape(outDir)}">${htmlEscape(outDir)}</span>
        <button class="btn-link" id="openFolderBtn" ${!canOpenFolder() ? 'disabled' : ''}>Abrir carpeta</button>
      </div>
      <div class="out-body">`;

  if (ref) {
    html += `<img src="/preview?p=${encodeURIComponent(ref)}" alt="Referencia" style="width:100%;border-radius:10px;border:1px solid #2a3342;margin-bottom:16px;">`;
  }
  if (capas.length) {
    html += '<div class="out-grid">';
    capas.forEach(c => {
      const name = c.split('/').pop();
      html += `<div class="thumb"><img src="/preview?p=${encodeURIComponent(c)}" alt="${htmlEscape(name)}"><span class="label">${htmlEscape(name)}</span></div>`;
    });
    html += '</div>';
  }
  html += `<details style="margin-top:16px;"><summary style="cursor:pointer;color:#9aa5b8;font-size:13px;">Ver JSON completo</summary>
    <div class="out-json">${htmlEscape(json)}</div></details>`;

  html += '</div></div>';
  outSection.innerHTML = html;
  outSection.classList.add('visible');

  // Abrir carpeta (solo funciona si el navegador permite file:// o usamos un endpoint)
  document.getElementById('openFolderBtn')?.addEventListener('click', () => {
    fetch('/open-folder?p=' + encodeURIComponent(outDir))
      .then(r => r.json())
      .then(j => { if (!j.ok) alert(j.error || 'No se pudo abrir'); });
  });
}

function canOpenFolder() {
  // El endpoint /open-folder siempre existe, el botón se habilita siempre
  return true;
}

function htmlEscape(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&','<':'<','>':'>','"':'"',"'":'''})[c]);
}

goBtn.addEventListener('click', convertFile);
pathInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });
frameInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });
scaleInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') convertFile(); });
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
            body = PAGE.replace("{{VER}}", __version__)
            body = body.replace("{{OUT}}", html.escape(OUT_BASE))
            return self._send(200, body)
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
        if u.path == "/open-folder":
            p = parse_qs(u.query).get("p", [""])[0]
            real = os.path.realpath(p)
            if not real.startswith(os.path.realpath(OUT_BASE)) or not os.path.isdir(real):
                return self._json(404, {"ok": False, "error": "carpeta no permitida"})
            try:
                subprocess.Popen(["xdg-open", real], start_new_session=True)
                return self._json(200, {"ok": True})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})
        return self._send(404, "no encontrado")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/convert":
            return self._handle_convert()
        if u.path == "/update":
            ok, msg = git_update()
            return self._json(200, {"ok": ok, "message": msg})
        return self._json(404, {"ok": False, "error": "ruta desconocida"})

    def _handle_convert(self):
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


if __name__ == "__main__":
    serve()