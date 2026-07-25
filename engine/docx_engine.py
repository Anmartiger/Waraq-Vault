from docx import Document
import io

def process_docx(file_bytes: bytes) -> str:
    """
    يستقبل ملف DOCX كبايتات في الذاكرة ويعيد نصه كاملاً.
    يشمل الفقرات والجداول لأن المستندات الرسمية تضع بياناتها داخل جداول غالباً.
    """
    try:
        # القراءة في الذاكرة العشوائية: لا مساس بالقرص الصلب
        document = Document(io.BytesIO(file_bytes))
        parts = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                parts.append(text)

        # الجداول لا تظهر ضمن paragraphs لذلك نستخرجها بشكل منفصل
        for table in document.tables:
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    text = cell.text.strip()
                    # الخلايا المدمجة تتكرر في row.cells لذلك نتجاهل التكرار المتتالي
                    if text and (not cells or cells[-1] != text):
                        cells.append(text)
                if cells:
                    parts.append(" | ".join(cells))

        # كل عنصر في سطر مستقل ليعمل البحث بأرقام الأسطر
        return "\n".join(parts)

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في محرك قراءة DOCX: {str(e)}")
