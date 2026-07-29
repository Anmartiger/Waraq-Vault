// Upload: POST /upload (multipart, field "file") — click or drag-and-drop.
// Text formats travel in batches of up to 50 (fast extraction path); images are
// capped at 5 and Force OCR re-tightens the rules, because those are the heavy
// paths. Big scanned PDFs come back as 413/confirm_ocr and open a consent
// dialog with a time estimate and an optional page selection.

import { escapeHtml } from "./utils.js";
import {
  drop, fileInput, input, setStatus, forceOcr, workspaceInput, upOpts,
  progressWrap, progressBar, progressLabel, progressItems, progressCancel
} from "./dom.js";
import { runSearch } from "./search.js";
import { confirmOverwrite, confirmBigScan } from "./modal.js";
import { refreshLibrary } from "./files.js";
import { t, i18nError } from "./i18n.js";

var MAX_FILES = 50;
var MAX_IMAGES = 5;
var POLL_MS = 400;
var activeJob = null;

// Mirrors the server-side checks in main.py — instant feedback, server still validates.
function isSupported(file) {
  var name = (file.name || "").toLowerCase();
  var type = file.type || "";
  if (name.indexOf(".") === -1) return true;   // no extension: the server sniffs content
  if (/\.(pdf|docx|txt|png|jpe?g|bmp|tiff?|webp)$/.test(name)) return true;
  return type.indexOf("image/") === 0 ||
         type.indexOf("text/") === 0 ||
         type === "application/pdf" ||
         type.indexOf("wordprocessingml") > -1;
}

function isImage(file) {
  return (file.type || "").indexOf("image/") === 0 ||
         /\.(png|jpe?g|bmp|tiff?|webp)$/i.test(file.name || "");
}

function detailText(data, status) {
  var d = data && data.detail;
  if (typeof d === "string") return d;
  return "Upload failed (" + status + ")";
}

var ICONS = {
  queued: "⏳", processing: "🔄", indexed: "✅",
  skipped: "⏭️", failed: "❌", cancelled: "🚫"
};

function renderJob(job) {
  progressWrap.hidden = false;

  if (job.percent == null) {
    progressBar.classList.add("indet");
    progressBar.style.width = "100%";
  } else {
    progressBar.classList.remove("indet");
    progressBar.style.width = job.percent + "%";
  }

  var label;
  if (job.state === "queued") {
    label = t("progress-queued", job.queue_position || 0);
  } else {
    label = (job.percent != null ? job.percent + "% — " : "") + (job.current || "processing…");
    var remaining = (job.total_units || 0) - (job.done_units || 0);
    if (job.items && job.items.length > 1 && remaining > 0) {
      label += " " + t("progress-remaining", remaining);
    }
  }
  progressLabel.textContent = label;

  // Per-file status list, only for batches.
  if (job.items && job.items.length > 1) {
    progressItems.innerHTML = job.items.map(function (it) {
      return '<div class="pitem">' + (ICONS[it.status] || "•") +
             ' <span class="pname" dir="auto">' + escapeHtml(it.name) + "</span>" +
             (it.detail ? ' <span class="pdetail">— ' + escapeHtml(it.detail) + "</span>" : "") +
             "</div>";
    }).join("");
  } else {
    progressItems.innerHTML = "";
  }
}

function resetUploadUi() {
  progressWrap.hidden = true;
  progressBar.classList.remove("indet");
  drop.classList.remove("busy");
  fileInput.value = "";
  activeJob = null;
}

function finishJob(job) {
  var r = job.result || {};
  resetUploadUi();

  if (job.state === "done") {
    var parts = [];
    if ((r.indexed || []).length) {
      parts.push(r.indexed.length === 1
        ? t("status-indexed-single", "<b>" + escapeHtml(r.indexed[0]) + "</b>")
        : t("status-indexed-multi", r.indexed.length));
    }
    if ((r.skipped || []).length) parts.push(t("status-skipped", r.skipped.length));
    if ((r.failed || []).length) parts.push(t("status-failed-count", r.failed.length));
    var note = r.replaced ? " " + t("status-replaced-note") : "";
    setStatus((parts.join(" · ") || "Done") + note + t("status-done-search"));
  } else if (job.state === "cancelled") {
    setStatus(t("status-cancelled"));
  } else {
    setStatus(t("status-job-failed", escapeHtml(job.error || "unknown error")));
  }

  refreshLibrary();
  if (input.value.trim().length >= 2) runSearch(input.value);
}

function pollJob(jobId) {
  activeJob = jobId;
  fetch("/jobs/" + jobId)
    .then(function (res) {
      if (!res.ok) throw new Error("job lost — was the server restarted?");
      return res.json();
    })
    .then(function (job) {
      renderJob(job);
      if (job.state === "done" || job.state === "error" || job.state === "cancelled") {
        finishJob(job);
      } else {
        setTimeout(function () { pollJob(jobId); }, POLL_MS);
      }
    })
    .catch(function (err) {
      resetUploadUi();
      setStatus(t("status-job-lost", escapeHtml(err.message)));
    });
}

function upload(fileList, opts) {
  opts = opts || {};
  var files = Array.prototype.slice.call(fileList || []);
  if (!files.length) return;

  var images = files.filter(isImage).length;
  var forced = forceOcr && forceOcr.checked;

  // Client-side mirrors of the server rules.
  if (forced && files.length > 1 && !(images === files.length && images <= MAX_IMAGES)) {
    setStatus(t("status-force-ocr-limit", MAX_IMAGES));
    return;
  }
  if (files.length > MAX_FILES) {
    setStatus(t("status-too-many-files", MAX_FILES));
    return;
  }
  if (images > MAX_IMAGES) {
    setStatus(t("status-too-many-images", MAX_IMAGES, MAX_FILES));
    return;
  }
  for (var i = 0; i < files.length; i++) {
    if (/\.doc$/i.test(files[i].name || "")) {
      setStatus(t("status-doc-rejected"));
      return;
    }
    if (!isSupported(files[i])) {
      setStatus(t("status-unsupported"));
      return;
    }
  }

  var what = files.length === 1 ? "<b>" + escapeHtml(files[0].name) + "</b>" : files.length + " " + t("files-count", files.length);
  setStatus(t("status-uploading", what));
  drop.classList.add("busy");
  progressWrap.hidden = false;
  progressBar.classList.remove("indet");
  progressBar.style.width = "0%";
  progressLabel.textContent = t("progress-uploading");
  progressItems.innerHTML = "";

  var fd = new FormData();
  files.forEach(function (f) { fd.append("file", f); });
  if (opts.overwrite) fd.append("overwrite", "true");
  if (forced) fd.append("force_ocr", "true");
  if (opts.confirmed) fd.append("confirmed", "true");
  if (opts.pages) fd.append("pages", opts.pages);
  var ws = (workspaceInput.value || "").trim();
  if (ws) fd.append("workspace", ws);

  fetch("/upload", { method: "POST", body: fd })
    .then(function (res) {
      return res.json().then(function (data) {
        if (res.status === 409) {          // duplicate — stopped before any OCR
          var clash = new Error(t("status-dup-cancelled"));
          clash.duplicate = (data && data.detail) || {};
          throw clash;
        }
        if (res.status === 413) {          // big scan — needs explicit consent
          var big = new Error(t("status-bigscan-cancelled"));
          big.confirm = (data && data.detail) || {};
          throw big;
        }
        if (!res.ok) throw new Error(i18nError(data) || detailText(data, res.status));
        return data;
      });
    })
    .then(function (data) {
      pollJob(data.job_id);
    })
    .catch(function (err) {
      resetUploadUi();
      if (err.duplicate) {
        confirmOverwrite(err.duplicate).then(function (yes) {
          if (yes) upload(files, { overwrite: true, confirmed: opts.confirmed, pages: opts.pages });
          else setStatus(t("status-dup-cancelled"));
        });
        return;
      }
      if (err.confirm) {
        confirmBigScan(err.confirm).then(function (res) {
          if (res.ok) upload(files, { overwrite: opts.overwrite, confirmed: true, pages: res.pages || "" });
          else setStatus(t("status-bigscan-cancelled"));
        });
        return;
      }
      setStatus(i18nError(err.message) || t("status-upload-failed", escapeHtml(err.message)));
    });
}

export function openPicker() { fileInput.click(); }

export function initUpload() {
  drop.addEventListener("click", function (e) {
    if (upOpts.contains(e.target)) return;   // typing a workspace ≠ opening the picker
    fileInput.click();
  });
  drop.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && !upOpts.contains(e.target)) {
      e.preventDefault(); fileInput.click();
    }
  });
  fileInput.addEventListener("change", function () { upload(fileInput.files); });

  ["dragenter", "dragover"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("drag"); });
  });
  ["dragleave", "dragend", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("drag"); });
  });
  drop.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) upload(e.dataTransfer.files);
  });

  // Cancel the in-flight job; the worker stops at the next page/image boundary.
  progressCancel.addEventListener("click", function () {
    if (!activeJob) return;
    progressLabel.textContent = t("progress-cancelling");
    fetch("/jobs/" + activeJob + "/cancel", { method: "POST" }).catch(function () {});
  });
}
