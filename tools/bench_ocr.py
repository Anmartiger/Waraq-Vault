"""
OCR benchmark harness for WaraqVault.

Measures the speed *and* the accuracy cost of every OCR knob, so a pipeline
change can be argued with numbers instead of a hunch. Accuracy is reported as
similarity against a baseline run, because a setting that is 40% faster and 20%
worse at reading Arabic is not an optimisation.

Usage
-----
    .venv/Scripts/python.exe tools/bench_ocr.py --file "scan.pdf" --pages 3
    .venv/Scripts/python.exe tools/bench_ocr.py --file "scan.pdf" --zoom 1.0,1.5,2.0,3.0
    .venv/Scripts/python.exe tools/bench_ocr.py --file "scan.pdf" --threads 4,8,16,31

Notes
-----
* The first run loads the EasyOCR models (~6 s) — that is excluded from timings.
* --threads only means anything on CPU; on GPU the sweep is skipped.
* Render time is reported separately from OCR time, because only OCR is the
  expensive half and only render time changes with --zoom.
"""

import argparse
import difflib
import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


def render_pages(path: Path, zoom: float, limit: int):
    """Return a list of RGB numpy arrays, rendered at the given zoom factor."""
    import numpy as np

    if path.suffix.lower() in IMAGE_EXTS:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        if zoom != 1.0:
            img = img.resize((int(img.width * zoom), int(img.height * zoom)), Image.LANCZOS)
        return [np.asarray(img)]

    import fitz
    doc = fitz.open(path)
    pages = []
    try:
        for page_num in range(min(limit, len(doc))):
            pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 4:
                arr = arr[:, :, :3]
            pages.append(arr.copy())   # copy: the pixmap buffer dies with `pix`
            del pix
    finally:
        doc.close()
    return pages


def similarity(a: str, b: str) -> float:
    """Normalised-text similarity, using the same folding the search index uses."""
    from engine.database import normalize
    na, nb = normalize(a), normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def run_config(ocr_engine, pages, label):
    """Time OCR over pre-rendered pages and return (seconds, text)."""
    from engine.textflow import smart_join
    chunks = []
    started = time.perf_counter()
    for arr in pages:
        chunks.append(smart_join(ocr_engine.run_ocr(arr)))
    elapsed = time.perf_counter() - started
    return elapsed, "\n".join(chunks)


def main():
    ap = argparse.ArgumentParser(description="Benchmark the WaraqVault OCR pipeline.")
    ap.add_argument("--file", required=True, help="a scanned PDF or an image to benchmark")
    ap.add_argument("--pages", type=int, default=3, help="how many PDF pages to use (default 3)")
    ap.add_argument("--zoom", default="1.5,2.0,3.0", help="render zoom factors to sweep")
    ap.add_argument("--threads", default="", help="CPU thread counts to sweep, e.g. 8,16,31")
    ap.add_argument("--baseline-zoom", type=float, default=2.0,
                    help="the zoom production uses today; accuracy is measured against it")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"file not found: {path}")
        return 1

    print("Loading OCR models…")
    load_started = time.perf_counter()
    from engine import ocr_engine
    print(f"  ready in {time.perf_counter() - load_started:.1f}s on {ocr_engine.OCR_DEVICE}\n")

    zooms = [float(z) for z in args.zoom.split(",") if z.strip()]
    if args.baseline_zoom not in zooms:
        zooms.insert(0, args.baseline_zoom)
    zooms = sorted(set(zooms))

    # ---- baseline (what production does today) -----------------------------
    render_started = time.perf_counter()
    base_pages = render_pages(path, args.baseline_zoom, args.pages)
    base_render = time.perf_counter() - render_started
    n = len(base_pages)
    print(f"Benchmarking {n} page(s) from {path.name}")
    print(f"Baseline: zoom {args.baseline_zoom} (production default)\n")

    base_secs, base_text = run_config(ocr_engine, base_pages, "baseline")
    rows = [{
        "config": f"zoom {args.baseline_zoom} (baseline)",
        "render": base_render / n, "ocr": base_secs / n,
        "chars": len(base_text), "acc": 1.0,
    }]

    # ---- zoom sweep --------------------------------------------------------
    for z in zooms:
        if z == args.baseline_zoom:
            continue
        t0 = time.perf_counter()
        pages = render_pages(path, z, args.pages)
        render = time.perf_counter() - t0
        secs, text = run_config(ocr_engine, pages, f"zoom {z}")
        rows.append({
            "config": f"zoom {z}", "render": render / n, "ocr": secs / n,
            "chars": len(text), "acc": similarity(base_text, text),
        })

    # ---- thread sweep (CPU only) ------------------------------------------
    thread_list = [int(t) for t in args.threads.split(",") if t.strip()]
    if thread_list and ocr_engine.GPU_AVAILABLE:
        print("(--threads ignored: OCR is running on the GPU)\n")
    elif thread_list:
        import torch
        original = torch.get_num_threads()
        for t in thread_list:
            torch.set_num_threads(t)
            secs, text = run_config(ocr_engine, base_pages, f"{t} threads")
            rows.append({
                "config": f"{t} CPU threads", "render": base_render / n, "ocr": secs / n,
                "chars": len(text), "acc": similarity(base_text, text),
            })
        torch.set_num_threads(original)

    # ---- report ------------------------------------------------------------
    print(f"{'config':<26}{'render s/pg':>12}{'ocr s/pg':>11}{'total s/pg':>12}"
          f"{'chars':>9}{'accuracy':>10}{'speedup':>9}")
    print("-" * 89)
    base_total = rows[0]["render"] + rows[0]["ocr"]
    for r in rows:
        total = r["render"] + r["ocr"]
        speedup = base_total / total if total else 0
        flag = "" if r["acc"] >= 0.98 else ("  ⚠ accuracy loss" if r["acc"] >= 0.90 else "  ✗ BAD")
        print(f"{r['config']:<26}{r['render']:>12.2f}{r['ocr']:>11.2f}{total:>12.2f}"
              f"{r['chars']:>9}{r['acc']:>9.1%}{speedup:>8.2f}x{flag}")

    print("\nAccuracy is similarity to the baseline text after Arabic normalisation.")
    print("Treat anything below ~98% as a real quality regression, not a rounding error.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
