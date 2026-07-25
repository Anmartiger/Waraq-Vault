// Themed confirm dialog, shown when an upload would duplicate an indexed document.

import { escapeHtml } from "./utils.js";

var overlay   = document.getElementById("modal");
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

// Resolves true to overwrite, false to keep the existing document.
export function confirmOverwrite(info) {
  info = info || {};
  var name = escapeHtml(info.filename || "this document");
  var when = info.indexed_at ? " on " + escapeHtml(info.indexed_at) : "";

  textEl.innerHTML = (info.match === "content")
    ? "The same file content is already indexed as <b>" + name + "</b>" + when +
      ".<br>Overwrite it, or cancel and keep what you have?"
    : "A document named <b>" + name + "</b> was already indexed" + when +
      ".<br>Overwrite it with this file, or cancel?";

  overlay.hidden = false;
  document.addEventListener("keydown", onKey);
  cancelBtn.focus();   // safer default: Enter keeps the existing document

  return new Promise(function (resolve) { resolver = resolve; });
}
