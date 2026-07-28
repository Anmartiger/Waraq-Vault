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

def _bbox_bounds(bbox):
    """أعلى وأسفل الصندوق مهما كان شكل النقاط الأربع."""
    ys = [float(p[1]) for p in bbox]
    return min(ys), max(ys)

def join_boxes(results, line_overlap: float = 0.45, para_gap: float = 0.75) -> str:
    """
    بناء الفقرات من إحداثيات صناديق OCR بدل التخمين من علامات الترقيم:
    - صندوقان يتداخلان رأسياً ⇒ نفس السطر البصري.
    - فجوة رأسية بين سطرين أكبر من ثلاثة أرباع ارتفاع السطر ⇒ فقرة جديدة.

    ترتيب المحرك محفوظ حرفياً — نُدخل الفواصل فقط ولا نعيد فرز أي شيء،
    حتى لا نمسّ ترتيب العربية (RTL) الذي يعتمد عليه الفهرس.
    """
    items = []
    for entry in results or []:
        bbox, text = entry[0], entry[1]
        text = (text or "").strip()
        if not text:
            continue
        top, bottom = _bbox_bounds(bbox)
        items.append((top, bottom, text))
    if not items:
        return ""

    heights = sorted(max(b - t, 1.0) for t, b, _ in items)
    median_height = heights[len(heights) // 2]

    # 1) تجميع الصناديق في أسطر بصرية حسب التداخل الرأسي
    lines = []
    for top, bottom, text in items:
        if lines:
            ltop, lbottom, texts = lines[-1]
            overlap = min(bottom, lbottom) - max(top, ltop)
            shorter = min(bottom - top, lbottom - ltop) or 1.0
            if overlap > line_overlap * shorter:
                lines[-1] = (min(top, ltop), max(bottom, lbottom), texts + [text])
                continue
        lines.append((top, bottom, [text]))

    # 2) تجميع الأسطر في فقرات حسب الفجوة الرأسية بينها
    paragraphs = [[" ".join(lines[0][2])]]
    for index in range(1, len(lines)):
        gap = lines[index][0] - lines[index - 1][1]
        if gap > para_gap * median_height:
            paragraphs.append([])
        paragraphs[-1].append(" ".join(lines[index][2]))

    return "\n".join(" ".join(p) for p in paragraphs if p)

def join_ocr(results) -> str:
    """
    نقطة الدخول الموحّدة لنتائج OCR: تقبل الشكلين معاً.
    - [(bbox, text, conf), ...] ⇒ تجميع هندسي دقيق.
    - ["نص", ...] ⇒ رجوع إلى الدمج بعلامات الترقيم (محركات أو اختبارات لا تعطي إحداثيات).
    """
    if not results:
        return ""
    first = results[0]
    if not isinstance(first, str) and isinstance(first, (list, tuple)) and len(first) >= 2:
        try:
            return join_boxes(results)
        except Exception:
            # إحداثيات غير متوقعة الشكل — لا نُسقط النص، نكمل بالطريقة القديمة
            return smart_join([e[1] for e in results if not isinstance(e, str)])
    return smart_join(results)

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
