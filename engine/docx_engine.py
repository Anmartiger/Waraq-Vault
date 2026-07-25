from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
import io

def _blocks_from(child, parent):
    """تحويل عنصر XML إلى فقرة أو جدول، مع فك أغلفة عناصر التحكم بالمحتوى."""
    if isinstance(child, CT_P):
        yield Paragraph(child, parent)
    elif isinstance(child, CT_Tbl):
        yield Table(child, parent)
    elif child.tag == qn("w:sdt"):
        # عناصر التحكم بالمحتوى (Content Controls) تغلّف فقرات وجداول حقيقية،
        # وتجاهلها يعني ضياع نصها وفواصل صفحاتها من الفهرسة
        content = child.find(qn("w:sdtContent"))
        if content is not None:
            for sub in content.iterchildren():
                yield from _blocks_from(sub, parent)

def _iter_blocks(parent):
    """
    المرور على الفقرات والجداول بترتيب ظهورها الفعلي داخل المستند،
    لأن python-docx يعيدها في قائمتين منفصلتين ويضيع الترتيب الأصلي.
    """
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("عنصر غير مدعوم للمرور عليه")

    for child in parent_elm.iterchildren():
        yield from _blocks_from(child, parent)

def _count_page_breaks(element) -> int:
    """
    عدّ فواصل الصفحات داخل عنصر معيّن:
    - lastRenderedPageBreak: ترقيم Word الحقيقي المحفوظ عند آخر مرة عرض فيها المستند
    - w:br type=page: فاصل صفحة يدوي أدرجه كاتب المستند
    ملف DOCX لا يخزّن أرقام صفحات جاهزة، وهاتان الإشارتان هما الدليل الوحيد المتاح.
    """
    breaks = len(element.findall(".//" + qn("w:lastRenderedPageBreak")))
    for br in element.findall(".//" + qn("w:br")):
        if br.get(qn("w:type")) == "page":
            breaks += 1
    return breaks

def _row_text(row) -> str:
    """نص صف الجدول مع تجاهل تكرار الخلايا المدمجة."""
    cells = []
    for cell in row.cells:
        text = cell.text.strip()
        # الخلايا المدمجة تتكرر في row.cells لذلك نتجاهل التكرار المتتالي
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)

def process_docx(file_bytes: bytes) -> str:
    """
    يستقبل ملف DOCX كبايتات في الذاكرة ويعيد نصه كاملاً.
    يشمل الفقرات والجداول، ويضيف علامات الصفحات بنفس صيغة محرك الـ PDF
    (--- صفحة N ---) إذا كان المستند يحمل إشارات ترقيم.
    """
    try:
        # القراءة في الذاكرة العشوائية: لا مساس بالقرص الصلب
        document = Document(io.BytesIO(file_bytes))

        # إذا لم يحمل المستند أي إشارة ترقيم نكتفي بأرقام الأسطر بدل تخمين الصفحات
        paginated = _count_page_breaks(document.element.body) > 0

        parts = []
        page = 1
        if paginated:
            parts.append(f"--- صفحة {page} ---")

        for block in _iter_blocks(document):
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    parts.append(text)
                breaks = _count_page_breaks(block._p)
            else:
                # الجداول تُستخرج صفاً صفاً لأن المستندات الرسمية تضع بياناتها فيها
                for row in block.rows:
                    row_text = _row_text(row)
                    if row_text:
                        parts.append(row_text)
                breaks = _count_page_breaks(block._tbl)

            # الفاصل يعني أن ما يليه ينتمي للصفحة التالية
            if paginated and breaks:
                page += breaks
                parts.append(f"--- صفحة {page} ---")

        # كل عنصر في سطر مستقل ليعمل البحث بأرقام الأسطر
        return "\n".join(parts)

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في محرك قراءة DOCX: {str(e)}")
