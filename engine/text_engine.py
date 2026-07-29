import codecs

def process_txt(file_bytes: bytes) -> str:
    """
    يستقبل ملفاً نصياً كبايتات ويعيد محتواه بعد فك الترميز وتوحيد نهايات الأسطر.
    الملفات العربية على ويندوز قد تكون بترميز cp1256 وليس UTF-8.
    نهايات الأسطر (\r\n و \r) تُوحَّد إلى \n لضمان دقة عدّ الأسطر.
    """
    if not file_bytes:
        return ""

    # الملفات ذات علامة الترتيب (BOM) الخاصة بـ UTF-16 تُفك مباشرة
    if file_bytes.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            text = file_bytes.decode("utf-16")
            return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        except UnicodeError:
            pass

    # utf-8-sig أولاً لأنه يزيل الـ BOM ويقرأ UTF-8 العادي أيضاً
    for encoding in ("utf-8-sig", "cp1256", "iso-8859-6"):
        try:
            text = file_bytes.decode(encoding)
            return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        except UnicodeDecodeError:
            continue

    # الملاذ الأخير: لا نُسقط الملف بسبب بايتات تالفة
    text = file_bytes.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
