"""
خط أنابيب الرفع: يفحص الدفعة ويرفض بسرعة (Fail Fast) قبل أي معالجة ثقيلة،
ثم يعالج كل ملف داخل مهمة خلفية ويفهرسه.
"""
import hashlib
import os

from fastapi import HTTPException

from engine import ocr_engine, jobs, storage
from engine.jobs import JobCancelled
from engine.pdf_engine import process_hybrid_pdf, pdf_precheck, parse_page_selection
from engine.docx_engine import process_docx
from engine.text_engine import process_txt
from engine.textflow import join_ocr
from engine.database import insert_document, find_duplicate, delete_documents
from services.file_detection import detect_kind, verify_content_matches, FALLBACK_CONTENT_TYPES

# سياسة الدفعات: الاستخراج النصي سريع فلا داعي لخنق المستخدم بملف واحد،
# أما الصور (OCR ثقيل) فتبقى محدودة، و Force OCR يعيد التقييد الصارم.
MAX_IMAGES_PER_BATCH = 5      # الحد الأقصى للصور في الرفعة الواحدة
_CONFIRM_SCANNED_PAGES = 5    # فوق هذا العدد نسأل المستخدم (ولا نرفض أبداً)
_EST_SEC_PER_PAGE_GPU = (1.5,  8.0)   # (min, max) — varies by text density & image noise
_EST_SEC_PER_PAGE_CPU = (15.0, 40.0)  # (min, max) — varies by text density & image noise


async def prepare_upload_batch(files, *, overwrite: bool, force_ocr: bool,
                                workspace: str, pages: str | None, confirmed: bool) -> list[dict]:
    """
    يقرأ ملفات الدفعة ويتحقق منها ويعيد قائمة عناصر جاهزة للفهرسة.
    يرفع HTTPException مباشرة عند أي مخالفة (ملف فارغ، نوع غير مدعوم، دفعة
    مصورة كبيرة بلا موافقة صريحة، تكرار...).
    """
    prepared = []
    for f in files:
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"الملف فارغ (0 بايت): {f.filename}")

        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext == ".doc" or f.content_type == "application/msword":
            raise HTTPException(
                status_code=400,
                detail="صيغة .doc القديمة غير مدعومة. يرجى حفظ الملف بصيغة .docx ثم رفعه."
            )

        kind = detect_kind(f.filename, f.content_type, data)
        if kind is None:
            raise HTTPException(
                status_code=400,
                detail=f"الملف غير مدعوم: {f.filename}. النظام يدعم PDF و Word (DOCX) والملفات النصية والصور."
            )

        # صمام الامتدادات المزيفة: المحتوى الفعلي يجب أن يطابق النوع المدّعى
        verify_content_matches(kind, data, f.filename)

        prepared.append({
            "name": f.filename,
            "bytes": data,
            "hash": hashlib.sha256(data).hexdigest(),
            "kind": kind,
            # المتصفح يرسل octet-stream للملفات بلا امتداد؛ نحن كشفنا النوع الحقيقي
            # من المحتوى فنخزّنه بدل الترويسة العامة (يصحّح الوسام ووحدة الترقيم معاً)
            "stored_type": (f.content_type
                            if f.content_type and f.content_type != "application/octet-stream"
                            else FALLBACK_CONTENT_TYPES[kind]),
            "force_ocr": force_ocr,
            "workspace": workspace,
            "skip": False,
            "overwrite_dup": False,
            "pages": None,
        })

    # قواعد الدفعات — Force OCR يعيد التقييد الصارم لأنه معالجة ثقيلة بطلب صريح
    image_count = sum(1 for p in prepared if p["kind"] == "image")
    if force_ocr:
        if len(prepared) > 1 and not (image_count == len(prepared) and image_count <= MAX_IMAGES_PER_BATCH):
            raise HTTPException(
                status_code=400,
                detail=f"مع تفعيل Force OCR: ملف واحد فقط، أو حتى {MAX_IMAGES_PER_BATCH} صور."
            )
    elif image_count > MAX_IMAGES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"الحد الأقصى {MAX_IMAGES_PER_BATCH} صور في الدفعة الواحدة (أُرسل {image_count})."
        )

    # الفحص المسبق لملفات PDF (سريع، بلا OCR): كم صفحة مصورة سنعالج فعلياً؟
    pdf_items = [p for p in prepared if p["kind"] == "pdf"]
    for p in pdf_items:
        try:
            p["precheck"] = pdf_precheck(p["bytes"])
        except Exception:
            raise HTTPException(status_code=400, detail=f"ملف PDF تالف أو غير قابل للقراءة: {p['name']}")

    # اختيار صفحات بعينها متاح لرفعة PDF واحدة فقط
    if pages:
        if len(prepared) != 1 or prepared[0]["kind"] != "pdf":
            raise HTTPException(status_code=400, detail="تحديد الصفحات متاح عند رفع ملف PDF واحد فقط.")
        try:
            prepared[0]["pages"] = parse_page_selection(pages, prepared[0]["precheck"]["total_pages"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # صمام أمان المعالج: فوق حد الصفحات المصورة نطلب موافقة صريحة مع تقدير زمني
    total_scanned = 0
    confirm_files = []
    for p in pdf_items:
        selected = set(p["pages"]) if p["pages"] else set(range(1, p["precheck"]["total_pages"] + 1))
        if force_ocr:
            scanned_count = len(selected)
        else:
            scanned_count = len(selected & set(p["precheck"]["scanned_pages"]))
        p["scanned_count"] = scanned_count
        total_scanned += scanned_count
        confirm_files.append({
            "name": p["name"],
            "total_pages": p["precheck"]["total_pages"],
            "scanned_pages": scanned_count,
        })

    if total_scanned > _CONFIRM_SCANNED_PAGES and not confirmed:
        lo, hi = _EST_SEC_PER_PAGE_GPU if ocr_engine.GPU_AVAILABLE else _EST_SEC_PER_PAGE_CPU
        raise HTTPException(status_code=413, detail={
            "reason": "confirm_ocr",
            "total_scanned_pages": total_scanned,
            "estimate_seconds_min": max(1, round(total_scanned * lo)),
            "estimate_seconds_max": max(1, round(total_scanned * hi)),
            "device": ocr_engine.OCR_DEVICE,
            "files": confirm_files,
            "page_selection_allowed": len(prepared) == 1 and prepared[0]["kind"] == "pdf",
        })

    # لا رفض بعد اليوم مهما بلغ عدد الصفحات: الحماية هي الموافقة الصريحة أعلاه
    # (مع التقدير الزمني واختيار الصفحات) والطابور الخلفي القابل للإلغاء.

    # فحص التكرار يسبق المعالجة حتى لا ينتظر المستخدم OCR بلا فائدة
    for p in prepared:
        duplicate = find_duplicate(p["name"], p["hash"])
        if not duplicate:
            continue
        if overwrite:
            p["overwrite_dup"] = True
        elif len(prepared) == 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "duplicate",
                    "match": duplicate["match"],          # "content" أو "filename"
                    "filename": duplicate["filename"],
                    "indexed_at": duplicate["created_at"],
                }
            )
        else:
            # داخل دفعة: نتخطى المكرر ونكمل الباقي، وتظهر حالته في تقرير المهمة
            p["skip"] = True

    return prepared


def process_upload_job(job_id: str, prepared: list, paged: bool) -> dict:
    """
    جسم المهمة الخلفية: يعالج كل ملفات الدفعة بالتسلسل ويحدّث التقدم بعد كل
    صفحة/صورة مكتملة فعلياً. يعمل داخل منفّذ المهام (خيط واحد) فلا يجمّد الخادم.
    """
    indexed, skipped, failed = [], [], []
    replaced = 0

    for idx, item in enumerate(prepared):
        if jobs.is_cancelled(job_id):
            jobs.set_item(job_id, idx, "cancelled")
            raise JobCancelled()

        name = item["name"]
        if item["skip"]:
            jobs.set_item(job_id, idx, "skipped", "مفهرس مسبقاً (مكرر)")
            skipped.append(name)
            if not paged:
                jobs.add_progress(job_id, done=idx + 1)
            continue

        jobs.set_item(job_id, idx, "processing")
        jobs.add_progress(job_id, current=name)

        try:
            # الاستبدال يزيل النسخ القديمة بالاسم وبالبصمة معاً قبل الفهرسة الجديدة
            if item["overwrite_dup"]:
                replaced += delete_documents(filename=name, file_hash=item["hash"])

            kind = item["kind"]
            page_map = None
            para_map = None

            def _page_progress(done, total, label):
                if paged:
                    jobs.add_progress(job_id, done=done, total=total, current=f"{name} — {label}")
                else:
                    jobs.add_progress(job_id, current=f"{name} — {label}")

            if kind == "pdf":
                pdf_kwargs = {
                    "force_ocr": item["force_ocr"],
                    "pages": item.get("pages"),
                    "progress": _page_progress,
                    "is_cancelled": lambda: jobs.is_cancelled(job_id),
                }
                if "max_ocr_pages" in item:
                    pdf_kwargs["max_ocr_pages"] = item["max_ocr_pages"]
                extracted_text, page_map, para_map = process_hybrid_pdf(
                    item["bytes"], ocr_engine.run_ocr_boxes, **pdf_kwargs,
                )
            elif kind == "docx":
                if item["force_ocr"]:
                    # Hybrid / OCR-targeted DOCX: attempt DOCX→PDF conversion
                    # for 100% accurate page/paragraph tracking (Gotenberg or a
                    # local LibreOffice, per PDF_ENGINE). If unavailable
                    # (dev/testing without either), fall back to the old
                    # inline-OCR path.
                    try:
                        from engine.pdf_conversion import convert_docx_to_pdf_sync
                        pdf_bytes = convert_docx_to_pdf_sync(item["bytes"])
                        extracted_text, page_map, para_map = process_hybrid_pdf(
                            pdf_bytes, ocr_engine.run_ocr_boxes,
                            force_ocr=True,
                            progress=_page_progress,
                            is_cancelled=lambda: jobs.is_cancelled(job_id),
                        )
                    except RuntimeError:
                        # Gotenberg unreachable — fall back to inline OCR via python-docx
                        extracted_text, page_map, para_map = process_docx(
                            item["bytes"],
                            force_ocr=True,
                            ocr_fn=ocr_engine.run_ocr_boxes,
                            is_cancelled=lambda: jobs.is_cancelled(job_id),
                        )
                else:
                    # Text-only DOCX: lightweight python-docx parsing (fast, no OCR)
                    extracted_text, page_map, para_map = process_docx(
                        item["bytes"],
                        force_ocr=False,
                        ocr_fn=None,
                        is_cancelled=lambda: jobs.is_cancelled(job_id),
                    )
            elif kind == "txt":
                extracted_text = process_txt(item["bytes"])
            else:
                # الصور تُمرَّر كبايتات مباشرة، والدمج الذكي يبني فقرات مترابطة
                extracted_text = join_ocr(ocr_engine.run_ocr_boxes(item["bytes"]))

            # نحفظ نسخة من الملف الأصلي ليُفتح لاحقاً من الواجهة؛ فشل الحفظ
            # لا يُسقط الفهرسة — يبقى المستند قابلاً للبحث وغير قابل للفتح فقط
            stored_name = None
            try:
                stored_name = storage.save(item["bytes"], item["hash"], name)
            except Exception as e:
                print(f"WARNING: could not store a copy of {name}: {e}")

            insert_document(name, item["stored_type"], extracted_text, item["hash"],
                            workspace=item["workspace"], page_map=page_map,
                            stored_name=stored_name, para_map=para_map)
            jobs.set_item(job_id, idx, "indexed")
            indexed.append(name)

        except JobCancelled:
            jobs.set_item(job_id, idx, "cancelled")
            raise
        except Exception as e:
            # منع تسريب أخطاء الواجهة الخلفية للمستخدم: التفاصيل للسجل، رسالة عامة للواجهة
            print(f"CRITICAL BACKEND ERROR [{name}]: {e}")
            detail = ("الملف تالف أو لا يحتوي على بيانات صورة صالحة رغم امتداده."
                      if item["kind"] == "image" else "الملف تالف أو غير مقروء.")
            jobs.set_item(job_id, idx, "failed", detail)
            failed.append(name)
        finally:
            if not paged:
                jobs.add_progress(job_id, done=idx + 1)

    return {"indexed": indexed, "skipped": skipped, "failed": failed, "replaced": replaced}
