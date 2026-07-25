// Upload: POST /upload (multipart, field "file") — click or drag-and-drop.

import { escapeHtml } from "./utils.js";
import { drop, fileInput, input, setStatus } from "./dom.js";
import { runSearch } from "./search.js";

function upload(file) {
  if (!file) return;
  var ok = (file.type.indexOf("image/") === 0) || file.type === "application/pdf";
  if (!ok) { setStatus("Unsupported file — please use a PDF or an image."); return; }

  setStatus("Uploading &amp; processing <b>" + escapeHtml(file.name) + "</b> …");
  drop.classList.add("busy");

  var fd = new FormData();
  fd.append("file", file);

  fetch("/upload", { method: "POST", body: fd })
    .then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error((data && data.detail) || ("Upload failed (" + res.status + ")"));
        return data;
      });
    })
    .then(function (data) {
      setStatus("✅ Indexed <b>" + escapeHtml(data.filename) + "</b> — you can search it now.");
      if (input.value.trim().length >= 2) runSearch(input.value);
    })
    .catch(function (err) {
      setStatus("Processing failed: " + escapeHtml(err.message));
    })
    .then(function () {
      drop.classList.remove("busy");
      fileInput.value = "";
    });
}

export function initUpload() {
  drop.addEventListener("click", function () { fileInput.click(); });
  drop.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", function () { upload(fileInput.files[0]); });

  ["dragenter", "dragover"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("drag"); });
  });
  ["dragleave", "dragend", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("drag"); });
  });
  drop.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) upload(e.dataTransfer.files[0]);
  });
}
