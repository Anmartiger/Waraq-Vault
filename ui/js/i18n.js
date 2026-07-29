// Lightweight i18n: EN/AR dictionaries for static UI elements.
// Green Zones (dynamic user data) are NEVER translated — only Red Zone
// static labels, buttons, placeholders, empty states, and headers.
//
// Usage:
//   import { t, setLang, initI18n } from "./i18n.js";
//   t("key")           → translated string
//   t("key", arg1, ..) → translated string with %1, %2 placeholders replaced
//   setLang("ar")      → flips dir + lang, re-scans data-i18n tags
//   initI18n()         → called once on startup; restores saved lang

var LANG_KEY = "waraq-lang";

// ---------- dictionaries ---------------------------------------------------
var dict = {
  en: {
    // ── shell / top bar ──
    "tagline": "Your private document vault — search your Arabic & English documents",
    "nav-library": "Library",
    "nav-search": "Focus search",
    "nav-upload": "Upload files",
    "offline": "Offline — local only",
    "theme-dark": "Switch to light mode",
    "theme-light": "Switch to dark mode",

    // ── files panel ──
    "library-heading": "Library",
    "sec-workspaces": "Workspaces",
    "sec-filter": "Filter by type",
    "chip-all": "All",
    "chip-pdf": "PDF",
    "chip-docx": "DOCX",
    "chip-txt": "TXT",
    "chip-img": "IMG",
    "filter-placeholder": "Filter files\u2026",
    "sel-delete": "Delete",
    "sel-clear": "Clear",
    "sel-count": "%1 selected",
    "files-count": "%1 files",
    "selected-label": "selected",
    "files-label": "files",
    "doc-empty-none": "No documents yet \u2014 upload something.",
    "doc-empty-filter": "Nothing matches this filter.",

    // ── uploader ──
    "up-title": "Drop files here, or click to upload",
    "up-sub": "PDF \u00b7 DOCX \u00b7 TXT up to 50 files \u00b7 images up to 5 \u2014 read and indexed automatically",
    "ws-placeholder": "Workspace (Default)",
    "force-ocr-label": "Force\u00a0OCR",

    // ── search ──
    "search-placeholder": "Search\u2026",
    "search-button": "Search",
    "scope-searching-file": "Searching in: %1",
    "scope-searching-ws": "Searching in workspace: %1",

    // ── progress ──
    "progress-cancel": "Cancel",
    "progress-queued": "Queued \u2014 position %1 in line\u2026",
    "progress-remaining": "(%1 remaining)",
    "progress-uploading": "Uploading\u2026",
    "progress-cancelling": "Cancelling\u2026",

    // ── empty / status / search feedback ──
    "empty-start": "Start by searching, or upload documents.",
    "empty-min-chars": "Type at least 2 characters to search\u2026",
    "empty-no-results": "No results for \u201c%1\u201d",
    "status-ready": "Ready",
    "status-searching": "Searching for %1 \u2026",
    "status-no-matches": "No matches for %1",
    "status-search-failed": "Search failed: %1",

    // ── upload feedback ──
    "status-indexed-single": "\u2705 Indexed %1",
    "status-indexed-multi": "\u2705 Indexed %1 files",
    "status-skipped": "\u23ed %1 skipped (already indexed)",
    "status-failed-count": "\u274c %1 failed",
    "status-replaced-note": "(replaced the previous copy)",
    "status-done-search": " \u2014 you can search now.",
    "status-cancelled": "\uD83D\uDEAB Processing cancelled \u2014 nothing partial was indexed for the interrupted file.",
    "status-job-failed": "Processing failed: %1",
    "status-job-lost": "Lost track of the job: %1",
    "status-uploading": "Uploading %1 \u2026",
    "status-upload-failed": "Processing failed: %1",
    "status-force-ocr-limit": "Force OCR is heavy on purpose \u2014 one file at a time, or up to %1 images.",
    "status-too-many-files": "Too many files \u2014 up to %1 per upload.",
    "status-too-many-images": "Up to %1 images per upload (text formats can go up to %2).",
    "status-doc-rejected": "Old .doc format isn\u2019t supported \u2014 please save it as .docx first.",
    "status-unsupported": "Unsupported file \u2014 please use PDF, Word (DOCX), text files, or images.",
    "status-dup-cancelled": "Upload cancelled \u2014 the existing document was kept.",
    "status-bigscan-cancelled": "Upload cancelled \u2014 nothing was processed.",

    // ── deletion feedback ──
    "status-deleted-one": "\uD83D\uDDD1\uFE0F Deleted %1 from the index.",
    "status-deleted-many": "\uD83D\uDDD1\uFE0F Deleted %1 files from the index.",
    "status-delete-failed": "Delete failed: %1",
    "status-bulk-delete-failed": "Bulk delete failed: %1",
    "status-ws-deleted": "\uD83D\uDDD1\uFE0F Deleted workspace %1 (%2 files).",
    "status-ws-delete-failed": "Workspace delete failed: %1",

    // ── device / OCR ──
    "status-device-switching": "Switching OCR to %1 \u2014 reloading models\u2026",
    "status-device-switched": "OCR now running on %1.",
    "status-device-failed": "Device switch failed: %1",

    // ── details panel ──
    "details-heading": "Details",
    "det-type": "Type",
    "det-workspace": "Workspace",
    "det-chars": "Extracted text",
    "det-indexed": "Indexed",
    "det-id": "ID",
    "det-storage": "Storage",
    "det-open": "Open original \u2197",
    "det-open-disabled": "Uploaded before file-opening existed \u2014 re-upload to enable",
    "det-delete": "Delete file",
    "det-unscope": "Clear selection",
    "det-scope-hint": "Search is scoped to this file \u2014 clear to search everything.",
    "det-stats-documents": "documents",
    "det-stats-workspaces": "workspaces",
    "det-stats-images": "images",
    "det-stats-storage": "local \u00b7 waraq.db",
    "det-stats-hint": "Select a file in the library to see its details, or click one to search inside it.",

    // ── results ──
    "result-match": "match",
    "result-matches": "matches",
    "result-document": "document",
    "result-documents": "documents",
    "result-in": "in",
    "result-for": "for",
    "result-show-more": "Show %1 more",
    "result-show-less": "Show less",
    "result-first-n": "Showing the first %1 of %2 matches.",
    "result-open": "Open \u2197",
    "result-open-title": "Open the original file",

    // ── modal defaults ──
    "modal-confirm": "Confirm",
    "modal-cancel": "Cancel",
    "modal-overwrite-title": "This document is already indexed",
    "modal-overwrite-content-match": "The same file content is already indexed as %1%2. Overwrite it, or cancel and keep what you have?",
    "modal-overwrite-content-name": "A document named %1 was already indexed%2. Overwrite it with this file, or cancel?",
    "modal-overwrite-ok": "Overwrite",
    "modal-delete-title": "Delete from the archive?",
    "modal-delete-content": "%1 will be removed from the archive and the search index.%2The original files on your disk are not touched.",
    "modal-delete-ws-content": "All %1 files inside it will be removed in one shot.",
    "modal-delete-ok": "Delete",
    "modal-bigscan-title": "Large scan \u2014 how much should we read?",
    "modal-bigscan-needs-ocr": "This upload needs OCR on %1 scanned page%2.",
    "modal-bigscan-estimate": "Estimated %1 on %2. Processing runs in the background \u2014 the app stays usable and you can cancel at any point.",
    "modal-bigscan-ok": "Start processing",
    "modal-bigscan-all": "All pages",
    "modal-bigscan-range": "A page range",
    "modal-bigscan-list": "Specific pages",
    "modal-bigscan-spec-label": "Pages to process (1\u2013%1)",
    "modal-bigscan-spec-label-nomax": "Pages to process",
    "modal-bigscan-est-pages": "%1 page%2 \u2014 estimated %3",
    "modal-bigscan-enter-pages": "Enter the pages you want.",
    "modal-bigscan-invalid-range": "Not a valid selection \u2014 use numbers between 1 and %1.",
    "modal-bigscan-invalid": "Not a valid selection.",
    "modal-bigscan-file-line": "%1 \u2014 %2 of %3 pages need OCR",

    // ── time estimates ──
    "time-sec": "%1 sec",
    "time-min": "~%1 min",
    "time-hm": "~%1h %2m",
    "time-h": "~%1h",
    "time-range-min": "~%1\u2013%2 min",

    // ── backend error translations (ar → current lang) ──
    "err-spoofed-ext": "The file extension does not match its actual content — rename the file with its correct extension.",
    "err-empty-file": "The file is empty (0 bytes).",
    "err-unsupported": "Unsupported file type — the system supports PDF, Word (DOCX), text files, and images.",
    "err-old-doc": "Old .doc format is not supported. Please save the file as .docx and upload it again.",
    "err-max-files": "Too many files — the maximum is 50 per upload.",
    "err-max-images": "Too many images — the maximum is 5 per upload.",
    "err-force-ocr-limit": "With Force OCR enabled: only one file, or up to 5 images.",
    "err-page-selection": "Page selection is only available when uploading a single PDF file.",
    "err-pdf-corrupt": "Corrupt or unreadable PDF file.",
    "err-corrupt-generic": "The file is corrupt or unreadable.",
    "err-job-unknown": "Unknown job — the server may have been restarted.",
    "err-doc-missing": "Document not found.",
    "err-ws-missing": "No workspace with that name exists.",
    "err-no-stored-copy": "No stored copy of this file — it was uploaded before the file-opening feature was added. Re-upload to enable opening.",
  },

  ar: {
    // ── shell / top bar ──
    "tagline": "خزانة أوراقك الخاصة — ابحث في مستنداتك العربية والإنجليزية",
    "nav-library": "المكتبة",
    "nav-search": "البحث",
    "nav-upload": "رفع ملفات",
    "offline": "يعمل محلياً — بدون إنترنت",
    "theme-dark": "التبديل إلى الوضع الفاتح",
    "theme-light": "التبديل إلى الوضع الداكن",

    // ── files panel ──
    "library-heading": "المكتبة",
    "sec-workspaces": "مساحات العمل",
    "sec-filter": "تصفية حسب النوع",
    "chip-all": "الكل",
    "chip-pdf": "PDF",
    "chip-docx": "DOCX",
    "chip-txt": "TXT",
    "chip-img": "صور",
    "filter-placeholder": "تصفية الملفات\u2026",
    "sel-delete": "حذف",
    "sel-clear": "إلغاء",
    "sel-count": "%1 محدد",
    "files-count": "%1 ملفات",
    "selected-label": "محدد",
    "files-label": "ملفات",
    "doc-empty-none": "لا توجد مستندات بعد — ارفع شيئاً.",
    "doc-empty-filter": "لا شيء يطابق هذا الفلتر.",

    // ── uploader ──
    "up-title": "أسقط الملفات هنا، أو انقر للرفع",
    "up-sub": "PDF · DOCX · TXT حتى 50 ملفاً · الصور حتى 5 — تُقرأ وتُفهرس تلقائياً",
    "ws-placeholder": "مساحة العمل (الافتراضية)",
    "force-ocr-label": "OCR\u00a0إجباري",

    // ── search ──
    "search-placeholder": "ابحث\u2026",
    "search-button": "بحث",
    "scope-searching-file": "البحث في: %1",
    "scope-searching-ws": "البحث في مساحة العمل: %1",

    // ── progress ──
    "progress-cancel": "إلغاء",
    "progress-queued": "في الطابور — المركز %1 في الصف\u2026",
    "progress-remaining": "(%1 متبق)",
    "progress-uploading": "جاري الرفع\u2026",
    "progress-cancelling": "جاري الإلغاء\u2026",

    // ── empty / status / search feedback ──
    "empty-start": "ابدأ بالبحث، أو ارفع مستندات.",
    "empty-min-chars": "اكتب حرفين على الأقل للبحث\u2026",
    "empty-no-results": "لا توجد نتائج لـ \"%1\"",
    "status-ready": "جاهز",
    "status-searching": "جاري البحث عن %1 \u2026",
    "status-no-matches": "لا توجد تطابقات لـ %1",
    "status-search-failed": "فشل البحث: %1",

    // ── upload feedback ──
    "status-indexed-single": "\u2705 تمت فهرسة %1",
    "status-indexed-multi": "\u2705 تمت فهرسة %1 ملفات",
    "status-skipped": "\u23ed %1 تم تخطيها (مفهرسة مسبقاً)",
    "status-failed-count": "\u274c %1 فشلت",
    "status-replaced-note": "(تم استبدال النسخة السابقة)",
    "status-done-search": " — يمكنك البحث الآن.",
    "status-cancelled": "\uD83D\uDEAB تم إلغاء المعالجة — لم تتم فهرسة أي شيء جزئي للملف المتوقف.",
    "status-job-failed": "فشلت المعالجة: %1",
    "status-job-lost": "فقد تتبع المهمة: %1",
    "status-uploading": "جاري رفع %1 \u2026",
    "status-upload-failed": "فشلت المعالجة: %1",
    "status-force-ocr-limit": "خاصية OCR الإجباري ثقيلة — ملف واحد في كل مرة، أو حتى %1 صور.",
    "status-too-many-files": "ملفات كثيرة جداً — حتى %1 في كل رفعة.",
    "status-too-many-images": "حتى %1 صور في كل رفعة (صيغ النصوص تصل إلى %2).",
    "status-doc-rejected": "صيغة .doc القديمة غير مدعومة — يرجى حفظ الملف بصيغة .docx أولاً.",
    "status-unsupported": "ملف غير مدعوم — يرجى استخدام PDF أو Word (DOCX) أو ملفات نصية أو صور.",
    "status-dup-cancelled": "تم إلغاء الرفع — تم الإبقاء على المستند الموجود.",
    "status-bigscan-cancelled": "تم إلغاء الرفع — لم تتم معالجة أي شيء.",

    // ── deletion feedback ──
    "status-deleted-one": "\uD83D\uDDD1\uFE0F تم حذف %1 من الفهرس.",
    "status-deleted-many": "\uD83D\uDDD1\uFE0F تم حذف %1 ملفات من الفهرس.",
    "status-delete-failed": "فشل الحذف: %1",
    "status-bulk-delete-failed": "فشل الحذف الجماعي: %1",
    "status-ws-deleted": "\uD83D\uDDD1\uFE0F تم حذف مساحة العمل %1 (%2 ملفات).",
    "status-ws-delete-failed": "فشل حذف مساحة العمل: %1",

    // ── device / OCR ──
    "status-device-switching": "جاري تبديل OCR إلى %1 — إعادة تحميل النماذج\u2026",
    "status-device-switched": "OCR يعمل الآن على %1.",
    "status-device-failed": "فشل تبديل الجهاز: %1",

    // ── details panel ──
    "details-heading": "التفاصيل",
    "det-type": "النوع",
    "det-workspace": "مساحة العمل",
    "det-chars": "النص المستخرج",
    "det-indexed": "تاريخ الفهرسة",
    "det-id": "المعرّف",
    "det-storage": "التخزين",
    "det-open": "فتح الأصل \u2197",
    "det-open-disabled": "تم الرفع قبل وجود ميزة فتح الملف — أعد الرفع لتفعيلها",
    "det-delete": "حذف الملف",
    "det-unscope": "إلغاء التحديد",
    "det-scope-hint": "البحث محصور في هذا الملف — امسح للبحث في الكل.",
    "det-stats-documents": "مستندات",
    "det-stats-workspaces": "مساحات عمل",
    "det-stats-images": "صور",
    "det-stats-storage": "محلي · waraq.db",
    "det-stats-hint": "اختر ملفاً من المكتبة لعرض تفاصيله، أو انقر عليه للبحث بداخله.",

    // ── results ──
    "result-match": "تطابق",
    "result-matches": "تطابقات",
    "result-document": "مستند",
    "result-documents": "مستندات",
    "result-in": "في",
    "result-for": "عن",
    "result-show-more": "عرض %1 إضافي",
    "result-show-less": "عرض أقل",
    "result-first-n": "عرض أول %1 من %2 تطابق.",
    "result-open": "فتح \u2197",
    "result-open-title": "فتح الملف الأصلي",

    // ── modal defaults ──
    "modal-confirm": "تأكيد",
    "modal-cancel": "إلغاء",
    "modal-overwrite-title": "هذا المستند مفهرس مسبقاً",
    "modal-overwrite-content-match": "نفس محتوى الملف مفهرس بالفعل باسم %1%2. هل تريد استبداله، أم الإلغاء والإبقاء على الموجود؟",
    "modal-overwrite-content-name": "مستند باسم %1 مفهرس مسبقاً%2. هل تريد استبداله بهذا الملف، أم الإلغاء؟",
    "modal-overwrite-ok": "استبدال",
    "modal-delete-title": "حذف من الأرشيف؟",
    "modal-delete-content": "%1 سيتم حذفه من الأرشيف وفهرس البحث.%2الملفات الأصلية على قرصك لن تُمس.",
    "modal-delete-ws-content": "كل الملفات (%1) بداخلها ستُحذف دفعة واحدة.",
    "modal-delete-ok": "حذف",
    "modal-bigscan-title": "مسح ضوئي كبير — كم تريد أن نقرأ؟",
    "modal-bigscan-needs-ocr": "هذه الرفعة تحتاج OCR لـ %1 صفحة ممسوحة%2.",
    "modal-bigscan-estimate": "الوقت المقدر %1 على %2. المعالجة تعمل في الخلفية — التطبيق يبقى قابلاً للاستخدام ويمكنك الإلغاء في أي وقت.",
    "modal-bigscan-ok": "ابدأ المعالجة",
    "modal-bigscan-all": "كل الصفحات",
    "modal-bigscan-range": "نطاق صفحات",
    "modal-bigscan-list": "صفحات محددة",
    "modal-bigscan-spec-label": "الصفحات المطلوب معالجتها (1\u2013%1)",
    "modal-bigscan-spec-label-nomax": "الصفحات المطلوب معالجتها",
    "modal-bigscan-est-pages": "%1 صفحة%2 — الوقت المقدر %3",
    "modal-bigscan-enter-pages": "أدخل الصفحات التي تريدها.",
    "modal-bigscan-invalid-range": "تحديد غير صالح — استخدم أرقاماً بين 1 و %1.",
    "modal-bigscan-invalid": "تحديد غير صالح.",
    "modal-bigscan-file-line": "%1 — %2 من %3 صفحات تحتاج OCR",

    // ── time estimates ──
    "time-sec": "%1 ثانية",
    "time-min": "~%1 دقيقة",
    "time-hm": "~%1س %2د",
    "time-h": "~%1س",
    "time-range-min": "~%1\u2013%2 دقيقة",

    // ── backend error translations (ar → current lang) ──
    "err-spoofed-ext": "الامتداد لا يطابق المحتوى الفعلي للملف — أعد تسمية الملف بامتداده الصحيح أو حوّله للصيغة المدعومة.",
    "err-empty-file": "الملف فارغ (0 بايت).",
    "err-unsupported": "نوع الملف غير مدعوم — النظام يدعم PDF و Word (DOCX) والملفات النصية والصور.",
    "err-old-doc": "صيغة .doc القديمة غير مدعومة. يرجى حفظ الملف بصيغة .docx ثم رفعه.",
    "err-max-files": "عدد الملفات كبير جداً — الحد الأقصى هو 50 ملفاً في الرفعة الواحدة.",
    "err-max-images": "عدد الصور كبير جداً — الحد الأقصى هو 5 صور في الرفعة الواحدة.",
    "err-force-ocr-limit": "مع تفعيل Force OCR: ملف واحد فقط، أو حتى 5 صور.",
    "err-page-selection": "تحديد الصفحات متاح عند رفع ملف PDF واحد فقط.",
    "err-pdf-corrupt": "ملف PDF تالف أو غير قابل للقراءة.",
    "err-corrupt-generic": "الملف تالف أو غير مقروء.",
    "err-job-unknown": "مهمة غير معروفة — ربما أُعيد تشغيل الخادم.",
    "err-doc-missing": "المستند غير موجود — ربما حُذف مسبقاً.",
    "err-ws-missing": "لا توجد مجموعة بهذا الاسم.",
    "err-no-stored-copy": "لا توجد نسخة محفوظة من هذا الملف — رُفع قبل تفعيل ميزة الفتح. أعد رفعه ليصبح قابلاً للفتح.",
  }
};

// ---------- current language ------------------------------------------------
var currentLang = "ar";

export function getLang() { return currentLang; }

var ARABIC = /[؀-ۿ]/;

// Map backend Arabic error strings to their i18n key for the current language.
// When a backend error is in Arabic, we detect the pattern and return the
// translation for the active UI language. Unknown messages pass through as-is.
function findErrorKey(arMsg) {
  if (!arMsg) return null;
  if (/الامتداد لا يطابق/.test(arMsg))       return "err-spoofed-ext";
  if (/الملف فارغ.*0.*بايت/.test(arMsg))      return "err-empty-file";
  if (/الملف غير مدعوم/.test(arMsg))          return "err-unsupported";
  if (/صيغة \.doc القديمة/.test(arMsg))       return "err-old-doc";
  if (/الحد الأقصى.*ملفاً/.test(arMsg))       return "err-max-files";
  if (/الحد الأقصى.*صور/.test(arMsg))         return "err-max-images";
  if (/Force OCR/.test(arMsg))                return "err-force-ocr-limit";
  if (/تحديد الصفحات/.test(arMsg))            return "err-page-selection";
  if (/ملف PDF تالف/.test(arMsg))              return "err-pdf-corrupt";
  if (/الملف تالف/.test(arMsg))               return "err-corrupt-generic";
  if (/مهمة غير معروفة/.test(arMsg))           return "err-job-unknown";
  if (/المستند غير موجود/.test(arMsg))         return "err-doc-missing";
  if (/لا توجد مجموعة/.test(arMsg))            return "err-ws-missing";
  if (/لا توجد نسخة محفوظة/.test(arMsg))       return "err-no-stored-copy";
  return null;
}

export function i18nError(raw) {
  var msg = raw && typeof raw === "object" && raw.detail ? raw.detail : String(raw || "");
  // If the message is already in the target language (no Arabic), just return it.
  var hasArabic = ARABIC.test(msg);
  var key = hasArabic ? findErrorKey(msg) : null;
  if (key) {
    var translated = t(key);
    // Some error messages include dynamic values we can extract.
    // For now, the full translated string covers the common cases.
    return translated;
  }
  // If it's Arabic but we don't have a mapping, return it as-is (raw)
  // to avoid the Frankenstein prefix issue.
  return msg;
}

// Lookup a key. Falls back to the key itself when missing.
export function t(key) {
  var d = dict[currentLang] || dict.en;
  var s = d[key];
  if (s === undefined) {
    // If the target language is missing a string, try English as a soft fallback.
    if (currentLang !== "en" && dict.en && dict.en[key] !== undefined) {
      s = dict.en[key];
    } else {
      return key;
    }
  }
  // Replace positional placeholders %1, %2, …
  for (var i = 1; i < arguments.length; i++) {
    s = s.replace("%" + i, arguments[i] == null ? "" : arguments[i]);
  }
  return s;
}

// ---------- DOM update via data-i18n ----------------------------------------
// Scans the whole document for elements with a data-i18n attribute and updates
// their text content (or placeholder / title / value if qualified).
// Exported so dynamic panels can call it after re-rendering post language change.
export function refreshI18n() { scanDOM(); }

function scanDOM() {
  var elements = document.querySelectorAll("[data-i18n]");
  for (var i = 0; i < elements.length; i++) {
    var el = elements[i];
    var raw = el.getAttribute("data-i18n");
    if (!raw) continue;
    // format: "key" or "key|attr" (e.g. "search-placeholder|placeholder")
    var parts = raw.split("|");
    var key = parts[0];
    var attr = parts[1] || "text";
    var val = (dict[currentLang] && dict[currentLang][key]) || (dict.en && dict.en[key]) || key;
    if (attr === "text") {
      el.textContent = val;
    } else if (attr === "html") {
      el.innerHTML = val;
    } else {
      // placeholder, title, aria-label, value, …
      el.setAttribute(attr, val);
    }
  }
}

// ---------- public API ------------------------------------------------------
export function setLang(lang) {
  if (lang !== "ar" && lang !== "en") lang = "ar";
  if (lang === currentLang) return;
  currentLang = lang;
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";

  scanDOM();
  // Let other modules react (theme.js updates the toggle tooltip, for example).
  document.documentElement.dispatchEvent(new CustomEvent("waraq-lang-changed", {
    detail: { lang: lang }
  }));

  try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
}

export function initI18n() {
  var saved = "ar";
  try { saved = localStorage.getItem(LANG_KEY) || "ar"; } catch (e) {}
  if (saved !== "ar" && saved !== "en") saved = "ar";
  currentLang = saved;
  document.documentElement.lang = saved;
  document.documentElement.dir = saved === "ar" ? "rtl" : "ltr";
  scanDOM();
}