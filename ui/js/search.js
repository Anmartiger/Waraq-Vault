// Search: GET /search?q=… — scope (one file, or a workspace) comes from the
// file manager sidebar.

import { escapeHtml } from "./utils.js";
import { form, input, setStatus, showEmpty } from "./dom.js";
import { renderResults } from "./results.js";
import { getScope } from "./files.js";

export function runSearch(q) {
  q = (q || "").trim();
  if (q.length < 2) {
    showEmpty("Type at least 2 characters to search…");
    setStatus("Ready");
    return;
  }
  setStatus("Searching for <b>" + escapeHtml(q) + "</b> …");

  var url = "/search?q=" + encodeURIComponent(q);
  var scope = getScope();
  if (scope.doc_id != null) url += "&doc_id=" + encodeURIComponent(scope.doc_id);
  else if (scope.workspace) url += "&workspace=" + encodeURIComponent(scope.workspace);

  fetch(url)
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
