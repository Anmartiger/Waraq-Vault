"""
Picks the DOCX->PDF conversion backend: Gotenberg (Docker microservice, the
default — unchanged behavior for docker-compose deployments) or a local
LibreOffice binary (desktop build, PDF_ENGINE=libreoffice).
"""

import logging
import os

logger = logging.getLogger(__name__)


def _autodetect_bundled_soffice():
    """
    Redundant safety net for the desktop build: PDF_ENGINE/SOFFICE_PATH are
    normally set by the Tauri shell (src-tauri/src/lib.rs) after it finds the
    bundled LibreOffice under the app's resource dir. If that hand-off ever
    misses — a packaging layout change, an env var not propagating — this
    looks for the same bundled copy directly from Python instead of silently
    falling back to a Gotenberg container that doesn't exist outside Docker.
    """
    from engine.paths import app_dir

    # app_dir() is resources/backend/waraq-backend/ in the installed app
    # (PyInstaller's onedir base) — libreoffice/ is a sibling of backend/.
    base = app_dir()
    for rel in ("../../libreoffice/program/soffice.exe", "../../libreoffice/program/soffice"):
        candidate = (base / rel).resolve()
        if candidate.is_file():
            return str(candidate)
    return None


_ENGINE = os.environ.get("PDF_ENGINE", "").strip().lower()
_SOFFICE = os.environ.get("SOFFICE_PATH")

if not _ENGINE:
    if not _SOFFICE:
        _SOFFICE = _autodetect_bundled_soffice()
    _ENGINE = "libreoffice" if _SOFFICE else "gotenberg"

if _ENGINE == "libreoffice":
    if _SOFFICE and not os.environ.get("SOFFICE_PATH"):
        os.environ["SOFFICE_PATH"] = _SOFFICE
    logger.info(f"📄 PDF engine: LibreOffice (SOFFICE_PATH={os.environ.get('SOFFICE_PATH')})")
    from engine.libreoffice_client import convert_docx_to_pdf, convert_docx_to_pdf_sync
else:
    logger.info(f"📄 PDF engine: Gotenberg (PDF_ENGINE={os.environ.get('PDF_ENGINE')!r} — "
                f"expected 'libreoffice' in a desktop build; falling back to Gotenberg means "
                f"no bundled LibreOffice was found, so DOCX conversion will fail without a "
                f"Gotenberg container)")
    from engine.gotenberg_client import convert_docx_to_pdf, convert_docx_to_pdf_sync

__all__ = ["convert_docx_to_pdf", "convert_docx_to_pdf_sync"]
