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
    con.close()
    print("✅ Database and FTS5 Schema initialized successfully.")

def insert_document(filename: str, content_type: str, raw_text: str):
    """إدخال مستند جديد إلى قاعدة البيانات"""
    con = sqlite3.connect(DB_PATH)
    try:
        norm_text = normalize(raw_text)
        con.execute(
            "INSERT INTO documents (filename, content_type, raw_text, normalized_text) VALUES (?, ?, ?, ?)",
            (filename, content_type, raw_text, norm_text)
        )
        con.commit()
    finally:
        con.close()

# أقصى عدد أسطر مطابقة يتم إبرازها لكل مستند (للحفاظ على حجم الرد معقولاً)
_HIGHLIGHT_CAP = 60

def _highlight_line(line: str, tokens: list) -> str:
    """إحاطة الكلمات المطابقة داخل السطر بوسم <b> اعتماداً على خوارزمية التطبيع نفسها."""
    def repl(match):
        word = match.group(0)
        norm_word = normalize(word)
        if norm_word and any(tok in norm_word for tok in tokens):
            return f"<b>{word}</b>"
        return word
    return re.sub(r"\S+", repl, line)

def _find_line_matches(raw_text: str, tokens: list, cap: int = _HIGHLIGHT_CAP):
    """
    البحث عن كل الأسطر التي تحتوي على كلمات البحث.
    يعيد (قائمة الأسطر المطابقة مع رقم كل سطر وإبراز الكلمات، العدد الكلي للمطابقات).
    """
    matches = []
    total = 0
    for i, line in enumerate((raw_text or "").split("\n"), start=1):
        if not line.strip():
            continue
        norm_line = normalize(line)
        if any(tok in norm_line for tok in tokens):
            total += 1
            if len(matches) < cap:
                matches.append({"line": i, "text": _highlight_line(line.strip(), tokens)})
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