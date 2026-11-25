#!/usr/bin/env python3
"""
Lanzador para design2fusion - apoyo a la integración de escritorio.

Uso:
    ./launch_design2fusion.py [opciones]

Opciones:
    --web      Lanzar UI web (servidor + navegador) - modo legacy
    --desktop  Lanzar app GTK4 nativa (nuevo modo)
    --help     Mostrar este mensaje

Si no se especifica opción, se lanza la app GTK4 nativa.
"""
import os
import sys
import subprocess
import time
import webbrowser
import argparse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def find_server_proc():
    """Devuelve el PID del proceso que escucha en el puerto 8765."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{PORT}" in line:
                # Extraer PID de "pid=XXXX"
                for part in line.split():
                    if "pid=" in part:
                        return part.split("=")[1].split(",")[0]
        return None
    except Exception:
        return None


def start_web_ui():
    """Inicia el servidor web si no está corriendo."""
    proc = subprocess.Popen(
        [os.path.expanduser("~/.local/bin/design2fusion"), "--ui"],
        cwd=APP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Servidor web iniciado (PID {proc.pid})")
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


def launch_desktop():
    """Lanza la app GTK4 nativa directamente."""
    exe = os.path.expanduser("~/.local/bin/design2fusion")
    if not os.path.exists(exe):
        exe = os.path.join(APP_DIR, "dist", "design2fusion")
    
    if not os.path.exists(exe):
        print("Error: No se encontró el ejecutable design2fusion")
        print(f"Busqué en: ~/.local/bin/design2fusion y dist/design2fusion")
        return 1
    
    # Ejecutar directamente - la app GTK corre en primer plano
    os.execv(exe, [exe, "--desktop"])


def main():
    parser = argparse.ArgumentParser(
        description="Lanzador design2fusion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--web", action="store_true", help="Abrir UI web (servidor + navegador)")
    parser.add_argument("--desktop", action="store_true", help="Abrir app GTK4 nativa (predetermiando)")
    
    args = parser.parse_args()
    
    if args.web:
        # Modo web - iniciar servidor y abrir navegador
        proc = find_server_proc()
        if proc:
            print(f"design2fusion ya está corriendo (PID {proc})")
        else:
            proc = start_web_ui()
        
        if wait_for_server():
            print(f"UI lista: {URL}")
            webbrowser.open(URL)
        else:
            print("No se pudo iniciar el servidor a tiempo.")
            if proc:
                proc.terminate()
    else:
        # Modo desktop - lanzar app nativa
        launch_desktop()


if __name__ == "__main__":
    sys.exit(main())