"""
Entry point for the packaged desktop build (PyInstaller sidecar spawned by Tauri).

Distinct from main.py's own __main__ block: no autoreload (incompatible with a
frozen executable — it respawns via sys.executable) and the port is
configurable since the Tauri shell picks it and passes it down.
"""

import os
import sys

# The Tauri shell already sets PYTHONIOENCODING/PYTHONUTF8 (see spawn_backend
# in src-tauri/src/lib.rs) so this is redundant in the packaged build — but it
# keeps `python desktop_main.py` safe to run directly too, and runs before the
# `from main import app` below pulls in every module that might print/log
# something non-ASCII (this codebase does, a lot) during import itself.
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn

from main import app

if __name__ == "__main__":
    port = int(os.environ.get("WARAQ_PORT", "8756"))
    uvicorn.run(app, host="127.0.0.1", port=port)
