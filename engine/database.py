import sqlite3
import re
from pathlib import Path

# تحديد مسار قاعدة البيانات لتكون في الجذر الرئيسي للمشروع
DB_PATH = Path(__file__).resolve().parent.parent / "waraq.db"

# خوارزمية النمر لتطبيع النصوص العربية (إزالة التشكيل وتوحيد الحروف)
_MARKS = re.compile("[ـً-ٰٟۖ-ۭ]")
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", 
    "ى": "ي", "ئ": "ي", 
    "ؤ": "و", 
    "ة": "ه", 
    "ـ": "", 
})

def normalize(text: str) -> str:
    """تجهيز النص ليكون قابلاً للبحث بغض النظر عن الأخطاء الإملائية أو التشكيل"""
    if not text:
        return ""
    return _MARKS.sub("", text).translate(_FOLD).lower()

def init_db():
    """تهيئة قاعدة البيانات وبناء جداول FTS5 إذا لم تكن موجودة"""
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            file_hash TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        -- جدول البحث النصي الكامل (FTS5)
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            normalized_text,
            content=documents,
            content_rowid=id
        );

        -- زنادات (Triggers) لمزامنة البيانات تلقائياً بين الجدولين
        CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, normalized_text) VALUES (new.id, new.normalized_text);
        END;
        
        CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, normalized_text) VALUES('delete', old.id, old.normalized_text);
        END;
        
        CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, normalized_text) VALUES('delete', old.id, old.normalized_text);
            INSERT INTO documents_fts(rowid, normalized_text) VALUES (new.id, new.normalized_text);
        END;
    """)

    # ترحيل قواعد البيانات القديمة التي أُنشئت قبل إضافة بصمة الملف
    existing_columns = [row[1] for row in con.execute("PRAGMA table_info(documents)")]
    if "file_hash" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN file_hash TEXT")
        con.commit()
        print("ℹ️ Added file_hash column to the existing documents table.")

    con.close()
    print("✅ Database and FTS5 Schema initialized successfully.")

def insert_document(filename: str, content_type: str, raw_text: str, file_hash: str = None):
    """إدخال مستند جديد إلى قاعدة البيانات"""
    con = sqlite3.connect(DB_PATH)
    try:
        norm_text = normalize(raw_text)
        con.execute(
            "INSERT INTO documents (filename, content_type, raw_text, normalized_text, file_hash) VALUES (?, ?, ?, ?, ?)",
            (filename, content_type, raw_text, norm_text, file_hash)
        )
        con.commit()
    finally:
        con.close()

def find_duplicate(filename: str, file_hash: str = None) -> dict:
    """
    البحث عن مستند مطابق قبل بدء المعالجة الثقيلة (OCR).
    الأولوية لتطابق المحتوى (البصمة) لأنه يكشف الملف نفسه حتى لو تغيّر اسمه.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        if file_hash:
            row = con.execute(
                "SELECT id, filename, created_at FROM documents WHERE file_hash = ? ORDER BY id LIMIT 1",
                (file_hash,)
            ).fetchone()
            if row:
                return {"match": "content", **dict(row)}

        row = con.execute(
            "SELECT id, filename, created_at FROM documents WHERE filename = ? ORDER BY id LIMIT 1",
            (filename,)
        ).fetchone()
        if row:
            return {"match": "filename", **dict(row)}

        return None
    finally:
        con.close()

def delete_documents(filename: str = None, file_hash: str = None) -> int:
    """
    حذف كل المستندات المطابقة بالاسم أو بالبصمة ويعيد عدد الصفوف المحذوفة.
    زناد docs_ad يتكفّل بإزالتها من فهرس FTS5 تلقائياً.
    """
    if not filename and not file_hash:
        return 0

    conditions, params = [], []
    if filename:
        conditions.append("filename = ?")
        params.append(filename)
    if file_hash:
        conditions.append("file_hash = ?")
        params.append(file_hash)

    con = sqlite3.connect(DB_PATH)
    try:
        cursor = con.execute(f"DELETE FROM documents WHERE {' OR '.join(conditions)}", params)
        con.commit()
        return cursor.rowcount
    finally:
        con.close()

# أقصى عدد أسطر مطابقة تُرسَل لكل مستند (سقف أمان؛ زر "Show more" في الواجهة يعرضها كلها)
_HIGHLIGHT_CAP = 1000

# ------------------------------------------------------------------
# السوابق العربية (حروف العطف والجر وأداة التعريف) — توليد تركيبي:
# و/ف × ب/ك/ل × ال — مع معالجة خاصة لـ "ل + ال = لل".
# تُستخدم في اتجاهين: توسيع استعلام FTS5 (وتخطيطا تُطابق تخطيطا)
# وتقليم الكلمة عند المطابقة والتظليل — دون أي مساس بالنص المخزّن.
# ------------------------------------------------------------------
_CONJ = ("", "و", "ف")
_PREP = ("", "ب", "ك", "ل")
_ART  = ("", "ال")

def _build_prefixes():
    out = set()
    for c in _CONJ:
        for p in _PREP:
            for a in _ART:
                tail = "لل" if (p == "ل" and a == "ال") else p + a
                pre = c + tail
                if pre:
                    out.add(pre)
    return sorted(out, key=len, reverse=True)   # الأطول أولاً عند التقليم

_PREFIXES = _build_prefixes()

# علامات الترقيم التي تُقلَّم من أطراف الكلمة قبل المقارنة (عربية ولاتينية)
_STRIP_CHARS = "\"'“”‘’«»()[]{}.,;:!?؟،؛…ـ-–—_*%٪/\\+|<>#@&=~`^"

def _word_stems(norm_word: str) -> set:
    """الكلمة كما هي + صورها بعد نزع سابقة واحدة (بشرط بقاء جذر من حرفين فأكثر)."""
    w = norm_word.strip(_STRIP_CHARS)
    if not w:
        return set()
    stems = {w}
    for pre in _PREFIXES:
        if w.startswith(pre) and len(w) - len(pre) >= 2:
            stems.add(w[len(pre):])
    return stems

def _token_matches_word(norm_word: str, token: str) -> bool:
    """
    مطابقة صارمة على حدود الكلمات بدل البحث عن أي تطابق جزئي:
    - كلمات البحث القصيرة (حرف/حرفان مثل "في" و"مع") تطابق الكلمة كاملة فقط،
      فلا تُظلَّل "في" داخل "تحفيزه" ولا تُجلَب "معلومات" عند البحث عن "مع".
    - الكلمات الأطول تطابق بادئة الكلمة (سلوك FTS5 نفسه مع المعامل *).
    """
    stems = _word_stems(norm_word)
    if len(token) >= 3:
        return any(s == token or s.startswith(token) for s in stems)
    return token in stems

def _line_has_match(norm_line: str, tokens: list) -> bool:
    for word in norm_line.split():
        stems = _word_stems(word)
        if not stems:
            continue
        for token in tokens:
            if len(token) >= 3:
                if any(s == token or s.startswith(token) for s in stems):
                    return True
            elif token in stems:
                return True
    return False

def _highlight_line(line: str, tokens: list) -> str:
    """إحاطة الكلمات المطابقة داخل السطر بوسم <b> اعتماداً على خوارزمية التطبيع نفسها."""
    def repl(match):
        word = match.group(0)
        norm_word = normalize(word)
        if norm_word and any(_token_matches_word(norm_word, tok) for tok in tokens):
            return f"<b>{word}</b>"
        return word
    return re.sub(r"\S+", repl, line)

# علامة بداية الصفحة التي يضيفها محرك الـ PDF (مثال: "--- صفحة 12 ---")
_PAGE_MARKER = re.compile(r"^\s*---\s*صفحة\s*(\d+)\s*---\s*$")

def _find_line_matches(raw_text: str, tokens: list, cap: int = _HIGHLIGHT_CAP):
    """
    البحث عن كل الأسطر التي تحتوي على كلمات البحث.
    يعيد (قائمة الأسطر المطابقة مع رقم السطر ورقم صفحته إن توفّرت، العدد الكلي للمطابقات).
    """
    matches = []
    total = 0
    page = None  # يبقى None للصور (لا تحتوي علامات صفحات)
    for i, line in enumerate((raw_text or "").split("\n"), start=1):
        marker = _PAGE_MARKER.match(line)
        if marker:
            page = int(marker.group(1))
            continue  # لا نعتبر سطر العلامة نفسه نتيجة بحث
        if not line.strip():
            continue
        norm_line = normalize(line)
        if _line_has_match(norm_line, tokens):
            total += 1
            if len(matches) < cap:
                entry = {"line": i, "text": _highlight_line(line.strip(), tokens)}
                if page is not None:
                    entry["page"] = page
                matches.append(entry)
    return matches, total

def _fts_match_expr(tokens: list) -> str:
    """
    بناء استعلام FTS5 موسَّع بالسوابق: كل كلمة بحث تُطابق نفسها أو أي صورة
    مسبوقة بحرف عطف/جر/تعريف (تخطيطا ← وتخطيطا، بالتخطيط...).
    الكلمات القصيرة (أقل من 3 أحرف) تُطابَق كاملةً بلا معامل * حتى لا تجلب
    "مع"* كلمة "معلومات" — وهذا مصدر النتائج الخاطئة سابقاً.
    """
    groups = []
    for t in tokens:
        variants = {t} | {pre + t for pre in _PREFIXES}
        # علامة الاقتباس المزدوجة تُضاعَف داخل سلاسل FTS5 (حماية من كسر الاستعلام)
        if len(t) >= 3:
            alts = [f'"{v.replace(chr(34), chr(34) * 2)}"*' for v in sorted(variants)]
        else:
            alts = [f'"{v.replace(chr(34), chr(34) * 2)}"' for v in sorted(variants)]
        groups.append("(" + " OR ".join(alts) + ")")
    return " AND ".join(groups)

# نطاقات الحروف لتحديد لغة المستند (وسام AR/EN/مختلط في الواجهة)
_AR_CHARS = re.compile(r"[؀-ۿ]")
_EN_CHARS = re.compile(r"[A-Za-z]")

def _detect_lang(text: str) -> str:
    """تحليل حقيقي لهوية النص بدل الافتراض الثابت: ar أو en أو mixed."""
    sample = (text or "")[:200000]   # عيّنة كافية وسقف للأداء
    ar = len(_AR_CHARS.findall(sample))
    en = len(_EN_CHARS.findall(sample))
    if ar and en:
        ratio = ar / (ar + en)
        if 0.1 <= ratio <= 0.9:
            return "mixed"
        return "ar" if ratio > 0.9 else "en"
    if ar:
        return "ar"
    return "en"

def _unit_for(content_type: str) -> str:
    """
    وحدة الترقيم الصادقة لكل نوع ملف:
    - الصور: كتل OCR لا "أسطر" حقيقية ← تُخفى الأرقام في الواجهة (block)
    - DOCX: فقرات وليست أسطراً بصرية ← تُعرض ¶ بدل L (para)
    - PDF/TXT: أسطر فعلية ← تُعرض L (line)
    """
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "block"
    if "wordprocessingml" in ct or ct == "application/msword":
        return "para"
    return "line"

def search_documents(query: str, limit: int = 20, doc_ids: list = None) -> list:
    """البحث الذكي باستخدام FTS5 — يعيد لكل مستند جميع الأسطر المطابقة مع أرقامها.
    doc_ids: قصر البحث على مستندات بعينها (مرشِّح النطاق في الواجهة)."""
    norm_query = normalize(query)
    # تقليم علامات الترقيم من أطراف كل كلمة بحث ("تخطيطا" تعمل مثل تخطيطا)
    tokens = [t.strip(_STRIP_CHARS) for t in re.split(r"\s+", norm_query)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []

    match_query = _fts_match_expr(tokens)

    sql = """
        SELECT d.id, d.filename, d.content_type, d.raw_text,
               snippet(documents_fts, 0, '<b>', '</b>', '...', 15) as snippet,
               bm25(documents_fts) AS rank
        FROM documents_fts
        JOIN documents d ON d.id = documents_fts.rowid
        WHERE documents_fts MATCH ?
    """
    params = [match_query]
    if doc_ids:
        placeholders = ",".join("?" for _ in doc_ids)
        sql += f" AND d.id IN ({placeholders})"
        params.extend(int(i) for i in doc_ids)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row  # لإرجاع النتائج كقواميس (Dictionaries)
    try:
        cursor = con.execute(sql, params)
        results = []
        for row in cursor.fetchall():
            # raw_text يُستخدم داخلياً فقط لاستخراج الأسطر ولا يُعاد كاملاً في الرد
            matches, total = _find_line_matches(row["raw_text"], tokens)
            results.append({
                "id": row["id"],
                "filename": row["filename"],
                "content_type": row["content_type"],
                "snippet": row["snippet"],
                "rank": row["rank"],
                "matches": matches,
                "match_count": total,
                "lang": _detect_lang(row["raw_text"]),
                "unit": _unit_for(row["content_type"]),
            })
        return results
    finally:
        con.close()

def list_documents() -> list:
    """قائمة المستندات المفهرسة — تغذّي مرشِّح النطاق وزر الحذف في الواجهة."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cursor = con.execute("""
            SELECT id, filename, content_type, created_at, length(raw_text) AS chars
            FROM documents
            ORDER BY created_at DESC, id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        con.close()

def delete_document_by_id(doc_id: int) -> int:
    """حذف مستند واحد بمعرّفه. زناد docs_ad يزيله من فهرس FTS5 — لا صفوف يتيمة."""
    con = sqlite3.connect(DB_PATH)
    try:
        cursor = con.execute("DELETE FROM documents WHERE id = ?", (int(doc_id),))
        con.commit()
        return cursor.rowcount
    finally:
        con.close()