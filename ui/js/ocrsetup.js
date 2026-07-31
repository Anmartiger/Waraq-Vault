// First-run OCR setup banner: polls /ocr/progress and shows real download
// percentage (or an indeterminate bar while loading into memory) until the
// engine is ready. Stays hidden entirely once the models are already cached
// from a previous run, since /ocr/progress then reports "ready" immediately.

import { t } from "./i18n.js";

var POLL_MS = 900;

var wrap, bar, label, timer;

function render(info) {
  if (!info || !wrap) return;

  if (info.phase === "ready") {
    wrap.hidden = true;
    stop();
    return;
  }

  wrap.hidden = false;

  if (info.phase === "error") {
    bar.classList.remove("indet");
    bar.style.width = "100%";
    label.textContent = t("ocr-setup-error", info.message || "");
    stop();
    return;
  }

  if (info.phase === "downloading" && typeof info.percent === "number") {
    bar.classList.remove("indet");
    bar.style.width = info.percent + "%";
    label.textContent = t("ocr-setup-downloading", info.percent.toFixed(0));
  } else if (info.phase === "downloading") {
    bar.classList.add("indet");
    bar.style.width = "100%";
    label.textContent = t("ocr-setup-downloading-indet");
  } else {
    bar.classList.add("indet");
    bar.style.width = "100%";
    label.textContent = t("ocr-setup-loading");
  }
}

function poll() {
  fetch("/ocr/progress")
    .then(function (r) { return r.json(); })
    .then(render)
    .catch(function () { /* transient — next poll retries */ });
}

function stop() {
  if (timer) { clearInterval(timer); timer = null; }
}

export function initOcrSetup() {
  wrap = document.getElementById("ocr-setup");
  bar = document.getElementById("ocr-setup-bar");
  label = document.getElementById("ocr-setup-label");
  if (!wrap || !bar || !label) return;

  poll();
  timer = setInterval(poll, POLL_MS);
}
