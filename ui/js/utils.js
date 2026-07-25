// Pure helpers shared by the rest of the UI — no DOM, no network.

// Arabic script range, used to tag a result as AR or EN.
export var ARABIC = /[؀-ۿ]/;

export function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

// The API wraps matched words in <b>…</b>. Escape everything first (so any
// markup inside the document text is neutralised), then re-enable only those
// highlight markers as themed <mark>.
export function renderHighlighted(s) {
  return escapeHtml(s)
    .replace(/&lt;b&gt;/g, "<mark>")
    .replace(/&lt;\/b&gt;/g, "</mark>");
}

export function typeLabel(ct) {
  if (!ct) return "FILE";
  if (ct.indexOf("pdf") > -1) return "PDF";
  if (ct.indexOf("image/") === 0) return "IMG";
  if (ct.indexOf("word") > -1) return "DOCX";   // …wordprocessingml.document
  if (ct.indexOf("text/") === 0) return "TXT";
  return ct.split("/").pop().toUpperCase();
}
