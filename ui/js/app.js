// WaraqVault UI entry point — wires the shell (rail, panels, theme), the search
// box, the uploader, the results list and the file manager to the local API.

import {
  showEmpty, input, filesPanel, detailsPanel, detailsClose, detailsToggle,
  navFiles, railLibrary, railSearch, railUpload, deviceChip
} from "./dom.js";
import { initTheme } from "./theme.js";
import { initSearch } from "./search.js";
import { initUpload, openPicker } from "./upload.js";
import { initShowMore } from "./results.js";
import { initFiles } from "./files.js";

function initShell() {
  var appEl = document.querySelector(".app");
  // Each panel lives in one of two regimes: a real grid column on wide screens
  // (collapse it by zeroing its column) or an overlay drawer on narrow ones
  // (slide it with .open). The same button has to drive whichever applies.
  var FILES_DRAWER = "(max-width:960px)";
  var DETAILS_DRAWER = "(max-width:1360px)";

  function toggleFiles() {
    if (window.matchMedia(FILES_DRAWER).matches) filesPanel.classList.toggle("open");
    else appEl.classList.toggle("files-off");
  }
  function toggleDetails() {
    if (window.matchMedia(DETAILS_DRAWER).matches) detailsPanel.classList.toggle("open");
    else appEl.classList.toggle("details-off");
  }
  function closeDetails() {
    detailsPanel.classList.remove("open");   // narrow: slide it away
    appEl.classList.add("details-off");      // wide: collapse the column
  }

  navFiles.addEventListener("click", toggleFiles);
  railLibrary.addEventListener("click", toggleFiles);
  railSearch.addEventListener("click", function () { input.focus(); });
  railUpload.addEventListener("click", openPicker);
  detailsToggle.addEventListener("click", toggleDetails);
  detailsClose.addEventListener("click", closeDetails);

  // The status chip in the header tells the truth about the OCR device.
  fetch("/status")
    .then(function (r) { return r.json(); })
    .then(function (s) {
      var line = (s && s.ingestion_pipeline) || "";
      var device = line.indexOf("OCR device:") > -1 ? line.split("OCR device:")[1].trim() : "";
      if (device) {
        deviceChip.textContent = (s.gpu ? "⚡ " : "🖥 ") + device;
        deviceChip.hidden = false;
      }
    })
    .catch(function () { /* header chip is decorative — search works regardless */ });
}

initTheme();
initShell();
initSearch();
initUpload();
initShowMore();
initFiles();

showEmpty("Start by searching, or upload documents.");
