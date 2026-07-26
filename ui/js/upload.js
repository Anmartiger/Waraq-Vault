// Upload: POST /upload (multipart, field "file", 1..5 files) — click or drag-and-drop.
// The server replies 202 with a job id; we poll /jobs/{id} and render real
// per-page / per-image progress, with a Cancel button for in-flight work.

import { escapeHtml } from "./utils.js";
import {
  drop, fileInput, input, setStatus, forceOcr,
  progressWrap, progressBar, progressLabel, progressItems, progressCancel
} from "./dom.js";
import { runSearch } from "./search.js";
import { confirmOverwrite } from "./modal.js";
import { refreshLibrary } from "./library.js";

var MAX_FILES = 5;
var POLL_MS = 400;
var activeJob = null;

// Mirrors the server-side check in main.py: extension first, then content type,
// because browsers report DOCX and text files inconsistently. Extensionless
// files are allowed through — the server sniffs their real content.
function isSupported(file) {
  var name = (file.name || "").toLowerCase();
  var type = file.type || "";
  if (name.indexOf(".") === -1) return true;   // no extension: let the server sniff
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
    label = "Queued — position " + (job.queue_position || 0) + " in line…";
  } else {
    label = (job.percent != null ? job.percent + "% — " : "") + (job.current || "processing…");
    var remaining = (job.total_units || 0) - (job.done_units || 0);
    if (job.items && job.items.length > 1 && remaining > 0) {
      label += " (" + remaining + " remaining)";
    }
  }
  progressLabel.textContent = label;

  // Per-image status list, only for batches.
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
      parts.push("✅ Indexed " + (r.indexed.length === 1 ? "<b>" + escapeHtml(r.indexed[0]) + "</b>" : r.indexed.length + " files"));
    }
    if ((r.skipped || []).length) parts.push("⏭️ " + r.skipped.length + " skipped (already indexed)");
    if ((r.failed || []).length) parts.push("❌ " + r.failed.length + " failed");
    var note = r.replaced ? " (replaced the previous copy)" : "";
    setStatus((parts.join(" · ") || "Done") + note + " — you can search now.");
  } else if (job.state === "cancelled") {
    setStatus("🚫 Processing cancelled — nothing partial was indexed for the interrupted file.");
  } else {
    setStatus("Processing failed: " + escapeHtml(job.error || "unknown error"));
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
      setStatus("Lost track of the job: " + escapeHtml(err.message));
    });
}

function upload(fileList, overwrite) {
  var files = Array.prototype.slice.call(fileList || []);
  if (!files.length) return;

  // Client-side mirrors of the server rules — instant feedback, server still validates.
  if (files.length > MAX_FILES) {
    setStatus("Too many files — up to " + MAX_FILES + " images per upload.");
    return;
  }
  if (files.length > 1 && !files.every(isImage)) {
    setStatus("Multi-file upload is for images only (up to " + MAX_FILES + "). Upload PDF, DOCX or TXT one at a time.");
    return;
  }
  for (var i = 0; i < files.length; i++) {
    if (/\.doc$/i.test(files[i].name || "")) {
      setStatus("Old .doc format isn’t supported — please save it as .docx first.");
      return;
    }
    if (!isSupported(files[i])) {
      setStatus("Unsupported file — please use a PDF, Word (DOCX), text file, or an image.");
      return;
    }
  }

  var what = files.length === 1 ? "<b>" + escapeHtml(files[0].name) + "</b>" : files.length + " images";
  setStatus("Uploading " + what + " …");
  drop.classList.add("busy");
  progressWrap.hidden = false;
  progressBar.classList.remove("indet");
  progressBar.style.width = "0%";
  progressLabel.textContent = "Uploading…";
  progressItems.innerHTML = "";

  var fd = new FormData();
  files.forEach(function (f) { fd.append("file", f); });
  if (overwrite) fd.append("overwrite", "true");
  if (forceOcr && forceOcr.checked) fd.append("force_ocr", "true");

  fetch("/upload", { method: "POST", body: fd })
    .then(function (res) {
      return res.json().then(function (data) {
        // 409 = already indexed; the server stopped before doing any OCR work.
        if (res.status === 409) {
          var clash = new Error("duplicate");
          clash.duplicate = (data && data.detail) || {};
          throw clash;
        }
        if (!res.ok) throw new Error(detailText(data, res.status));
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
          if (yes) {
            upload(files, true);
          } else {
            setStatus("Upload cancelled — the existing document was kept.");
          }
        });
        return;
      }
      setStatus("Processing failed: " + escapeHtml(err.message));
    });
}

export function initUpload() {
  drop.addEventListener("click", function () { fileInput.click(); });
  drop.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
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
    progressLabel.textContent = "Cancelling…";
    fetch("/jobs/" + activeJob + "/cancel", { method: "POST" }).catch(function () {});
  });
}
