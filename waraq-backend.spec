# -*- mode: python ; coding: utf-8 -*-
# Freezes the FastAPI backend into a standalone onedir build for the Tauri
# sidecar. onedir (not onefile) on purpose: torch/easyocr are large enough
# that onefile's per-launch self-extraction would add real startup latency.
from PyInstaller.utils.hooks import collect_all

datas = [('ui', 'ui')]
binaries = []
hiddenimports = [
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
    'multipart',
]

for pkg in ('easyocr', 'torch', 'torchvision', 'SimpleITK', 'fitz'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['desktop_main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='waraq-backend',
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='waraq-backend',
)
