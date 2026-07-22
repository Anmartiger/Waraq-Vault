# WaraqVault — data & OCR hand-off (for Ghassan)

WaraqVault is an offline desktop app that makes someone's Arabic + English documents
searchable, entirely on their own machine. It's **one local SQLite database**. Two sides
write into it:

- **You** — OCR + the data/store layer: read text out of scanned images/photos, and own the
  `documents` table.
- **Anmar** — search: the full-text index (`documents_fts`) and the queries on top of it.

The schema below is our **shared contract**. Both sides `INSERT` into `documents`; the triggers
keep the search index in sync automatically — you don't touch `documents_fts` directly.

---

## Schema (SQLite + FTS5)

```sql
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL,        -- absolute path in the local archive
    filename        TEXT NOT NULL,
    ext             TEXT,                 -- pdf | docx | png | jpg | txt ...
    size            INTEGER,
    added_at        INTEGER DEFAULT (strftime('%s','now')),
    source          TEXT,                 -- 'parsed' (Anmar)  |  'ocr' (Ghassan)
    lang            TEXT,                 -- 'ar' | 'en' | 'mixed'
    ocr_confidence  REAL,                 -- NULL for parsed docs; you fill it for OCR
    raw_text        TEXT,                 -- text exactly as extracted
    normalized_text TEXT                  -- Arabic-normalized copy (this is what gets indexed)
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    normalized_text,
    content='documents',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, normalized_text) VALUES (new.id, new.normalized_text);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, normalized_text) VALUES ('delete', old.id, old.normalized_text);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, normalized_text) VALUES ('delete', old.id, old.normalized_text);
    INSERT INTO documents_fts(rowid, normalized_text) VALUES (new.id, new.normalized_text);
END;
```

---

## Your part

### 1. The OCR function — what it should return
```
extract(image_path)  ->  { text: string, lang: "ar" | "en" | "mixed", confidence: 0.0–1.0 }
```
- **text** — the recognized text (Arabic + English). Keep normal reading order; **don't** strip
  diacritics or "clean" the Arabic — the search side handles that.
- **lang** — your best guess at the language.
- **confidence** — how sure OCR is (0–1). Store it so low-confidence scans can be flagged later.

### 2. Columns you set when inserting an OCR'd document
| column | you set it to |
|---|---|
| `path` | absolute path of the source image/PDF |
| `filename` | the file name |
| `ext` | `png` / `jpg` / `pdf` … |
| `size` | file size in bytes |
| `source` | `'ocr'` |
| `lang` | your detected language |
| `ocr_confidence` | your 0–1 score |
| `raw_text` | the OCR text |
| `normalized_text` | **leave to the shared step — see note below** |

### 3. Important: don't reimplement Arabic normalization
`normalized_text` is what actually gets searched. The search side owns **one** `normalize()`
function (it folds diacritics, alef/hamza/ya variants, tāʾ-marbūṭa). When we integrate, your OCR
text passes through the **same insert function** Anmar's parser uses, which fills
`normalized_text` for you. This keeps OCR'd and parsed documents searching identically.

> For your own standalone testing, just set `normalized_text = raw_text` as a placeholder so a
> row is insertable; the real value gets filled at integration.

### 4. Example — inserting one OCR'd scan
```sql
INSERT INTO documents
  (path, filename, ext, size, source, lang, ocr_confidence, raw_text, normalized_text)
VALUES
  ('C:\archive\scan_042.png', 'scan_042.png', 'png', 384210, 'ocr', 'ar', 0.93,
   'نص من الصورة الممسوحة ضوئيًا', 'نص من الصورة الممسوحة ضوئيا');  -- placeholder normalized_text
```

---

## What to agree on now
1. **The columns above** — if OCR needs more fields (page number, source folder, a "needs
   review" flag for low confidence), say so now and we'll add them.
2. **Normalization lives on the search side only** — one implementation, applied to everything,
   so results are consistent.

Questions → ping Anmar.
