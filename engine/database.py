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

def _highlight_line(line: str, tokens: list) -> str:
    """إحاطة الكلمات المطابقة داخل السطر بوسم <b> اعتماداً على خوارزمية التطبيع نفسها."""
    def repl(match):
        word = match.group(0)
        norm_word = normalize(word)
        if norm_word and any(tok in norm_word for tok in tokens):
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
        if any(tok in norm_line for tok in tokens):
            total += 1
            if len(matches) < cap:
                entry = {"line": i, "text": _highlight_line(line.strip(), tokens)}
                if page is not None:
                    entry["page"] = page
                matches.append(entry)
    return matches, total

def search_documents(query: str, limit: int = 20) -> list:
    """البحث الذكي باستخدام FTS5 — يعيد لكل مستند جميع الأسطر المطابقة مع أرقامها"""
    norm_query = normalize(query)
    # تحويل كلمات البحث إلى صيغة يفهمها FTS5 (كل كلمة يجب أن تحتوي على المعامل *)
    tokens = [t for t in re.split(r"\s+", norm_query) if t]
    if not tokens:
        return []

    match_query = " ".join(f'"{t}"*' for t in tokens)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row  # لإرجاع النتائج كقواميس (Dictionaries)
    try:
        cursor = con.execute("""
            SELECT d.filename, d.content_type, d.raw_text,
                   snippet(documents_fts, 0, '<b>', '</b>', '...', 15) as snippet,
                   bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (match_query, limit))

        results = []
        for row in cursor.fetchall():
            # raw_text يُستخدم داخلياً فقط لاستخراج الأسطر ولا يُعاد كاملاً في الرد
            matches, total = _find_line_matches(row["raw_text"], tokens)
            results.append({
                "filename": row["filename"],
                "content_type": row["content_type"],
                "snippet": row["snippet"],
                "rank": row["rank"],
                "matches": matches,
                "match_count": total,
            })
        return results
    finally:
        con.close()