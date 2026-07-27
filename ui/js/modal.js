// Themed confirm dialog — overwrites, deletions, and the big-scan OCR confirmation.

import { escapeHtml } from "./utils.js";

var overlay   = document.getElementById("modal");
var titleEl   = document.getElementById("modal-title");
var textEl    = document.getElementById("modal-text");
var inputRow  = document.getElementById("modal-input-row");
var inputLbl  = document.getElementById("modal-input-label");
var inputEl   = document.getElementById("modal-input");
var okBtn     = document.getElementById("modal-ok");
var cancelBtn = document.getElementById("modal-cancel");

var resolver = null;   // resolve() of the promise currently awaiting an answer
var withInput = false;

function close(accepted) {
  if (!resolver) return;
  var done = resolver;
  resolver = null;
  overlay.hidden = true;
  document.removeEventListener("keydown", onKey);
  done(withInput ? { ok: accepted, value: inputEl.value.trim() } : accepted);
}

function onKey(e) {
  if (e.key === "Escape") close(false);
}

okBtn.addEventListener("click", function () { close(true); });
cancelBtn.addEventListener("click", function () { close(false); });
// Clicking the dim backdrop (but not the dialog itself) cancels.
overlay.addEventListener("click", function (e) { if (e.target === overlay) close(false); });

// Generic confirm. Resolves a boolean — or {ok, value} when an input is requested.
export function confirmDialog(opts) {
  titleEl.textContent = opts.title || "Are you sure?";
  textEl.innerHTML = opts.html || "";
  okBtn.textContent = opts.okText || "Confirm";
  cancelBtn.textContent = opts.cancelText || "Cancel";

  withInput = !!opts.inputLabel;
  inputRow.hidden = !withInput;
  if (withInput) {
    inputLbl.textContent = opts.inputLabel;
    inputEl.placeholder = opts.inputPlaceholder || "";
    inputEl.value = "";
  }

  overlay.hidden = false;
  document.addEventListener("keydown", onKey);
  cancelBtn.focus();   // safer default: Enter keeps things as they are

  return new Promise(function (resolve) { resolver = resolve; });
}

// Shown when an upload would duplicate an indexed document.
export function confirmOverwrite(info) {
  info = info || {};
  var name = escapeHtml(info.filename || "this document");
  var when = info.indexed_at ? " on " + escapeHtml(info.indexed_at) : "";

  var html = (info.match === "content")
    ? "The same file content is already indexed as <b>" + name + "</b>" + when +
      ".<br>Overwrite it, or cancel and keep what you have?"
    : "A document named <b>" + name + "</b> was already indexed" + when +
      ".<br>Overwrite it with this file, or cancel?";

  return confirmDialog({
    title: "This document is already indexed",
    html: html,
    okText: "Overwrite"
  });
}

// Shown before removing one document, several documents, or a whole workspace.
export function confirmDelete(label, extraHtml) {
  return confirmDialog({
    title: "Delete from the archive?",
    html: "<b>" + escapeHtml(label) + "</b> will be removed from the archive and the search index." +
          (extraHtml || "") +
          "<br>The original files on your disk are not touched.",
    okText: "Delete"
  });
}

// The CPU safety valve: a big scanned PDF needs explicit consent, with a rough
// time estimate and (for a single PDF) an optional page selection.
export function confirmBigScan(detail) {
  detail = detail || {};
  var mins = Math.max(1, Math.round((detail.estimate_seconds || 0) / 60));
  var files = (detail.files || []).map(function (f) {
    return "<li><b>" + escapeHtml(f.name) + "</b> — " + f.scanned_pages +
           " of " + f.total_pages + " pages need OCR</li>";
  }).join("");

  var html =
    "This upload needs OCR on <b>" + (detail.total_scanned_pages || "?") + " scanned pages</b>." +
    "<ul>" + files + "</ul>" +
    "Rough estimate: <b>~" + mins + " min</b> on " + escapeHtml(detail.device || "this machine") +
    ". The app stays usable and you can cancel anytime.";

  var opts = {
    title: "Large scan — proceed?",
    html: html,
    okText: "Process it",
    cancelText: "Cancel"
  };
  if (detail.page_selection_allowed) {
    opts.inputLabel = "Only these pages (optional) — e.g. 1-10, 15, 22-30";
    opts.inputPlaceholder = "all pages";
  }
  return confirmDialog(opts).then(function (res) {
    if (typeof res === "boolean") return { ok: res, pages: "" };
    return { ok: res.ok, pages: res.value };
  });
}
