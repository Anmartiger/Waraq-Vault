// Cached element references and the two small screen-writing helpers.
// Modules are deferred, so the document is already parsed when this runs.

import { escapeHtml } from "./utils.js";

export var statusEl  = document.getElementById("status");
export var resultsEl = document.getElementById("results");
export var form      = document.querySelector("form.search");
export var input     = form.querySelector('input[name="q"]');
export var drop      = document.getElementById("drop");
export var fileInput = document.getElementById("file");

// upload options + progress feedback
export var forceOcr       = document.getElementById("force-ocr");
export var workspaceInput = document.getElementById("workspace");
export var upOpts         = document.getElementById("up-opts");
export var progressWrap   = document.getElementById("progress");
export var progressBar    = document.getElementById("progress-bar");
export var progressLabel  = document.getElementById("progress-label");
export var progressItems  = document.getElementById("progress-items");
export var progressCancel = document.getElementById("progress-cancel");

// file manager panel
export var filesPanel = document.getElementById("files-panel");
export var filesCount = document.getElementById("files-count");
export var wsList     = document.getElementById("ws-list");
export var typeChips  = document.getElementById("type-chips");
export var fileFilter = document.getElementById("file-filter");
export var docList    = document.getElementById("doc-list");
export var selBar     = document.getElementById("sel-bar");
export var selCount   = document.getElementById("sel-count");
export var selDelete  = document.getElementById("sel-delete");
export var selClear   = document.getElementById("sel-clear");

// scope indicator above the results
export var scopeBar   = document.getElementById("scope-bar");
export var scopeLabel = document.getElementById("scope-label");
export var scopeClear = document.getElementById("scope-clear");

// details panel + shell controls
export var detailsPanel  = document.getElementById("details-panel");
export var detBody       = document.getElementById("det-body");
export var detailsClose  = document.getElementById("details-close");
export var detailsToggle = document.getElementById("details-toggle");
export var themeToggle   = document.getElementById("theme-toggle");
export var deviceChip    = document.getElementById("device-chip");
export var navFiles      = document.getElementById("nav-files");
export var railLibrary   = document.getElementById("rail-library");
export var railSearch    = document.getElementById("rail-search");
export var railUpload    = document.getElementById("rail-upload");

export function setStatus(html) { statusEl.innerHTML = html; }

export function showEmpty(msg) {
  resultsEl.innerHTML =
    '<div class="empty"><div class="big">🔍</div><div>' + escapeHtml(msg) + "</div></div>";
}
