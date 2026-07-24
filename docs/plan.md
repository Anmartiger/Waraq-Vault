# WaraqVault — Current Status & Roles

A focused, demo-first plan for a working product that proves the Arabic search differentiator. 

## Stack & Architecture (Locked)
- **Engine/DB:** Python + SQLite FTS5 (Implemented in `engine/database.py`).
- **Data Ingestion:** Hybrid processing (PyMuPDF for PDFs + EasyOCR for Images).
- **Server:** FastAPI (`main.py`) serving a local API on `127.0.0.1`.
- **UI:** HTML/CSS/JS in `ui/index.html`.

## Roles (Updated to reflect current progress)
- **Little Elephant (Backend & API) - [COMPLETED]**
  Owns the entire data pipeline. Successfully built the FastAPI server, the SQLite FTS5 database, the OCR/PDF integration, and the Arabic normalization logic. The backend is 100% locked and functional.
- **Tiger (Frontend & UI) - [PENDING]**
  Owns the product surface. Responsible for writing the JavaScript in `ui/index.html` to connect the frontend to the existing `/upload` and `/search` endpoints.

## The Integration Contract
The UI simply calls the API endpoints. 
- `POST /upload` -> Handles files and indexes them automatically.
- `GET /search?q=...` -> Returns normalized Arabic search results with snippets.
No direct DB queries are allowed from the UI.