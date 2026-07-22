# WaraqVault — build plan & roles

A focused, demo-first plan for a ~2-week sprint. The goal is a **working product that proves the
Arabic search differentiator**, not a production platform.

## Stack decision

**All-Python, browser-based UI.** No Rust/Tauri on the critical path.

- Engine: Python + SQLite **FTS5** + PyMuPDF (PDF) + python-docx (DOCX) + the Arabic normalizer.
- Server: **FastAPI** (or Flask) — a tiny local server on `127.0.0.1`.
- UI: the themed **HTML/CSS** in [`ui/index.html`](../ui/index.html), served locally + drag-and-drop.
- OCR: one library, integrated fast.

Why Python is the right call here: the heavy lifting is SQLite FTS5 (C) and OCR (C/C++); Python is
just orchestration, so the speed difference is imperceptible for a local, single-user, offline app.
In our own testing, PyMuPDF extracted Arabic from PDFs **correctly**, which not every tool does.

## Roles — engine vs. shell (one owner for the database)

- **Tiger — the engine.** Owns everything data: PDF/DOCX parsing, Arabic normalization, the entire
  schema + FTS5 index, and the search functions. Nobody else touches the database.
- **Little Elephant — the shell.** Owns the product surface: the FastAPI server, the web UI +
  drag-and-drop, and OCR integration.

### The integration contract (prevents merge pain)
Tiger ships a Python module that is the **only** code that opens the DB, exposing ~4 functions:

```
engine.index_path(path)                                    # digital files: parse → normalize → index
engine.add_document(path, text, source, lang, confidence)  # OCR text (or any text)
engine.search(query) -> [ {filename, path, snippet, lang, score} ]
engine.stats()
```

The UI and OCR **call these functions** — they never write SQL. OCR flow: image → text →
`engine.add_document(..., source="ocr")`.

## Timeline (~2 weeks — adjust to your deadline, keep a buffer)

- **Days 1–2** — Vertical slice: engine as an importable module + FastAPI serving the UI; search
  works end-to-end in the browser.
- **Days 3–5** — Ingest (drag-and-drop → `index_path`) + OCR (pick a library, timeboxed; wire it in).
- **Days 6–8** — Make Arabic bulletproof: build a real, messy test corpus; fix normalization edge
  cases, snippet quality, and ranking.
- **Days 9–11** — Polish the demo surface: result cards, highlighting, open-file, empty/loading states.
- **Days 12–13** — Rehearse the demo + prepare the pitch.
- **Day 14** — Buffer + final polish.

## OCR pick (timeboxed)
Test **EasyOCR** (usually stronger on Arabic) vs **pytesseract/Tesseract + Arabic pack** (lighter)
on **one** representative Arabic scan. Pick within an hour — cleanest Arabic reading wins.

## Out of scope (protect the timeline)
Rust/Tauri, native installer, open-format export, "scalability", multi-user, cloud, settings screens.

## The winning demo
Type an Arabic word one way → WaraqVault finds a document that spelled it another way (diacritics /
hamza / yāʾ). Show a naive tool failing on the same query. Close with: *"100% offline — your
documents never leave your machine."* Rehearse that 3-minute path until it's boring.
