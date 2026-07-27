# أدوات نصية مشتركة بين المحركات — بلا أي اعتماديات ثقيلة.

# علامات الترقيم القاطعة: نهاية السطر بها تعني نهاية فقرة منطقية
_TERMINAL_PUNCT = (".", "؟", "!", "?", "؛", ";", ":", "،", ",", "…")

def smart_join(lines) -> str:
    """
    دمج أسطر OCR القصيرة (مربعات القراءة) في فقرات مترابطة بدل الدمج الأعمى:
    السطر الذي ينتهي بعلامة ترقيم قاطعة يُغلق الفقرة، وما عداه يُدمج مع ما
    يليه بمسافة واحدة. هذا يحفظ "السياق المتصل" الذي يحتاجه محرك البحث
    للعثور على الكلمات المتجاورة، بدل تمزيق الفقرة الواحدة إلى عشرة أسطر.
    """
    paragraphs = []
    buffer = []
    for line in lines or []:
        text = (line or "").strip()
        if not text:
            continue
        buffer.append(text)
        if text.endswith(_TERMINAL_PUNCT):
            paragraphs.append(" ".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer))
    return "\n".join(paragraphs)

def page_for_line(page_map, line_number):
    """
    إيجاد رقم الصفحة لسطر معيّن من خريطة الصفحات [[أول_سطر, رقم_الصفحة], ...].
    تعيد None عندما لا تتوفر معلومة صفحة (صور، نصوص، أو ما بعد نطاق الخريطة).
    """
    if not page_map:
        return None
    page = None
    for start_line, page_no in page_map:
        if line_number >= start_line:
            page = page_no
        else:
            break
    return page
