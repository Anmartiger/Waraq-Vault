-- WaraqVault — shared SQLite schema  (DRAFT v0.1 — review with Ghassan)
--
-- One database file, two owners:
--   documents      : document / content store   (Ghassan — data layer; OCR writes rows here)
--   documents_fts  : FTS5 full-text index        (Anmar   — indexing + search)
--
-- Both sides read/write this file, so THIS SCHEMA IS THE CONTRACT between us.
-- Anmar's parser and Ghassan's OCR both INSERT into `documents`; the triggers
-- keep the search index in sync automatically.

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL,        -- absolute path in the local archive
    filename        TEXT NOT NULL,
    ext             TEXT,                 -- pdf | docx | png | jpg | txt ...
    size            INTEGER,
    added_at        INTEGER DEFAULT (strftime('%s','now')),
    source          TEXT,                 -- 'parsed' (Anmar)  |  'ocr' (Ghassan)
    lang            TEXT,                 -- 'ar' | 'en' | 'mixed'
    ocr_confidence  REAL,                 -- NULL for parsed docs; Ghassan fills for OCR
    raw_text        TEXT,                 -- text exactly as extracted
    normalized_text TEXT                  -- Arabic-normalized copy (this is what gets indexed)
);

-- External-content FTS5 index over the normalized text.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    normalized_text,
    content='documents',
    content_rowid='id',
    tokenize='unicode61'
);

-- Keep documents_fts in lock-step with documents.
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
