// Themed confirm dialog — duplicate overwrites and file deletion share it.

import { escapeHtml } from "./utils.js";

var overlay   = document.getElementById("modal");
var titleEl   = document.getElementById("modal-title");
var textEl    = document.getElementById("modal-text");
var okBtn     = document.getElementById("modal-ok");
var cancelBtn = document.getElementById("modal-cancel");

var resolver = null;   // resolve() of the promise currently awaiting an answer

function close(answer) {
  if (!resolver) return;
  var done = resolver;
  resolver = null;
  overlay.hidden = true;
  document.removeEventListener("keydown", onKey);
  done(answer);
}

function onKey(e) {
  if (e.key === "Escape") close(false);
}

okBtn.addEventListener("click", function () { close(true); });
cancelBtn.addEventListener("click", function () { close(false); });
// Clicking the dim backdrop (but not the dialog itself) cancels.
overlay.addEventListener("click", function (e) { if (e.target === overlay) close(false); });

// Generic confirm. Resolves true when the destructive action is chosen.
export function confirmDialog(opts) {
  titleEl.textContent = opts.title || "Are you sure?";
  textEl.innerHTML = opts.html || "";
  okBtn.textContent = opts.okText || "Confirm";
  cancelBtn.textContent = opts.cancelText || "Cancel";

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

// Shown before removing a document from the index.
export function confirmDelete(name) {
  return confirmDialog({
    title: "Delete this document?",
    html: "<b>" + escapeHtml(name) + "</b> will be removed from the archive and the search index." +
          "<br>The original file on your disk is not touched.",
    okText: "Delete"
  });
}
