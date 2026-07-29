// Rendering of the results list: one card per document, every matching line
// numbered and highlighted, revealed a batch at a time.

import { ARABIC, escapeHtml, renderHighlighted, typeLabel } from "./utils.js";
import { resultsEl } from "./dom.js";
import { t } from "./i18n.js";

var INITIAL = 8;   // lines shown before the first "Show more"
var BATCH   = 50;  // additional lines revealed per "Show more" click

// Badge for the document's real language, detected by the backend.
// Falls back to the old client-side heuristic for older payloads.
function langBadge(r, sample) {
  var lang = r.lang || (ARABIC.test(sample) ? "ar" : "en");
  if (lang === "mixed") return '<span class="badge mixed">AR·EN</span>';
  if (lang === "ar")    return '<span class="badge ar">AR</span>';
  return '<span class="badge">EN</span>';
}

function cardHtml(r) {
  var matches = r.matches || [];
  var total = (r.match_count != null) ? r.match_count : matches.length;
  var sample = (matches[0] ? matches[0].text : "") + " " + (r.filename || "") + " " + (r.snippet || "");

  // Numbering semantics differ per format: real lines (PDF/TXT), page-only
  // (DOCX), and OCR blocks (images → no misleading position at all).
  var unit = r.unit || "line";

  var body;
  if (matches.length) {
    var rows = matches.map(function (m, idx) {
      // Format-specific metadata: PDF/DOCX show p.X, para Y (per-page counter);
      // TXT shows L{Z}; images show no position at all.
      var locParts = [], titleParts = [];
      if (unit === "line") {
        // TXT: line_number only, no paragraph tracking
        locParts.push('<span class="ln">L' + m.line + '</span>');
        titleParts.push("Line " + m.line);
        titleParts.push("File: " + r.filename);
      } else if (unit === "page") {
        // PDF/DOCX: page number always present; paragraph number if available
        var page = m.page;
        var para = m.para;
        if (page != null) {
          locParts.push('<span class="pg">p.' + page + '</span>');
          titleParts.push("Page " + page);
        }
        if (para != null) {
          locParts.push('<span class="paralabel">para ' + para + '</span>');
          titleParts.push("Paragraph " + para);
        }
      }
      // Images (unit=block): no position markers at all — locParts stays empty
      var loc = locParts.join("");
      var title = titleParts.join("; ") || r.filename;
      return '<div class="line' + (idx >= INITIAL ? " extra" : "") + '" dir="auto">' +
               (loc ? '<span class="loc" title="' + title + '">' + loc + '</span>' : "") +
               '<span class="linetext">' + renderHighlighted(m.text) + '</span>' +
             '</div>';
    }).join("");
    var hidden = matches.length - INITIAL;
      var btn = hidden > 0
        ? '<button class="showmore" type="button" data-mode="more">' + t("result-show-more", Math.min(BATCH, hidden)) + '</button>'
        : "";
      // Only when the true total exceeds the safety cap we were able to send.
      var capnote = (total > matches.length)
        ? '<div class="capnote">' + t("result-first-n", matches.length, total) + '</div>'
        : "";
    body = '<div class="lines">' + rows + "</div>" + btn + capnote;
  } else {
    // Fallback: no per-line matches returned — show the single API snippet.
    body = '<div class="snippet">' + renderHighlighted(r.snippet) + "</div>";
  }

  return (
    '<div class="card">' +
      '<div class="meta">' +
        '<span class="fname">' + escapeHtml(r.filename) + "</span>" +
        langBadge(r, sample) +
        '<span class="badge">' + escapeHtml(typeLabel(r.content_type)) + "</span>" +
        (r.workspace && r.workspace !== "Default"
          ? '<span class="wsbadge">' + escapeHtml(r.workspace) + "</span>" : "") +
        '<span class="hits">' + total + " " + (total === 1 ? t("result-match") : t("result-matches")) + "</span>" +
        (r.openable && r.id != null
          ? '<button type="button" class="openlink" data-open="' + r.id + '" ' +
            'title="' + t("result-open-title") + '">' + t("result-open") + '</button>' : "") +
      "</div>" +
      body +
    "</div>"
  );
}

// Paints the summary line plus one card per document.
// Returns the tallies so the caller can mirror them in the status line.
export function renderResults(list, q) {
  var totalMatches = list.reduce(function (a, r) {
    return a + ((r.match_count != null) ? r.match_count : (r.matches ? r.matches.length : 1));
  }, 0);
  var docWord = list.length === 1 ? t("result-document") : t("result-documents");
  var hitWord = totalMatches === 1 ? t("result-match") : t("result-matches");

  resultsEl.innerHTML =
    '<div class="summary">' + totalMatches + " " + hitWord +
      ' <span class="muted">' + t("result-in") + " " + list.length + " " + docWord +
      " " + t("result-for") + " \u201c" + escapeHtml(q) + "\u201d</span></div>" +
    list.map(cardHtml).join("");

  return { totalMatches: totalMatches, docs: list.length, docWord: docWord, hitWord: hitWord };
}

// Show more / Show less — reveal matching lines BATCH at a time.
export function initShowMore() {
  resultsEl.addEventListener("click", function (e) {
    // Opening the original from a result card.
    var open = e.target.closest && e.target.closest("[data-open]");
    if (open) {
      window.open("/documents/" + open.getAttribute("data-open") + "/open", "_blank", "noopener");
      return;
    }
    var btn = e.target.closest && e.target.closest(".showmore");
    if (!btn) return;
    var lines = btn.previousElementSibling;
    var i;

    if (btn.getAttribute("data-mode") === "less") {          // collapse back to the first INITIAL
      var shownEls = lines.querySelectorAll(".line.extra.shown");
      for (i = 0; i < shownEls.length; i++) shownEls[i].classList.remove("shown");
      lines.classList.remove("expanded");
      btn.setAttribute("data-mode", "more");
      btn.textContent = t("result-show-more", Math.min(BATCH, shownEls.length));
      return;
    }

    var hiddenEls = lines.querySelectorAll(".line.extra:not(.shown)");
    var reveal = Math.min(BATCH, hiddenEls.length);
    for (i = 0; i < reveal; i++) hiddenEls[i].classList.add("shown");
    lines.classList.add("expanded");

    var left = hiddenEls.length - reveal;
    if (left > 0) {
      btn.textContent = t("result-show-more", Math.min(BATCH, left));
    } else {
      btn.setAttribute("data-mode", "less");
      btn.textContent = t("result-show-less");
    }
  });
}
