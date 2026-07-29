// Search: GET /search?q=… — scope (one file, or a workspace) comes from the
// file manager sidebar.

import { escapeHtml } from "./utils.js";
import { form, input, setStatus, showEmpty } from "./dom.js";
import { renderResults } from "./results.js";
import { getScope } from "./files.js";
import { t } from "./i18n.js";

export function runSearch(q) {
  q = (q || "").trim();
  if (q.length < 2) {
    showEmpty(t("empty-min-chars"));
    setStatus(t("status-ready"));
    return;
  }
  setStatus(t("status-searching", "<b>" + escapeHtml(q) + "</b>"));

  var url = "/search?q=" + encodeURIComponent(q);
  var scope = getScope();
  if (scope.doc_id != null) url += "&doc_id=" + encodeURIComponent(scope.doc_id);
  else if (scope.workspace) url += "&workspace=" + encodeURIComponent(scope.workspace);

  fetch(url)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      var list = (data && data.results) || [];
      if (!list.length) {
        showEmpty(t("empty-no-results", q));
        setStatus(t("status-no-matches", "<b>" + escapeHtml(q) + "</b>"));
        return;
      }
      var result = renderResults(list, q);
      setStatus(result.totalMatches + " " + result.hitWord + " " + t("result-in") + " " + result.docs + " " + result.docWord);
    })
    .catch(function (err) {
      setStatus(t("status-search-failed", escapeHtml(err.message)));
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
