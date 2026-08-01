"""
حفظ نسخة محلية من الملف الأصلي حتى يستطيع المستخدم فتحه من الواجهة.

النسخ تعيش في مجلد storage/ داخل المشروع (مستثنى من git) وتُسمّى ببصمة الملف،
فالملفات المتطابقة تتشارك نسخة واحدة مهما تكرر رفعها. لا شيء يغادر الجهاز.
"""

import os

from engine.paths import data_dir

# Its own subdirectory, deliberately — prune() below sweeps this entire
# directory and deletes anything not a known document copy. data_dir() also
# holds waraq.db (engine/database.py) and, in the desktop build, backend.log
# (src-tauri/src/lib.rs) — sharing that directory meant prune() had already
# deleted a live waraq.db as an "orphan" file the first time anyone deleted a
# document. Never point this at a directory that holds anything else.
STORAGE_DIR = data_dir() / "originals"

# امتدادات نسمح بها في اسم النسخة المحفوظة (الاسم الحقيقي يبقى في قاعدة البيانات)
_MAX_EXT = 12

def save(file_bytes: bytes, file_hash: str, filename: str) -> str:
    """حفظ نسخة وإعادة اسمها المخزَّن. الملف الموجود مسبقاً لا يُعاد كتابته."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(filename or "")[1].lower()
    if len(ext) > _MAX_EXT or not ext.isprintable():
        ext = ""
    stored_name = f"{file_hash}{ext}"
    path = STORAGE_DIR / stored_name
    if not path.exists():
        # الكتابة إلى ملف مؤقت ثم إعادة التسمية: لا نترك نسخة نصف مكتوبة أبداً
        tmp_path = path.with_suffix(path.suffix + ".part")
        tmp_path.write_bytes(file_bytes)
        tmp_path.replace(path)
    return stored_name

def path_for(stored_name: str):
    """المسار الفعلي للنسخة، أو None إذا لم تعد موجودة."""
    if not stored_name:
        return None
    # basename يمنع أي محاولة خروج من المجلد عبر ../ في اسم مُتلاعَب به
    safe = os.path.basename(str(stored_name))
    if not safe:
        return None
    path = STORAGE_DIR / safe
    return path if path.is_file() else None

def prune(referenced: set) -> int:
    """
    حذف النسخ التي لم يعد يشير إليها أي مستند في قاعدة البيانات.
    مصالحة كاملة بدل تتبّع كل عملية حذف على حدة — تُصلح نفسها ذاتياً.
    """
    if not STORAGE_DIR.exists():
        return 0
    removed = 0
    for path in STORAGE_DIR.iterdir():
        if path.is_file() and path.name not in referenced:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass   # ملف مفتوح في برنامج آخر — سيُنظَّف في المرة القادمة
    return removed
