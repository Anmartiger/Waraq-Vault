// Dark / light mode with persistence. The pre-paint snippet in index.html
// applies the saved theme before CSS loads; this module owns the toggle.

import { themeToggle } from "./dom.js";

var KEY = "waraq-theme";

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  themeToggle.textContent = theme === "dark" ? "🌙" : "☀️";
  themeToggle.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  try { localStorage.setItem(KEY, theme); } catch (e) { /* private mode: theme just won't persist */ }
}

export function initTheme() {
  var current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  apply(current);
  themeToggle.addEventListener("click", function () {
    apply(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}
