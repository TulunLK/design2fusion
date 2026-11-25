#!/usr/bin/env python3
"""Lanza la UI local de design2fusion y la abre en el navegador."""
import os
import sys
import subprocess
import time
import webbrowser
import signal

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def find_server_proc():
    """Devuelve el PID del proceso que escucha en el puerto 8765."""
    try:
        result = subprocess.run(
            ["lsof", "-ti:8765"], capture_output=True, text=True, timeout=5
        )
        pids = [p for p in result.stdout.strip().splitlines() if p]
        return pids[0] if pids else None
    except Exception:
        return None


def start_server():
    """Inicia el servidor si no está corriendo."""
    pid = find_server_proc()
    if pid:
        print(f"design2fusion ya está corriendo (PID {pid})")
        return None

    script = os.path.join(APP_DIR, "d2f", "ui.py")
    # Lanzamos `design2fusion --ui` (mismo entrypoint que el PATH)
    proc = subprocess.Popen(
        [sys.executable, "-m", "d2f.ui"],
        cwd=APP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Servidor iniciado (PID {proc.pid})")
    return proc


def wait_for_server(timeout=15):
    """Espera hasta que el servidor responda."""
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    proc = start_server()
    if proc is None:
        # Ya está corriendo, solo abrimos el navegador
        webbrowser.open(URL)
        return

    if wait_for_server():
        print(f"UI lista: {URL}")
        webbrowser.open(URL)
    else:
        print("No se pudo iniciar el servidor a tiempo.")
        proc.terminate()


if __name__ == "__main__":
    main()
