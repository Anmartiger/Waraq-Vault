// OCR hardware: shows what is actually running, lets the user force GPU or CPU,
// and — crucially — explains *why* a detected NVIDIA card is not being used.

import { escapeHtml } from "./utils.js";
import { deviceChip, deviceSelect, setStatus } from "./dom.js";
import { t } from "./i18n.js";

var KEY = "waraq-device";

function render(info) {
  if (!info) return;

  deviceSelect.value = info.mode || "auto";

  // A GPU that torch cannot use stays selectable-but-disabled, with the reason.
  var gpuOption = deviceSelect.querySelector('option[value="gpu"]');
  if (gpuOption) {
    gpuOption.disabled = !info.gpu_usable;
    gpuOption.textContent = info.gpu_usable ? "⚡ GPU"
                          : (info.gpu_present ? "⚡ GPU (unavailable)" : "⚡ GPU (none)");
  }

  var onGpu = info.active === "gpu";
  deviceChip.hidden = false;
  deviceChip.textContent = (onGpu ? "⚡ " : "🖥 ") + (info.device || "");
  deviceChip.className = "chip";
  deviceChip.title = info.reason || (onGpu ? "OCR is running on the GPU" : "OCR is running on the CPU");

  // Hardware is present but unusable — say so loudly, with the exact fix.
  if (!info.gpu_usable && info.gpu_present) {
    deviceChip.className = "chip warn";
    deviceChip.textContent = "⚠ GPU idle — " + (info.gpu_name || "NVIDIA");
    deviceChip.title = (info.reason || "") + (info.install_hint ? "\n\n" + info.install_hint : "");
  }
}

function apply(mode) {
  setStatus(t("status-device-switching", "<b>" + escapeHtml(mode) + "</b>"));
  return fetch("/device", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: mode })
  })
    .then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error((data && data.detail) || ("Could not switch (" + res.status + ")"));
        return data;
      });
    })
    .then(function (info) {
      render(info);
      try { localStorage.setItem(KEY, info.mode); } catch (e) {}
      setStatus(t("status-device-switched", "<b>" + escapeHtml(info.device) + "</b>"));
    })
    .catch(function (err) {
      setStatus(t("status-device-failed", escapeHtml(err.message)));
      return fetch("/device").then(function (r) { return r.json(); }).then(render);
    });
}

export function initDevice() {
  fetch("/device")
    .then(function (r) { return r.json(); })
    .then(function (info) {
      render(info);
      // Re-apply the user's saved preference across restarts, but never fight
      // the server: a saved "gpu" on a machine that cannot do GPU is ignored.
      var saved = null;
      try { saved = localStorage.getItem(KEY); } catch (e) {}
      if (saved && saved !== info.mode && !(saved === "gpu" && !info.gpu_usable)) {
        apply(saved);
      }
      if (!info.gpu_usable && info.gpu_present && info.install_hint) {
        console.info("WaraqVault: GPU detected but unusable.\n" + info.reason + "\n" + info.install_hint);
      }
    })
    .catch(function () { /* the chip is informational — search works regardless */ });

  deviceSelect.addEventListener("change", function () { apply(deviceSelect.value); });
}
