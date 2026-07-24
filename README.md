<p align="center">
  <img src="assets/logo.png" alt="WaraqVault" width="840">
</p>

<p align="center">
  <b>A private, fully offline desktop app for searching your Arabic &amp; English documents.</b><br>
  No cloud &middot; no account &middot; no uploads &mdash; everything stays on your machine.
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-BE9540">
  <img alt="Offline-first" src="https://img.shields.io/badge/Offline--first-0E3536">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-1C6E74">
  <img alt="SQLite FTS5" src="https://img.shields.io/badge/SQLite-FTS5-1C6E74">
</p>

---

## The idea

WaraqVault turns a scattered pile of files &mdash; PDFs, Word documents, and scanned images spread
across WhatsApp, email, and phone storage &mdash; into a **private, instantly searchable archive**
that lives entirely on your own computer. You drag documents in; you search; you get the exact file
back, with a snippet and a link to open the original. Nothing is ever uploaded.

The hard part it gets right is **Arabic search**. Most tools stumble on Arabic because they
mishandle right-to-left text, diacritics, and letter variants &mdash; so a search for one spelling
silently misses the *same word* typed another way. WaraqVault normalizes Arabic at **both index time
and query time**, so a match happens no matter how either was written.

## The differentiator &mdash; Arabic done right

| You search for | …and it still finds | They differ only by |
|---|---|---|
| `ارشيف` | `أرشيف` | hamza on the alef |
| `مستشفي` | `مستشفى` | yāʾ vs. alef maqṣūra |
| `وثيقه` | `وثيقة` | hāʾ vs. tāʾ marbūṭa |
| `مكتب` | `مُكْتَب` | diacritics (tashkīl) |

This is the part existing tools consistently get wrong &mdash; and the reason WaraqVault exists.

## How it works

```
   documents  →  INGEST  →  EXTRACT  →  NORMALIZE  →  INDEX  →  SEARCH  →  result
                 drag in    parse +     fold Arabic   SQLite    query in    open the
                            OCR         variants      FTS5      AR / EN     original
```

## Tech stack

| Layer | Tool |
|---|---|
| Engine + glue | **Python** |
| Full-text index (no server) | **SQLite + FTS5** |
| PDF / DOCX text extraction | **PyMuPDF**, **python-docx** |
| Arabic normalization | custom layer (index + query time) |
| Local web UI *(planned)* | **FastAPI** + HTML/CSS/JS |
| OCR for scans *(planned)* | **EasyOCR / Tesseract** |

> The search core is **already built and working** &mdash; see [`engine/waraq.py`](engine/waraq.py).

## Quickstart

```bash
pip install -r requirements.txt

python engine/waraq.py demo                # proof: cross-spelling Arabic search (no files needed)
python engine/waraq.py index ./my-docs     # index a folder of PDFs / DOCX / TXT
python engine/waraq.py search "أرشيف"       # search in Arabic or English
```

## What's in here

| Path | What it is |
|---|---|
| [`engine/waraq.py`](engine/waraq.py) | The search core: parse → normalize → FTS5 index → search |
| [`schema.sql`](schema.sql) | The shared SQLite schema (documents store + FTS5 index) |
| [`ui/index.html`](ui/index.html) | The themed web UI (served locally; RTL-aware, highlights matches) |
| [`docs/plan.md`](docs/plan.md) | The build plan &amp; team roles for the sprint |
| [`docs/for-ghassan.md`](docs/for-ghassan.md) | The data + OCR hand-off contract |

## Status &amp; roadmap

- [x] Arabic normalization (applied at index **and** query time)
- [x] SQLite **FTS5** index + ranked search with snippets
- [ ] PDF / DOCX / TXT parsing
- [x] Themed web UI design
- [x] FastAPI server wiring the UI to the engine
- [x] Drag-and-drop ingest
- [x] OCR for scanned images

## Team

- **Link-Top** — The Infrastructure & Data Pipeline: Built the core FastAPI backend, hybrid ingestion routing (PyMuPDF & EasyOCR), foundational SQLite FTS5 setup, and endpoint integration.
- **AnmarTiger** — The Frontend & Search Logic: Developed the Web UI (drag-and-drop), the Arabic normalization algorithm, and advanced FTS5 search mechanics (BM25 ranking, snippet highlighting, and page/line extraction).

## License

[MIT](LICENSE) &mdash; free and open source.
