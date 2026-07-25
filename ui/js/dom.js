// Cached element references and the two small screen-writing helpers.
// Modules are deferred, so the document is already parsed when this runs.

import { escapeHtml } from "./utils.js";

export var statusEl  = document.getElementById("status");
export var resultsEl = document.getElementById("results");
export var form      = document.querySelector("form.search");
export var input     = form.querySelector('input[name="q"]');
export var drop      = document.getElementById("drop");
export var fileInput = document.getElementById("file");

export function setStatus(html) { statusEl.innerHTML = html; }

export function showEmpty(msg) {
  resultsEl.innerHTML =
    '<div class="empty"><div class="big">🔍</div><div>' + escapeHtml(msg) + "</div></div>";
}
