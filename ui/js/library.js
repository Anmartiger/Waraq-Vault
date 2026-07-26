// The library row: search-scope filter over indexed documents, plus deletion.

import { escapeHtml } from "./utils.js";
import { scopeSel, deleteBtn, input, setStatus } from "./dom.js";
import { confirmDelete } from "./modal.js";
import { runSearch } from "./search.js";

// Rebuilds the scope dropdown from the server, preserving the current selection
// when that document still exists.
export function refreshLibrary() {
  return fetch("/documents")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var docs = (data && data.documents) || [];
      var current = scopeSel.value;
      var options = ['<option value="">All files (' + docs.length + ")</option>"];
      docs.forEach(function (d) {
        options.push('<option value="' + d.id + '">' + escapeHtml(d.filename) + "</option>");
      });
      scopeSel.innerHTML = options.join("");
      var stillThere = docs.some(function (d) { return String(d.id) === current; });
      scopeSel.value = stillThere ? current : "";
      deleteBtn.disabled = !scopeSel.value;
    })
    .catch(function () { /* the library list is non-critical; search still works */ });
}

export function initLibrary() {
  refreshLibrary();

  // Changing the scope re-runs the current search inside the chosen file;
  // picking "All files" restores full-corpus search.
  scopeSel.addEventListener("change", function () {
    deleteBtn.disabled = !scopeSel.value;
    if (input.value.trim().length >= 2) runSearch(input.value);
  });

  deleteBtn.addEventListener("click", function () {
    var id = scopeSel.value;
    if (!id) return;
    var name = scopeSel.options[scopeSel.selectedIndex].textContent;

    confirmDelete(name).then(function (yes) {
      if (!yes) return;
      fetch("/documents/" + encodeURIComponent(id), { method: "DELETE" })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error((data && data.detail) || ("Delete failed (" + res.status + ")"));
            return data;
          });
        })
        .then(function () {
          setStatus("🗑️ Deleted <b>" + escapeHtml(name) + "</b> from the index.");
          return refreshLibrary();
        })
        .then(function () {
          if (input.value.trim().length >= 2) runSearch(input.value);
        })
        .catch(function (err) {
          setStatus("Delete failed: " + escapeHtml(err.message));
        });
    });
  });
}
