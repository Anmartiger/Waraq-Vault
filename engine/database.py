import sqlite3
import re
import json
from pathlib import Path

from engine.textflow import page_for_line, para_for_line

# تحديد مسار قاعدة البيانات داخل مجلد storage/ (يبقى ملفاً حقيقياً حتى مع bind mount فارغ)
DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "waraq.db"

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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            file_hash TEXT,
            workspace TEXT NOT NULL DEFAULT 'Default',
            page_map TEXT,
            stored_name TEXT,
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

    # ترحيل قواعد البيانات القديمة بدون مسح بيانات المستخدم (لا حاجة لحذف waraq.db)
    existing_columns = [row[1] for row in con.execute("PRAGMA table_info(documents)")]
    if "file_hash" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN file_hash TEXT")
        con.commit()
        print("ℹ️ Added file_hash column to the existing documents table.")
    if "workspace" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN workspace TEXT NOT NULL DEFAULT 'Default'")
        con.commit()
        print("ℹ️ Added workspace column to the existing documents table.")
    if "page_map" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN page_map TEXT")
        con.commit()
        print("ℹ️ Added page_map column to the existing documents table.")
    if "stored_name" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN stored_name TEXT")
        con.commit()
        print("ℹ️ Added stored_name column — new uploads keep an openable copy.")
    if "para_map" not in existing_columns:
        con.execute("ALTER TABLE documents ADD COLUMN para_map TEXT")
        con.commit()
        print("ℹ️ Added para_map column — paragraph metadata per page stored cleanly.")

    con.close()
    print("✅ Database and FTS5 Schema initialized successfully.")

def insert_document(filename: str, content_type: str, raw_text: str, file_hash: str = None,
                    workspace: str = "Default", page_map: list = None, stored_name: str = None,
                    para_map: list = None):
    """إدخال مستند جديد إلى قاعدة البيانات.
    page_map: خريطة الصفحات [[أول_سطر, رقم_الصفحة], ...] — تُخزَّن خارج النص
    حتى لا تلوّث فهرس البحث بفواصل وهمية.
    para_map: خريطة الفقرات [[أول_سطر, رقم_الصفحة, رقم_الفقرة], ...] — تُخزَّن خارج النص
    ورقم الفقرة يُعاد تعيينه إلى 1 مع كل صفحة جديدة."""
    con = sqlite3.connect(DB_PATH)
    try:
        norm_text = normalize(raw_text)
        con.execute(
            "INSERT INTO documents (filename, content_type, raw_text, normalized_text, file_hash,"
            " workspace, page_map, stored_name, para_map)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filename, content_type, raw_text, norm_text, file_hash,
             workspace or "Default", json.dumps(page_map) if page_map else None,
             stored_name, json.dumps(para_map) if para_map else None)
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

# علامة الصفحة القديمة (--- صفحة N ---): المحركات الجديدة لا تحقنها في النص إطلاقاً،
# لكن الصفوف المفهرسة قبل هذا الإصدار ما زالت تحملها — نقرأها كإرث ولا نعرضها كنتائج.
_PAGE_MARKER = re.compile(r"^\s*---\s*صفحة\s*(\d+)\s*---\s*$")

def _find_line_matches(raw_text: str, tokens: list, cap: int = _HIGHLIGHT_CAP,
                       page_map: list = None, para_map: list = None):
    """
    البحث عن كل الأسطر التي تحتوي على كلمات البحث.
    أرقام الصفحات تأتي من خريطة الصفحات المخزّنة خارج النص (page_map)؛
    وللصفوف القديمة فقط نلتقطها من العلامات المتبقية داخل النص.
    أرقام الفقرات تأتي من خريطة الفقرات (para_map) وتُعاد تعيينها لكل صفحة.
    """
    matches = []
    total = 0
    legacy_page = None
    for i, line in enumerate((raw_text or "").split("\n"), start=1):
        marker = _PAGE_MARKER.match(line)
        if marker:
            legacy_page = int(marker.group(1))
            continue  # سطر العلامة القديم ليس نتيجة بحث
        if not line.strip():
            continue
        norm_line = normalize(line)
        if _line_has_match(norm_line, tokens):
            total += 1
            if len(matches) < cap:
                entry = {"line": i, "text": _highlight_line(line.strip(), tokens)}
                page = page_for_line(page_map, i) if page_map else legacy_page
                if page is not None:
                    entry["page"] = page
                para = para_for_line(para_map, i) if para_map else None
                if para is not None:
                    entry["para"] = para
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
    - الصور: كتل OCR لا "أسطر" حقيقية ← بلا أي رقم موضع (block)
    - PDF و DOCX: الصفحة هي الموضع الذي يجده القارئ فعلاً في الملف الأصلي (page)
    - TXT: أسطر حقيقية في ملف نصي ← تُعرض L (line)
    """
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "block"
    if "pdf" in ct or "wordprocessingml" in ct or ct == "application/msword":
        return "page"
    # كل ما عداه نص: السطر هو الموضع الصادق الوحيد المتاح
    return "line"

def search_documents(query: str, limit: int = 20, doc_ids: list = None, workspace: str = None) -> list:
    """البحث الذكي باستخدام FTS5 — يعيد لكل مستند جميع الأسطر المطابقة مع أرقامها.
    doc_ids: قصر البحث على مستندات بعينها. workspace: قصره على مجموعة كاملة."""
    norm_query = normalize(query)
    # تقليم علامات الترقيم من أطراف كل كلمة بحث ("تخطيطا" تعمل مثل تخطيطا)
    tokens = [t.strip(_STRIP_CHARS) for t in re.split(r"\s+", norm_query)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []

    match_query = _fts_match_expr(tokens)

    sql = """
        SELECT d.id, d.filename, d.content_type, d.raw_text, d.workspace, d.page_map,
               d.para_map,
               (d.stored_name IS NOT NULL) AS openable,
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
    if workspace:
        sql += " AND d.workspace = ?"
        params.append(workspace)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row  # لإرجاع النتائج كقواميس (Dictionaries)
    try:
        cursor = con.execute(sql, params)
        results = []
        for row in cursor.fetchall():
            page_map = json.loads(row["page_map"]) if row["page_map"] else None
            para_map = json.loads(row["para_map"]) if row["para_map"] else None
            # raw_text يُستخدم داخلياً فقط لاستخراج الأسطر ولا يُعاد كاملاً في الرد
            matches, total = _find_line_matches(row["raw_text"], tokens,
                                                page_map=page_map, para_map=para_map)
            results.append({
                "id": row["id"],
                "filename": row["filename"],
                "content_type": row["content_type"],
                "workspace": row["workspace"],
                "snippet": row["snippet"],
                "rank": row["rank"],
                "matches": matches,
                "match_count": total,
                "lang": _detect_lang(row["raw_text"]),
                "unit": _unit_for(row["content_type"]),
                "openable": bool(row["openable"]),
            })
        return results
    finally:
        con.close()

def list_documents(workspace: str = None) -> list:
    """قائمة المستندات المفهرسة — تغذّي مدير الملفات ومرشِّح النطاق في الواجهة."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT id, filename, content_type, workspace, created_at, length(raw_text) AS chars,
                   (stored_name IS NOT NULL) AS openable
            FROM documents
        """
        params = []
        if workspace:
            sql += " WHERE workspace = ?"
            params.append(workspace)
        sql += " ORDER BY created_at DESC, id DESC"
        cursor = con.execute(sql, params)
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

def delete_documents_by_ids(doc_ids: list) -> int:
    """الحذف الجماعي للملفات المحددة في مدير الملفات — عملية واحدة (Transaction)."""
    ids = [int(i) for i in (doc_ids or [])]
    if not ids:
        return 0
    con = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join("?" for _ in ids)
        cursor = con.execute(f"DELETE FROM documents WHERE id IN ({placeholders})", ids)
        con.commit()
        return cursor.rowcount
    finally:
        con.close()

def get_document(doc_id: int) -> dict:
    """بيانات مستند واحد (بلا نصه الخام) — يُستخدم لفتح الملف الأصلي."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT id, filename, content_type, workspace, created_at, stored_name"
            " FROM documents WHERE id = ?", (int(doc_id),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()

def referenced_stored_names() -> set:
    """أسماء النسخ التي ما زال يشير إليها مستند — كل ما عداها يتيم ويُحذف."""
    con = sqlite3.connect(DB_PATH)
    try:
        return {
            row[0] for row in con.execute(
                "SELECT DISTINCT stored_name FROM documents WHERE stored_name IS NOT NULL"
            )
        }
    finally:
        con.close()

def list_workspaces() -> list:
    """مساحات العمل (المجموعات) مع عدد مستندات كل واحدة — هيكلة مسطحة بلا مجلدات متداخلة."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cursor = con.execute("""
            SELECT workspace AS name, COUNT(*) AS count, SUM(length(raw_text)) AS chars
            FROM documents
            GROUP BY workspace
            ORDER BY name COLLATE NOCASE
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        con.close()

def delete_workspace(name: str) -> int:
    """حذف مجموعة كاملة بضربة واحدة. الزناد يتكفل بتنظيف فهرس FTS5."""
    con = sqlite3.connect(DB_PATH)
    try:
        cursor = con.execute("DELETE FROM documents WHERE workspace = ?", (name,))
        con.commit()
        return cursor.rowcount
    finally:
        con.close()