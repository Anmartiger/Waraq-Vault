// Cached element references and the two small screen-writing helpers.
// Modules are deferred, so the document is already parsed when this runs.

import { escapeHtml } from "./utils.js";

export var statusEl  = document.getElementById("status");
export var resultsEl = document.getElementById("results");
export var form      = document.querySelector("form.search");
export var input     = form.querySelector('input[name="q"]');
export var drop      = document.getElementById("drop");
export var fileInput = document.getElementById("file");

// search scope + deletion (library row)
export var scopeSel  = document.getElementById("scope");
export var deleteBtn = document.getElementById("delete-doc");

// upload options + progress feedback
export var forceOcr       = document.getElementById("force-ocr");
export var progressWrap   = document.getElementById("progress");
export var progressBar    = document.getElementById("progress-bar");
export var progressLabel  = document.getElementById("progress-label");
export var progressItems  = document.getElementById("progress-items");
export var progressCancel = document.getElementById("progress-cancel");

export function setStatus(html) { statusEl.innerHTML = html; }

export function showEmpty(msg) {
  resultsEl.innerHTML =
    '<div class="empty"><div class="big">🔍</div><div>' + escapeHtml(msg) + "</div></div>";
}
