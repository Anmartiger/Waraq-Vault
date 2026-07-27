// Search: GET /search?q=…

import { escapeHtml } from "./utils.js";
import { form, input, setStatus, showEmpty, scopeSel } from "./dom.js";
import { renderResults } from "./results.js";

export function runSearch(q) {
  q = (q || "").trim();
  if (q.length < 2) {
    showEmpty("Type at least 2 characters to search…");
    setStatus("Ready");
    return;
  }
  setStatus("Searching for <b>" + escapeHtml(q) + "</b> …");
  // Scope filter: restrict the search to one document when a file is selected.
  var scope = scopeSel && scopeSel.value ? "&doc_id=" + encodeURIComponent(scopeSel.value) : "";
  fetch("/search?q=" + encodeURIComponent(q) + scope)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      var list = (data && data.results) || [];
      if (!list.length) {
        showEmpty("No results for “" + q + "”");
        setStatus("No matches for <b>" + escapeHtml(q) + "</b>");
        return;
      }
      var t = renderResults(list, q);
      setStatus(t.totalMatches + " " + t.hitWord + " in " + t.docs + " " + t.docWord);
    })
    .catch(function (err) {
      setStatus("Search failed: " + escapeHtml(err.message));
    });
}

export function initSearch() {
  var timer = null;
  form.addEventListener("submit", function (e) { e.preventDefault(); runSearch(input.value); });
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { runSearch(input.value); }, 300);
  });
}
