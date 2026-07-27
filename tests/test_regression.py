"""WaraqVault — end-to-end regression suite (stubbed OCR, throwaway DB).

Covers: format sniffing, batch upload rules, duplicates, job progress and
cancellation, deletion with FTS sync, scoped search, Arabic proclitic recall,
strict short-token matching, language detection and per-format units.

Run:  .venv/Scripts/python.exe tests/test_regression.py   (needs: pip install httpx)
The real waraq.db is never touched."""
import sys, os, types, time, tempfile, sqlite3
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = 0, []
def check(name, cond, extra=""):
    global PASS
    if cond: PASS += 1; print(f"  OK   {name}")
    else: FAIL.append(name); print(f"  FAIL {name} {extra}")

# ---- stub the OCR engine BEFORE anything imports it (no EasyOCR load) ----
fake = types.ModuleType("engine.ocr_engine")
fake.GPU_AVAILABLE = False
fake.GPU_NAME = None
fake.OCR_DEVICE = "CPU (stub)"
fake.DELAY = 0.0
def _run_ocr(image):
    if fake.DELAY: time.sleep(fake.DELAY)
    return ["سطر عربي من OCR", "stub ocr line"]
fake.run_ocr = _run_ocr
fake.extract_text_from_image = lambda src: " \n ".join(_run_ocr(src))
fake.reader = None
sys.modules["engine.ocr_engine"] = fake

from engine import database
TMPDB = Path(tempfile.gettempdir()) / "waraq_test_problems.db"
if TMPDB.exists(): TMPDB.unlink()
database.DB_PATH = TMPDB

import main
from fastapi.testclient import TestClient
import fitz

PNG = b"\x89PNG\r\n\x1a\n" + b"fakepngdata-A"
PNG2 = b"\x89PNG\r\n\x1a\n" + b"fakepngdata-B"
PNG3 = b"\x89PNG\r\n\x1a\n" + b"fakepngdata-C"

def blank_pdf(pages):
    d = fitz.open()
    for _ in range(pages): d.new_page()
    data = d.tobytes(); d.close(); return data

def wait_job(client, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.05)
    raise TimeoutError(job_id)

def upload(client, files, **form):
    payload = [("file", f) for f in files]
    return client.post("/upload", files=payload, data={k: str(v).lower() for k, v in form.items()})

def _zip_nondocx():
    import io, zipfile as zf
    buf = io.BytesIO()
    with zf.ZipFile(buf, "w") as z: z.writestr("data/readme.txt", "hello")
    return buf.getvalue()

client = TestClient(main.app)
with client:
    print("\n=== P4: detect_kind — extension → content-type → magic/content sniffing ===")
    dk = main.detect_kind
    check("pdf by magic, no ext/ctype",  dk("weird", "", b"%PDF-1.7 xx") == "pdf")
    check("png by magic",                dk("noext", "application/octet-stream", PNG) == "image")
    check("jpeg by magic",               dk("noext", "", b"\xff\xd8\xff\xe0junk") == "image")
    check("arabic utf-8 text, no ext",   dk("هندسة_AI", "application/octet-stream", "نص عربي عادي".encode("utf-8")) == "txt")
    check("cp1256 text, no ext",         dk("قديم", "", "ملف عربي قديم".encode("cp1256")) == "txt")
    check("binary w/ NUL rejected",      dk("blob", "application/octet-stream", b"\x01\x02\x00\x04" * 100) is None)
    check("plain zip is NOT docx",       dk("archive", "", __import__("io").BytesIO and _zip_nondocx()) is None)

    print("\n=== upload validation: fail fast before any processing ===")
    r = upload(client, [("empty.png", b"", "image/png")])
    check("0-byte file -> 400", r.status_code == 400, r.text)
    r = upload(client, [(f"i{i}.png", PNG + bytes([i]), "image/png") for i in range(6)])
    check("6 files -> 400 (max 5)", r.status_code == 400, r.text)
    r = upload(client, [("a.png", PNG, "image/png"), ("b.pdf", b"%PDF-1.7", "application/pdf")])
    check("mixed batch -> 400 (images only)", r.status_code == 400, r.text)
    r = upload(client, [("old.doc", b"junk", "application/msword")])
    check(".doc -> 400 with guidance", r.status_code == 400 and "docx" in r.text)

    print("\n=== P4 end-to-end: extensionless Arabic text file becomes searchable ===")
    r = upload(client, [("هندسة_AI", "المرجل يعمل بتقنية الضغط العالي".encode("utf-8"), "application/octet-stream")])
    check("202 + job id", r.status_code == 202 and "job_id" in r.json(), r.text)
    j = wait_job(client, r.json()["job_id"])
    check("job done, file indexed", j["state"] == "done" and j["result"]["indexed"] == ["هندسة_AI"])
    s = client.get("/search", params={"q": "الضغط"}).json()
    check("its content is searchable", s["count"] == 1 and s["results"][0]["filename"] == "هندسة_AI")
    check("stored as txt => unit line", s["results"][0]["unit"] == "line")

    print("\n=== Feature: multi-image batch (3 images) with per-item statuses ===")
    r = upload(client, [("imgA.png", PNG, "image/png"), ("imgB.png", PNG2, "image/png"), ("imgC.png", PNG3, "image/png")])
    check("batch accepted 202", r.status_code == 202, r.text)
    j = wait_job(client, r.json()["job_id"])
    st = [i["status"] for i in j["items"]]
    check("all 3 indexed", j["result"]["indexed"] == ["imgA.png", "imgB.png", "imgC.png"], str(j["result"]))
    check("per-item statuses recorded", st == ["indexed"] * 3, str(st))

    print("\n=== Feature: duplicates — single 409, batch skip, overwrite replaces ===")
    r = upload(client, [("imgA.png", PNG, "image/png")])
    check("single dup -> 409 sync (no OCR wasted)", r.status_code == 409 and r.json()["detail"]["match"] == "content")
    r = upload(client, [("imgA.png", PNG, "image/png"), ("imgD.png", PNG + b"D", "image/png")])
    j = wait_job(client, r.json()["job_id"])
    check("batch dup skipped, new indexed",
          j["result"]["skipped"] == ["imgA.png"] and j["result"]["indexed"] == ["imgD.png"], str(j["result"]))
    check("skipped item carries reason", any(i["status"] == "skipped" and i["detail"] for i in j["items"]))
    r = upload(client, [("imgA.png", PNG, "image/png")], overwrite=True)
    j = wait_job(client, r.json()["job_id"])
    check("overwrite replaces (no duplicate rows)", j["state"] == "done" and j["result"]["replaced"] >= 1, str(j["result"]))
    con = sqlite3.connect(TMPDB)
    n = con.execute("SELECT COUNT(*) FROM documents WHERE filename='imgA.png'").fetchone()[0]
    check("exactly one imgA row remains", n == 1, f"rows={n}")
    con.close()

    print("\n=== P7/P1: image results — OCR runs, unit=block (no fake line numbers) ===")
    s = client.get("/search", params={"q": "stub"}).json()
    img = next(x for x in s["results"] if x["filename"] == "imgA.png")
    check("image unit is block", img["unit"] == "block")
    check("image matches carry no page", all("page" not in m for m in img["matches"]))

    print("\n=== P7: PDF pipeline — real progress events, queue, cancellation ===")
    fake.DELAY = 0.35
    r = upload(client, [("big_scan.pdf", blank_pdf(4), "application/pdf")])
    job_id = r.json()["job_id"]
    saw_pages, saw_progress = False, False
    for _ in range(100):
        j = client.get(f"/jobs/{job_id}").json()
        if j["total_units"] == 4: saw_pages = True
        if j["state"] == "processing" and j["done_units"] >= 1:
            saw_progress = True; break
        time.sleep(0.05)
    check("total = real page count (4)", saw_pages)
    check("done_units advances per completed page", saw_progress)
    rc = client.post(f"/jobs/{job_id}/cancel")
    check("cancel accepted", rc.status_code == 200 and rc.json()["cancelled"] is True)
    j = wait_job(client, job_id)
    check("job ends cancelled", j["state"] == "cancelled")
    docs = client.get("/documents").json()["documents"]
    check("cancelled pdf NOT indexed (no partial rows)", all(d["filename"] != "big_scan.pdf" for d in docs))
    fake.DELAY = 0.0

    print("\n=== P8: force_ocr flag reaches the PDF engine ===")
    calls = {}
    orig = main.process_hybrid_pdf
    def spy(pdf_bytes, ocr_fn, force_ocr=False, progress=None, is_cancelled=None):
        calls["force_ocr"] = force_ocr
        return orig(pdf_bytes, ocr_fn, force_ocr=force_ocr, progress=progress, is_cancelled=is_cancelled)
    main.process_hybrid_pdf = spy
    r = upload(client, [("hybrid.pdf", blank_pdf(1), "application/pdf")], force_ocr=True)
    wait_job(client, r.json()["job_id"])
    main.process_hybrid_pdf = orig
    check("force_ocr=True propagated", calls.get("force_ocr") is True)

    print("\n=== Feature: deletion — cascade to FTS, no orphans, 404 on missing ===")
    docs = client.get("/documents").json()["documents"]
    victim = next(d for d in docs if d["filename"] == "imgD.png")
    r = client.delete(f"/documents/{victim['id']}")
    check("delete -> 200", r.status_code == 200 and r.json()["deleted"] == 1)
    check("second delete -> 404", client.delete(f"/documents/{victim['id']}").status_code == 404)
    con = sqlite3.connect(TMPDB)
    nd = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    nf = con.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
    con.close()
    check("FTS rows == document rows (no orphans)", nd == nf, f"docs={nd} fts={nf}")
    s = client.get("/search", params={"q": "stub"}).json()
    check("deleted doc gone from search", all(x["filename"] != "imgD.png" for x in s["results"]))

    print("\n=== Feature: scoped search (doc_id filter) ===")
    all_hits = client.get("/search", params={"q": "stub"}).json()
    one = all_hits["results"][0]
    scoped = client.get("/search", params={"q": "stub", "doc_id": one["id"]}).json()
    check("multiple docs unscoped", all_hits["count"] >= 2, str(all_hits["count"]))
    check("scoped -> only the chosen doc", scoped["count"] == 1 and scoped["results"][0]["id"] == one["id"])
    check("clearing scope restores corpus", client.get("/search", params={"q": "stub"}).json()["count"] == all_hits["count"])

    print("\n=== P2: proclitic recall — تخطيطا finds وتخطيطا (no stemmer, no reindex) ===")
    database.insert_document("plan.txt", "text/plain", "كان وتخطيطا للمستقبل واضحا في المشروع", "h-plan")
    res = database.search_documents("تخطيطا")
    hit = next((r_ for r_ in res if r_["filename"] == "plan.txt"), None)
    check("document found via FTS expansion", hit is not None)
    check("وتخطيطا highlighted", hit and "<b>وتخطيطا</b>" in hit["matches"][0]["text"], hit and hit["matches"][0]["text"])
    res = database.search_documents("بالتخطيط")   # user types WITH prefix, doc has bare form?
    # (reverse direction is stemming territory — not claimed; just must not crash)
    check("prefixed query does not crash", isinstance(res, list))

    print("\n=== P3: short tokens are exact — no more false positives/highlights ===")
    database.insert_document("prep1.txt", "text/plain", "ذهبت مع اخي الي السوق", "h-p1")
    database.insert_document("prep2.txt", "text/plain", "هذه المعلومات مفيدة جدا", "h-p2")
    database.insert_document("prep3.txt", "text/plain", "فيلم جميل عن تحفيزه الدائم", "h-p3")
    names = lambda rs: {r_["filename"] for r_ in rs}
    r1 = database.search_documents("مع")
    check("'مع' finds the real preposition", "prep1.txt" in names(r1))
    check("'مع' does NOT drag in المعلومات", "prep2.txt" not in names(r1), str(names(r1)))
    r2 = database.search_documents("في")
    check("'في' does NOT match فيلم/تحفيزه", "prep3.txt" not in names(r2), str(names(r2)))
    hit = next((r_ for r_ in database.search_documents("تخطيطا") if r_["filename"] == "plan.txt"), None)
    check("highlight stays word-bounded", hit and "<b>في</b>" not in hit["matches"][0]["text"])
    r3 = database.search_documents("معلومات")
    check("'معلومات' (≥3) still prefix-matches المعلومات", "prep2.txt" in names(r3))

    print("\n=== P5: real language detection (ar / en / mixed) ===")
    database.insert_document("en.txt", "text/plain", "pure english content about life and money", "h-en")
    database.insert_document("mix.txt", "text/plain", "تقرير المشروع النهائي final project report with english details مكتمل", "h-mx")
    langs = {r_["filename"]: r_["lang"] for r_ in database.search_documents("مشروع") + database.search_documents("english") + database.search_documents("money")}
    check("arabic doc -> ar", langs.get("plan.txt") == "ar", str(langs))
    check("english doc -> en", langs.get("en.txt") == "en", str(langs))
    check("mixed doc -> mixed", langs.get("mix.txt") == "mixed", str(langs))

    print("\n=== P6: DOCX results use paragraph units (¶ in the UI) ===")
    database.insert_document("word.docx", main._DOCX_TYPE, "--- صفحة 1 ---\nفقرة اولى عن الارشيف\nفقرة ثانية", "h-dx")
    hit = next(r_ for r_ in database.search_documents("الارشيف") if r_["filename"] == "word.docx")
    check("docx unit is para", hit["unit"] == "para")
    check("docx keeps its page number", hit["matches"][0].get("page") == 1)

    print("\n=== hardening: quoted/punctuated queries don't break FTS ===")
    check('quoted "مع" behaves like مع', names(database.search_documents('"مع"')) == names(r1))
    check("lone punctuation query -> empty, no crash", database.search_documents('"" !!') == [])

    print("\n=== /status reports the OCR device ===")
    st = client.get("/status").json()
    check("device string present", "CPU (stub)" in st["ingestion_pipeline"], st["ingestion_pipeline"])

print(f"\n{'='*60}\nPASSED: {PASS}   FAILED: {len(FAIL)}")
for f in FAIL: print("  ✗", f)
if TMPDB.exists(): TMPDB.unlink()
print("temp DB removed; real waraq.db untouched")
sys.exit(1 if FAIL else 0)
