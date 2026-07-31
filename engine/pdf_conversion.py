"""
Picks the DOCX->PDF conversion backend: Gotenberg (Docker microservice, the
default — unchanged behavior for docker-compose deployments) or a local
LibreOffice binary (desktop build, PDF_ENGINE=libreoffice).
"""

import os

_ENGINE = os.environ.get("PDF_ENGINE", "gotenberg").strip().lower()

if _ENGINE == "libreoffice":
    from engine.libreoffice_client import convert_docx_to_pdf, convert_docx_to_pdf_sync
else:
    from engine.gotenberg_client import convert_docx_to_pdf, convert_docx_to_pdf_sync

__all__ = ["convert_docx_to_pdf", "convert_docx_to_pdf_sync"]
