"""
Local LibreOffice DOCX -> PDF conversion for the desktop build.

Used instead of Gotenberg when PDF_ENGINE=libreoffice (set by the Tauri
sidecar, which bundles a LibreOffice install and points SOFFICE_PATH at it).
Runs soffice headless directly instead of talking to a Docker microservice.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_CONVERT_TIMEOUT = 120  # seconds — matches the Gotenberg client's budget


def _soffice_binary() -> str:
    override = os.environ.get("SOFFICE_PATH")
    if override and Path(override).exists():
        return override
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    raise RuntimeError(
        "تعذر العثور على LibreOffice (soffice). تأكد من تثبيته أو ضبط متغير SOFFICE_PATH."
    )


def convert_docx_to_pdf_sync(docx_bytes: bytes) -> bytes:
    """
    Convert a DOCX file (in-memory bytes) to PDF via a local headless LibreOffice.

    Raises:
        RuntimeError: If soffice can't be found or the conversion fails.
    """
    binary = _soffice_binary()

    with tempfile.TemporaryDirectory(prefix="waraq-docx2pdf-") as tmp:
        tmp_dir = Path(tmp)
        src_path = tmp_dir / "document.docx"
        src_path.write_bytes(docx_bytes)

        # -env:UserInstallation isolates this run's profile in the temp dir so
        # concurrent conversions never fight over a shared LibreOffice profile lock,
        # and a copied/portable LibreOffice tree never needs to touch the registry.
        profile_dir = tmp_dir / "profile"
        cmd = [
            binary,
            "--headless",
            "--norestore",
            "--convert-to", "pdf",
            "--outdir", str(tmp_dir),
            f"-env:UserInstallation=file:///{profile_dir.as_posix()}",
            str(src_path),
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=_CONVERT_TIMEOUT, check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "انتهت مهلة تحويل المستند إلى PDF عبر LibreOffice. قد يكون الملف كبيراً جداً."
            )

        pdf_path = tmp_dir / "document.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            stderr = (result.stderr or b"").decode(errors="replace")[:400]
            raise RuntimeError(f"فشل LibreOffice في تحويل المستند: {stderr}")

        return pdf_path.read_bytes()


async def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Async wrapper so callers can use either engine interchangeably."""
    return await asyncio.to_thread(convert_docx_to_pdf_sync, docx_bytes)
