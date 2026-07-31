"""
اكتشاف نوع الملف الحقيقي: الامتداد ثم ترويسة المتصفح ثم بصمة المحتوى (Magic Bytes)
— لا ثقة بالاسم وحده، لأن امتداداً مزيفاً يجب أن يُكتشف قبل أن يلوّث الفهرس.
"""
import io
import os
import zipfile

from fastapi import HTTPException

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")

# نوع افتراضي يُخزَّن في قاعدة البيانات إذا لم يرسل المتصفح content_type
FALLBACK_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": DOCX_CONTENT_TYPE,
    "txt": "text/plain",
    "image": "image/png",
}


def _zip_flavor(data: bytes) -> str | None:
    """تمييز نكهة ملف ZIP: docx أو odt أو zip عادي — لرسائل خطأ صادقة."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if any(n.startswith("word/") for n in names):
                return "docx"
            if "mimetype" in names:
                mimetype = z.read("mimetype")[:100].decode("ascii", "replace")
                if "opendocument.text" in mimetype:
                    return "odt"
            return "zip"
    except Exception:
        return None


def _sniff_kind(data: bytes) -> str | None:
    """التعرف على نوع الملف من محتواه الفعلي (Magic Bytes) — لا ثقة بالاسم وحده."""
    if not data:
        return None
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff") \
       or data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    # BMP: توقيع "BM" وحده ضعيف (نص يبدأ بـ BMW مثلاً) — نتحقق من الحقول المحجوزة
    if data.startswith(b"BM") and len(data) > 26 and data[6:10] == b"\x00\x00\x00\x00":
        return "image"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    if data[:4] == b"PK\x03\x04":
        return "docx" if _zip_flavor(data) == "docx" else None
    # نص محتمل: لا بايتات صفرية + قابل لفك الترميز بأحد ترميزات المشروع
    sample = data[:4096]
    if b"\x00" in sample:
        return None
    for encoding in ("utf-8", "cp1256"):
        try:
            sample.decode(encoding)
            return "txt"
        except UnicodeDecodeError:
            continue
    return None


def detect_kind(filename: str, content_type: str, file_bytes: bytes = b"") -> str | None:
    """تحديد نوع الملف: الامتداد ← ترويسة content_type ← بصمة المحتوى."""
    ext = os.path.splitext(filename or "")[1].lower()
    ctype = (content_type or "").lower()

    if ext == ".pdf" or ctype == "application/pdf":
        return "pdf"
    if ext == ".docx" or ctype == DOCX_CONTENT_TYPE:
        return "docx"
    if ext == ".txt" or ctype.startswith("text/"):
        return "txt"
    if ext in IMAGE_EXTENSIONS or ctype.startswith("image/"):
        return "image"
    return _sniff_kind(file_bytes)


def verify_content_matches(kind: str, data: bytes, filename: str) -> None:
    """
    صمام أمان الامتدادات المزيفة: الامتداد ادّعى نوعاً، والمحتوى يجب أن يثبته.
    ملف ODT مسمّى .pdf يُرفض هنا برسالة واضحة بدل تلويث قاعدة البيانات بسجل تالف.
    """
    sniffed = _sniff_kind(data)
    if sniffed == kind:
        return
    flavor = _zip_flavor(data) if data[:4] == b"PK\x03\x04" else None
    actual = {"odt": "ملف OpenDocument (ODT)", "zip": "أرشيف ZIP", "docx": "ملف Word"}.get(
        flavor, {"pdf": "ملف PDF", "image": "صورة", "txt": "ملف نصي", None: "محتوى غير معروف"}.get(sniffed, "محتوى غير معروف")
    )
    raise HTTPException(
        status_code=400,
        detail=f"الامتداد لا يطابق المحتوى الحقيقي للملف {filename}: المحتوى الفعلي {actual}. "
               f"أعد تسمية الملف بامتداده الصحيح أو حوّله للصيغة المدعومة."
    )
