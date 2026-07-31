"""
Resolves filesystem paths that differ between three ways this app runs:
source checkout, PyInstaller-frozen desktop build, and Docker container.
Everything else in the codebase should go through these instead of building
paths off __file__ or the CWD directly.
"""

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory containing bundled read-only resources (ui/).

    Under PyInstaller, sys._MEIPASS is the extraction dir (onefile) or the
    directory next to the executable (onedir) — either way, that's where our
    bundled data files (ui/) were placed by the spec's `datas` list.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Writable directory for the database and stored document copies.

    WARAQ_DATA_DIR overrides everything (used by the Tauri sidecar, which
    points this at the OS-appropriate per-user app data folder). Frozen
    builds without an explicit override fall back to a per-user folder
    because the install location (e.g. Program Files) may not be writable.
    Source/Docker runs keep the historical project-relative storage/ dir.
    """
    override = os.environ.get("WARAQ_DATA_DIR")
    if override:
        path = Path(override)
    elif getattr(sys, "frozen", False):
        base = (
            os.environ.get("APPDATA")
            or os.environ.get("XDG_DATA_HOME")
            or str(Path.home() / ".local" / "share")
        )
        path = Path(base) / "WaraqVault"
    else:
        path = Path(__file__).resolve().parent.parent / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path
