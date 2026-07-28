// Themed confirm dialog — overwrites, deletions, and the big-scan OCR confirmation.

import { escapeHtml } from "./utils.js";

var overlay   = document.getElementById("modal");
var titleEl   = document.getElementById("modal-title");
var textEl    = document.getElementById("modal-text");
var choiceRow = document.getElementById("modal-choices");
var inputRow  = document.getElementById("modal-input-row");
var inputLbl  = document.getElementById("modal-input-label");
var inputEl   = document.getElementById("modal-input");
var estimateEl= document.getElementById("modal-estimate");
var okBtn     = document.getElementById("modal-ok");
var cancelBtn = document.getElementById("modal-cancel");

var resolver = null;   // resolve() of the promise currently awaiting an answer
var withInput = false;
var choiceCfg = null;

function currentMode() {
  var picked = choiceRow.querySelector("input[type=radio]:checked");
  return picked ? picked.value : null;
}

// Counts pages in a "1-10, 15" spec so the estimate reacts as the user types.
function countPages(spec, maxPage) {
  var seen = {}, n = 0, bad = false;
  String(spec || "").split(",").forEach(function (part) {
    part = part.trim();
    if (!part) return;
    var m = part.match(/^(\d+)\s*-\s*(\d+)$/), single = part.match(/^(\d+)$/);
    var from, to;
    if (m) { from = +m[1]; to = +m[2]; if (from > to) { var t = from; from = to; to = t; } }
    else if (single) { from = to = +single[1]; }
    else { bad = true; return; }
    for (var p = from; p <= to; p++) {
      if (p < 1 || (maxPage && p > maxPage)) { bad = true; return; }
      if (!seen[p]) { seen[p] = 1; n++; }
    }
  });
  return { count: n, invalid: bad };
}

function refreshEstimate() {
  if (!choiceCfg) return;
  var mode = currentMode();
  var needsSpec = mode === "range" || mode === "list";
  inputRow.hidden = !needsSpec;
  if (!needsSpec) {
    estimateEl.textContent = "";
    okBtn.disabled = false;
    return;
  }
  var parsed = countPages(inputEl.value, choiceCfg.maxPage);
  if (!inputEl.value.trim()) {
    estimateEl.textContent = "Enter the pages you want.";
    estimateEl.className = "modal-estimate warn";
    okBtn.disabled = true;
  } else if (parsed.invalid || !parsed.count) {
    estimateEl.textContent = choiceCfg.maxPage
      ? "Not a valid selection — use numbers between 1 and " + choiceCfg.maxPage + "."
      : "Not a valid selection.";
    estimateEl.className = "modal-estimate warn";
    okBtn.disabled = true;
  } else {
    estimateEl.textContent = parsed.count + " page" + (parsed.count === 1 ? "" : "s") +
                             " — estimated " + choiceCfg.estimator(parsed.count * choiceCfg.perPageSeconds);
    estimateEl.className = "modal-estimate";
    okBtn.disabled = false;
  }
}

function close(accepted) {
  if (!resolver) return;
  var done = resolver;
  resolver = null;
  overlay.hidden = true;
  document.removeEventListener("keydown", onKey);
  var value = "";
  if (choiceCfg) {
    value = (currentMode() === "all") ? "" : inputEl.value.trim();
  } else if (withInput) {
    value = inputEl.value.trim();
  }
  done((withInput || choiceCfg) ? { ok: accepted, value: value } : accepted);
}

function onKey(e) {
  if (e.key === "Escape") close(false);
}

okBtn.addEventListener("click", function () { close(true); });
cancelBtn.addEventListener("click", function () { close(false); });
// Clicking the dim backdrop (but not the dialog itself) cancels.
overlay.addEventListener("click", function (e) { if (e.target === overlay) close(false); });

// Generic confirm. Resolves a boolean — or {ok, value} when input/choices are used.
export function confirmDialog(opts) {
  titleEl.textContent = opts.title || "Are you sure?";
  textEl.innerHTML = opts.html || "";
  okBtn.textContent = opts.okText || "Confirm";
  cancelBtn.textContent = opts.cancelText || "Cancel";
  okBtn.disabled = false;

  choiceCfg = opts.choices || null;
  withInput = !!opts.inputLabel;
  estimateEl.textContent = "";
  inputEl.value = "";

  if (choiceCfg) {
    choiceRow.hidden = false;
    choiceRow.innerHTML = choiceCfg.options.map(function (o, i) {
      return '<label class="modal-choice">' +
               '<input type="radio" name="' + choiceCfg.name + '" value="' + o.value + '"' +
                 (i === 0 ? " checked" : "") + ">" +
               '<span class="ch-label">' + escapeHtml(o.label) + "</span>" +
               (o.hint ? '<span class="ch-hint">' + escapeHtml(o.hint) + "</span>" : "") +
             "</label>";
    }).join("");
    inputLbl.textContent = choiceCfg.specLabel || "Pages";
    inputEl.placeholder = "1-10, 15";
    inputRow.hidden = true;                       // shown when a spec mode is picked
    choiceRow.querySelectorAll("input[type=radio]").forEach(function (radio) {
      radio.addEventListener("change", function () {
        var opt = choiceCfg.options.filter(function (o) { return o.value === radio.value; })[0];
        if (opt && opt.placeholder) inputEl.placeholder = opt.placeholder;
        refreshEstimate();
        if (!inputRow.hidden) inputEl.focus();
      });
    });
    inputEl.oninput = refreshEstimate;
    refreshEstimate();
  } else {
    choiceRow.hidden = true;
    choiceRow.innerHTML = "";
    inputEl.oninput = null;
    inputRow.hidden = !withInput;
    if (withInput) {
      inputLbl.textContent = opts.inputLabel;
      inputEl.placeholder = opts.inputPlaceholder || "";
    }
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

function humanDuration(seconds) {
  seconds = Math.max(1, Math.round(seconds || 0));
  if (seconds < 90) return seconds + " sec";
  var mins = Math.round(seconds / 60);
  if (mins < 90) return "~" + mins + " min";
  var hours = Math.floor(mins / 60), rest = mins % 60;
  return "~" + hours + "h" + (rest ? " " + rest + "m" : "");
}

// The CPU safety valve: there is no page limit any more, so a big scan is
// allowed — but only after the user sees what it costs and can narrow it down.
export function confirmBigScan(detail) {
  detail = detail || {};
  var total = detail.total_scanned_pages || 0;
  var perPage = total ? (detail.estimate_seconds || 0) / total : 0;
  var files = (detail.files || []).map(function (f) {
    return "<li><b>" + escapeHtml(f.name) + "</b> — " + f.scanned_pages +
           " of " + f.total_pages + " pages need OCR</li>";
  }).join("");
  var maxPage = (detail.files || []).reduce(function (m, f) { return Math.max(m, f.total_pages || 0); }, 0);

  var html =
    "This upload needs OCR on <b>" + total + " scanned page" + (total === 1 ? "" : "s") + "</b>." +
    "<ul>" + files + "</ul>" +
    "Estimated <b>" + humanDuration(detail.estimate_seconds) + "</b> on " +
    escapeHtml(detail.device || "this machine") +
    ". Processing runs in the background — the app stays usable and you can cancel at any point.";

  var opts = {
    title: "Large scan — how much should we read?",
    html: html,
    okText: "Start processing",
    cancelText: "Cancel"
  };

  if (detail.page_selection_allowed) {
    // Choosing fewer pages is the fastest way to cut the wait, so make it a
    // first-class choice rather than an afterthought in a text box.
    opts.choices = {
      name: "pagemode",
      options: [
        { value: "all", label: "All pages", hint: humanDuration(detail.estimate_seconds) },
        { value: "range", label: "A page range", hint: "e.g. 1-10", spec: true, placeholder: "1-10" },
        { value: "list", label: "Specific pages", hint: "e.g. 3, 7, 12", spec: true, placeholder: "3, 7, 12" }
      ],
      specLabel: maxPage ? "Pages to process (1–" + maxPage + ")" : "Pages to process",
      perPageSeconds: perPage,
      maxPage: maxPage,
      estimator: humanDuration
    };
  }

  return confirmDialog(opts).then(function (res) {
    if (typeof res === "boolean") return { ok: res, pages: "" };
    return { ok: res.ok, pages: res.value || "" };
  });
}
