#!/usr/bin/env python3
"""
WaraqVault — search-core validation spike (Python).

Proves the design end-to-end before the Rust build:
    parse  ->  normalize (Arabic-aware)  ->  FTS5 index  ->  search

This is a THROWAWAY prototype to validate behaviour (especially Arabic
normalization). The real thing gets built in Rust once the toolchain is
installed — but the schema.sql and the normalize() rules port 1:1.

Usage:
    python waraq.py demo                 # self-contained proof, no files needed
    python waraq.py index <folder>       # index real .pdf/.docx/.txt into waraq.db
    python waraq.py search <query...>    # search waraq.db (Arabic or English)
"""
import sys, re, sqlite3
from pathlib import Path

# make Arabic print correctly regardless of the Windows console codepage
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SCHEMA = (HERE.parent / "schema.sql").read_text(encoding="utf-8")

# ---------------------------------------------------------------- normalize
# Strip Arabic diacritics / tatweel, then fold the letter variants that make
# the same word look different. Applied at BOTH index time and query time.
_MARKS = re.compile("[ـً-ٰٟۖ-ۭ]")  # tatweel + harakat + Quranic marks (NOT the digits 0660-0669)
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",   # alef + hamza forms  -> bare alef
    "ى": "ي", "ئ": "ي",                       # alef maqsura / hamza-on-ya -> ya
    "ؤ": "و",                                  # hamza-on-waw -> waw
    "ة": "ه",                                  # ta marbuta -> ha
    "ـ": "",                                    # tatweel (kashida)
})

def normalize(text: str) -> str:
    return _MARKS.sub("", text).translate(_FOLD).lower()

# ---------------------------------------------------------------- parse
def parse(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    if ext == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"unsupported file type: {ext}")

def guess_lang(text: str) -> str:
    ar = sum(1 for ch in text if "؀" <= ch <= "ۿ")
    letters = sum(1 for ch in text if ch.isalpha())
    if not letters:
        return "en"
    r = ar / letters
    return "ar" if r > 0.6 else ("mixed" if r > 0.15 else "en")

# ---------------------------------------------------------------- db
def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    return con

def _insert(con, path, filename, ext, size, source, text):
    con.execute(
        "INSERT INTO documents(path,filename,ext,size,source,lang,raw_text,normalized_text)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (path, filename, ext, size, source, guess_lang(text), text, normalize(text)),
    )
    con.commit()

def index_file(con, path: Path):
    text = parse(path)
    _insert(con, str(path), path.name, path.suffix.lower().lstrip("."),
            path.stat().st_size, "parsed", text)

# ---------------------------------------------------------------- search
def search(con, query: str, limit: int = 20):
    tokens = [t for t in re.split(r"\s+", normalize(query)) if t]
    if not tokens:
        return []
    match = " ".join(f'"{t}"*' for t in tokens)          # prefix match, AND-ed
    return con.execute(
        "SELECT d.filename, d.path, d.lang,"
        "       snippet(documents_fts,0,'[',']','…',12),"
        "       bm25(documents_fts) AS rank "
        "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
        "WHERE documents_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, limit),
    ).fetchall()

# ---------------------------------------------------------------- demo
def demo():
    con = connect(":memory:")
    # Each doc stores the HARD spelling (diacritics / hamza / alef-maqsura / ta-marbuta).
    docs = [
        ("عقد_ايجار.txt",  "عقد إيجار مكتَب تجاري في وسط البلد"),        # مكتَب  (fatha)
        ("تقرير_طبي.txt",  "تقرير صادر عن مستشفى الأمل التخصصي"),        # مستشفى (alef maqsura)
        ("سياسة.txt",      "سياسة أرشيف الملفات والنسخ الاحتياطي"),      # أرشيف  (hamza)
        ("رسالة.txt",      "هذه وثيقة رسمية مهمة للغاية"),               # وثيقة  (ta marbuta)
        ("readme_en.txt",  "Archive indexing and full-text search core"),
    ]
    for name, text in docs:
        _insert(con, name, name, "txt", len(text.encode()), "demo", text)

    print("normalize() folds the variants to one key:")
    for w in ["مكتَب", "مستشفى", "أرشيف", "وثيقة"]:
        print(f"    {w:<8} → {normalize(w)}")

    # Queries deliberately use the OTHER spelling than the docs.
    tests = [
        ("مكتب",     "office — query is plain, doc had a diacritic (مكتَب)"),
        ("مستشفي",   "hospital — query uses ya, doc has alef-maqsura (مستشفى)"),
        ("ارشيف",    "archive — query is bare alef, doc has hamza (أرشيف)"),
        ("وثيقه",    "document — query uses ha, doc has ta-marbuta (وثيقة)"),
        ("indexing", "English path still works"),
    ]
    print("\ncross-spelling search (each query is spelled differently than the document):")
    ok = 0
    for q, why in tests:
        hits = search(con, q)
        mark = "✓" if hits else "✗"
        ok += bool(hits)
        top = f'{hits[0][0]}  "{hits[0][3]}"' if hits else "(no match)"
        print(f"    {mark}  search «{q}»  →  {top}")
        print(f"           {why}")
    print(f"\n{ok}/{len(tests)} matched. This is the differentiator: same word, different spelling, still found.")

# ---------------------------------------------------------------- cli
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "demo":
        demo()
    elif cmd == "index":
        if len(sys.argv) < 3:
            sys.exit("usage: python waraq.py index <folder>")
        con = connect("waraq.db")
        n = 0
        for p in Path(sys.argv[2]).rglob("*"):
            if p.suffix.lower() in (".pdf", ".docx", ".txt") and p.is_file():
                try:
                    index_file(con, p); n += 1; print("indexed:", p)
                except Exception as e:
                    print("skip:", p, "->", e)
        print(f"done — {n} file(s) indexed into waraq.db")
    elif cmd == "search":
        con = connect("waraq.db")
        q = " ".join(sys.argv[2:])
        rows = search(con, q)
        if not rows:
            print("no matches for:", q); return
        for fn, path, lang, snip, rank in rows:
            print(f"{fn}  [{lang}]  (score {-rank:.2f})\n    …{snip}…\n    {path}\n")
    else:
        import difflib
        near = difflib.get_close_matches(cmd, ["demo", "index", "search"], n=1)
        print(f"unknown command: {cmd!r}")
        if near:
            print(f'did you mean:  python waraq.py {near[0]} ' +
                  ("<folder>" if near[0] == "index" else '"your query"' if near[0] == "search" else ""))
        print("commands:  demo  |  index <folder>  |  search <query>")

if __name__ == "__main__":
    main()
