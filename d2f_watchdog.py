#!/usr/bin/env python3
"""
Watchdog para auto-actualización de design2fusion UI.

Monitorea el directorio `d2f/` y reinicia el servidor HTTP cuando detecta
cambios en archivos .py. Diseñado para correr junto al servidor en el
mismo proceso (thread) o como proceso separado.

Uso:
    python watchdog.py              # lanza servidor + watchdog
    python watchdog.py --serve-only # solo servidor (sin watchdog)
    python watchdog.py --watch-only # solo watchdog (asume servidor externo)
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("ERROR: watchdog no instalado. Ejecutá: pip install watchdog", file=sys.stderr)
    sys.exit(1)

# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------
REPO_DIR = Path(__file__).parent.resolve()
SRC_DIR = REPO_DIR / "d2f"
PORT = 8765
SERVER_SCRIPT = SRC_DIR / "ui.py"


# -----------------------------------------------------------------------------
# Manejo del proceso servidor
# -----------------------------------------------------------------------------
class ServerManager:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return False  # ya corriendo
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_DIR) + ":" + env.get("PYTHONPATH", "")
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "d2f.ui"],
                cwd=REPO_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            print(f"[watchdog] Servidor iniciado (PID {self.proc.pid})")
            # Thread para leer logs del servidor
            threading.Thread(target=self._read_logs, daemon=True).start()
            return True

    def _read_logs(self):
        assert self.proc and self.proc.stdout
        for line in iter(self.proc.stdout.readline, b""):
            sys.stdout.write(f"[server] {line.decode(errors='replace')}")
            sys.stdout.flush()

    def stop(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                print("[watchdog] Deteniendo servidor...")
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
                print("[watchdog] Servidor detenido")
            self.proc = None

    def restart(self):
        print("[watchdog] Reiniciando servidor por cambios en código...")
        self.stop()
        time.sleep(0.5)
        self.start()

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None


# -----------------------------------------------------------------------------
# Event handler para watchdog
# -----------------------------------------------------------------------------
class ChangeHandler(FileSystemEventHandler):
    def __init__(self, server_mgr: ServerManager, debounce=1.0):
        self.server_mgr = server_mgr
        self.debounce = debounce
        self._last_event = 0
        self._timer = None

    def on_any_event(self, event):
        if event.is_directory:
            return
        # Solo .py en d2f/
        if not event.src_path.endswith(".py"):
            return
        try:
            rel = Path(event.src_path).relative_to(SRC_DIR)
        except ValueError:
            return  # fuera de d2f/
        # Ignorar __pycache__ y tests
        if "__pycache__" in rel.parts or rel.parts[0] == "tests":
            return

        now = time.time()
        if now - self._last_event < self.debounce:
            # Reiniciar timer de debounce
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._do_restart)
            self._timer.start()
        else:
            self._last_event = now
            self._do_restart()

    def _do_restart(self):
        self._last_event = time.time()
        self.server_mgr.restart()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def wait_for_server(timeout=15):
    import urllib.request
    url = f"http://127.0.0.1:{PORT}/"
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    import argparse
    global PORT
    parser = argparse.ArgumentParser(description="design2fusion watchdog")
    parser.add_argument("--serve-only", action="store_true", help="Solo servidor, sin watchdog")
    parser.add_argument("--watch-only", action="store_true", help="Solo watchdog, servidor externo")
    parser.add_argument("--port", type=int, default=PORT, help="Puerto del servidor")
    args = parser.parse_args()

    PORT = args.port

    server_mgr = ServerManager()

    # Manejo de señales para limpieza
    def handle_signal(signum, frame):
        print("\n[watchdog] Señal recibida, cerrando...")
        server_mgr.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not args.watch_only:
        server_mgr.start()
        if not wait_for_server():
            print("[watchdog] ERROR: Servidor no respondió a tiempo", file=sys.stderr)
            server_mgr.stop()
            sys.exit(1)
        print(f"[watchdog] UI lista en http://127.0.0.1:{PORT}/")

    if not args.serve_only:
        # Iniciar observer
        observer = Observer()
        handler = ChangeHandler(server_mgr)
        observer.schedule(handler, str(SRC_DIR), recursive=True)
        observer.start()
        print(f"[watchdog] Observando {SRC_DIR} por cambios...")

        try:
            while True:
                time.sleep(1)
                # Verificar que el servidor sigue vivo
                if not args.watch_only and not server_mgr.is_running():
                    print("[watchdog] Servidor murió inesperadamente, reiniciando...")
                    server_mgr.start()
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            server_mgr.stop()


if __name__ == "__main__":
    main()