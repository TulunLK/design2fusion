# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Configuración del proyecto
# -----------------------------------------------------------------------------
# En archivos .spec, __file__ no está disponible; usamos el directorio actual
APP_DIR = Path.cwd().resolve()
SRC_DIR = APP_DIR / "d2f"
CLI_ENTRY = SRC_DIR / "cli.py"

# -----------------------------------------------------------------------------
# Análisis de dependencias (automático + explícitas)
# -----------------------------------------------------------------------------
block_cipher = None

a = Analysis(
    [str(CLI_ENTRY)],
    pathex=[str(SRC_DIR), str(APP_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "PIL.ImageFilter",
        "json",
        "html",
        "tempfile",
        "traceback",
        "urllib.parse",
        "http.server",
        "socketserver",
        "subprocess",
        "shutil",
        "pathlib",
        "dataclasses",
        "typing",
        "d2f.ui",  # importado dinámicamente por cli.py --ui
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filtrar binarios/datas para no incluir basura
a.datas = [x for x in a.datas if not any(p in x[0] for p in (".pyc", "__pycache__", ".git"))]

# -----------------------------------------------------------------------------
# Ejecutable principal (CLI + UI via --ui)
# -----------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="design2fusion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(APP_DIR / "d2f.png") if (APP_DIR / "d2f.png").exists() else None,
)

# -----------------------------------------------------------------------------
# Ejecutable CLI (opcional, mismo binario con entrypoint distinto)
# Se usa el mismo .exe pero con --cli como argumento interno
# -----------------------------------------------------------------------------
# No creamos exe separado; el entrypoint 'design2fusion' en setup.py/pip
# ya expone cli:main. Aquí el binario único sirve para ambos:
#   design2fusion            -> UI (--ui implícito si no hay args)
#   design2fusion --ui       -> UI
#   design2fusion archivo... -> CLI
# La lógica está en cli.py y ui.py (if __name__ == "__main__")

# -----------------------------------------------------------------------------
# App bundle (macOS/Linux desktop integration opcional)
# -----------------------------------------------------------------------------
# app = BUNDLE(
#     exe_ui,
#     name="design2fusion.app",
#     icon=str(APP_DIR / "d2f.png"),
#     bundle_identifier="com.tulunlk.design2fusion",
#     info_plist={
#         "CFBundleName": "design2fusion",
#         "CFBundleDisplayName": "design2fusion",
#         "CFBundleVersion": "0.2.0",
#         "CFBundleShortVersionString": "0.2.0",
#         "NSHighResolutionCapable": True,
#     },
# )