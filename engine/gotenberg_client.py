"""
Asynchronous Gotenberg client for DOCX → PDF conversion.

Gotenberg (https://gotenberg.dev) is an internal microservice that converts
office documents to PDF via LibreOffice. This module provides both async and
sync entry points so it can be used from FastAPI's worker threads without
blocking the main event loop.

Environment:
    GOTENBERG_URL — base URL of the Gotenberg service (default: http://localhost:3000)
"""

import os
import asyncio

import httpx

_GOTENBERG_URL = os.environ.get("GOTENBERG_URL", "http://localhost:3000")

# Generous timeout: large/complex DOCX files with embedded images may take a while
# for LibreOffice to render inside the Gotenberg container.
_CONVERT_TIMEOUT = 120.0  # seconds


async def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Convert a DOCX file (in-memory bytes) to PDF via Gotenberg's LibreOffice endpoint.

    Args:
        docx_bytes: Raw bytes of the .docx file.

    Returns:
        The generated PDF as bytes.

    Raises:
        RuntimeError: If Gotenberg is unreachable or the conversion fails.
    """
    url = f"{_GOTENBERG_URL}/forms/libreoffice/convert"

    files = {"files": ("document.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}

    async with httpx.AsyncClient(timeout=_CONVERT_TIMEOUT) as client:
        try:
            response = await client.post(url, files=files)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise RuntimeError(
                "انتهت مهلة تحويل المستند إلى PDF عبر Gotenberg. قد يكون الملف كبيراً جداً أو الخادم مشغولاً."
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"فشل Gotenberg في تحويل المستند (HTTP {e.response.status_code}): {e.response.text[:200]}"
            )
        except httpx.RequestError as e:
            raise RuntimeError(
                f"تعذر الاتصال بخدمة Gotenberg ({_GOTENBERG_URL}). تأكد من أن الحاوية قيد التشغيل: {e}"
            )

    # Gotenberg returns the PDF with a Content-Disposition header but the body is the raw PDF.
    content_type = response.headers.get("content-type", "")
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF-"):
        raise RuntimeError(
            f"استجابة غير متوقعة من Gotenberg (توقّع PDF): {content_type} / {response.content[:80]!r}"
        )

    return response.content


def convert_docx_to_pdf_sync(docx_bytes: bytes) -> bytes:
    """
    Synchronous wrapper around convert_docx_to_pdf.

    Safe to call from a worker thread (ThreadPoolExecutor) — it creates its own
    event loop so it never touches the main FastAPI loop.

    Args:
        docx_bytes: Raw bytes of the .docx file.

    Returns:
        The generated PDF as bytes.
    """
    try:
        asyncio.get_running_loop()
        # A loop is already running in this thread (e.g. FastAPI's event loop),
        # so asyncio.run() here would raise — delegate to a fresh thread instead.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, convert_docx_to_pdf(docx_bytes)).result()
    except RuntimeError:
        return asyncio.run(convert_docx_to_pdf(docx_bytes))