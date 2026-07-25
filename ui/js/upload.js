// Upload: POST /upload (multipart, field "file") — click or drag-and-drop.

import { escapeHtml } from "./utils.js";
import { drop, fileInput, input, setStatus } from "./dom.js";
import { runSearch } from "./search.js";

// Mirrors the server-side check in main.py: extension first, then content type,
// because browsers report DOCX and text files inconsistently.
function isSupported(file) {
  var name = (file.name || "").toLowerCase();
  var type = file.type || "";
  if (/\.(pdf|docx|txt|png|jpe?g|bmp|tiff?|webp)$/.test(name)) return true;
  return type.indexOf("image/") === 0 ||
         type.indexOf("text/") === 0 ||
         type === "application/pdf" ||
         type.indexOf("wordprocessingml") > -1;
}

function upload(file) {
  if (!file) return;
  if (/\.doc$/i.test(file.name || "")) {
    setStatus("Old .doc format isn’t supported — please save it as .docx first.");
    return;
  }
  if (!isSupported(file)) {
    setStatus("Unsupported file — please use a PDF, Word (DOCX), text file, or an image.");
    return;
  }

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
