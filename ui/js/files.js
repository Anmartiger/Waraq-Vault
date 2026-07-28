// The file manager sidebar: workspaces, type filter, the document list with
// multi-select + bulk delete, the active search scope, and the details panel.

import { escapeHtml, typeLabel } from "./utils.js";
import {
  input, setStatus, filesCount, wsList, typeChips, fileFilter, docList,
  selBar, selCount, selDelete, selClear, scopeBar, scopeLabel, scopeClear,
  detBody, workspaceInput
} from "./dom.js";
import { confirmDelete } from "./modal.js";
import { runSearch } from "./search.js";

var state = {
  docs: [],
  workspaces: [],
  workspace: "",      // "" = all workspaces
  docId: null,        // number = search scoped to that document
  typeFilter: "",
  nameFilter: "",
  selected: new Set() // doc ids checked in the manager
};

var ICONS = { pdf: "📕", docx: "📘", txt: "📄", image: "🖼️" };

function kindOf(doc) {
  var ct = (doc.content_type || "").toLowerCase();
  if (ct.indexOf("pdf") > -1) return "pdf";
  if (ct.indexOf("word") > -1) return "docx";
  if (ct.indexOf("image/") === 0) return "image";
  return "txt";
}

function fmtChars(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M chars";
  if (n >= 1000) return Math.round(n / 1000) + "K chars";
  return n + " chars";
}

function rerunSearch() {
  if (input.value.trim().length >= 2) runSearch(input.value);
}

// ---- the scope that search.js reads -------------------------------------
export function getScope() {
  if (state.docId != null) return { doc_id: state.docId };
  if (state.workspace) return { workspace: state.workspace };
  return {};
}

function renderScopeBar() {
  if (state.docId != null) {
    var doc = state.docs.find(function (d) { return d.id === state.docId; });
    scopeLabel.textContent = "Searching in: " + (doc ? doc.filename : "#" + state.docId);
    scopeBar.hidden = false;
  } else if (state.workspace) {
    scopeLabel.textContent = "Searching in workspace: " + state.workspace;
    scopeBar.hidden = false;
  } else {
    scopeBar.hidden = true;
  }
}

// ---- rendering -----------------------------------------------------------
function renderWorkspaces() {
  var total = state.docs.length;
  var rows = ['<div class="ws-row' + (state.workspace === "" ? " active" : "") + '" data-ws="">' +
              '<span class="ws-name">All files</span><span class="ws-n">' + total + "</span></div>"];
  state.workspaces.forEach(function (w) {
    rows.push(
      '<div class="ws-row' + (state.workspace === w.name ? " active" : "") + '" data-ws="' + escapeHtml(w.name) + '">' +
        '<span class="ws-name">' + escapeHtml(w.name) + "</span>" +
        '<span class="ws-n">' + w.count + "</span>" +
        '<button type="button" class="ws-del" title="Delete this workspace and its files" data-del-ws="' + escapeHtml(w.name) + '">🗑</button>' +
      "</div>"
    );
  });
  wsList.innerHTML = rows.join("");
}

function visibleDocs() {
  return state.docs.filter(function (d) {
    if (state.workspace && d.workspace !== state.workspace) return false;
    if (state.typeFilter && kindOf(d) !== state.typeFilter) return false;
    if (state.nameFilter && d.filename.toLowerCase().indexOf(state.nameFilter) === -1) return false;
    return true;
  });
}

function renderDocs() {
  var docs = visibleDocs();
  filesCount.textContent = state.docs.length ? state.docs.length + " files" : "";
  if (!docs.length) {
    docList.innerHTML = '<div class="doc-empty">' +
      (state.docs.length ? "Nothing matches this filter." : "No documents yet — upload something.") + "</div>";
  } else {
    docList.innerHTML = docs.map(function (d) {
      var checked = state.selected.has(d.id) ? " checked" : "";
      return '<div class="doc-row' + (state.docId === d.id ? " active" : "") + '" data-id="' + d.id + '" role="option">' +
        '<input type="checkbox" class="d-check" data-check="' + d.id + '"' + checked + ">" +
        '<span class="d-ico">' + (ICONS[kindOf(d)] || "📄") + "</span>" +
        '<span class="d-main"><span class="d-name">' + escapeHtml(d.filename) + "</span>" +
          '<span class="d-meta">' + typeLabel(d.content_type) + " · " + fmtChars(d.chars || 0) +
          (state.workspace ? "" : " · " + escapeHtml(d.workspace || "Default")) + "</span></span>" +
        (d.openable
          ? '<button type="button" class="d-del d-open" title="Open the original file" data-open="' + d.id + '">↗</button>'
          : "") +
        '<button type="button" class="d-del" title="Delete this file" data-del="' + d.id + '">🗑</button>' +
      "</div>";
    }).join("");
  }
  renderSelBar();
  renderScopeBar();
}

function renderSelBar() {
  var n = state.selected.size;
  selBar.hidden = n === 0;
  selCount.textContent = n + " selected";
}

function renderDetails() {
  var doc = state.docId != null ? state.docs.find(function (d) { return d.id === state.docId; }) : null;
  if (doc) {
    detBody.innerHTML =
      '<div class="det-card">' +
        '<div class="det-name">' + escapeHtml(doc.filename) + "</div>" +
        '<div class="det-kv"><span class="k">Type</span><span class="v">' + typeLabel(doc.content_type) + "</span></div>" +
        '<div class="det-kv"><span class="k">Workspace</span><span class="v">' + escapeHtml(doc.workspace || "Default") + "</span></div>" +
        '<div class="det-kv"><span class="k">Extracted text</span><span class="v">' + fmtChars(doc.chars || 0) + "</span></div>" +
        '<div class="det-kv"><span class="k">Indexed</span><span class="v">' + escapeHtml(doc.created_at || "—") + "</span></div>" +
        '<div class="det-kv"><span class="k">ID</span><span class="v">#' + doc.id + "</span></div>" +
      "</div>" +
      '<div class="det-actions">' +
        (doc.openable
          ? '<button type="button" class="btn-open" id="det-open">Open original ↗</button>'
          : '<button type="button" class="btn-open" disabled ' +
            'title="Uploaded before file-opening existed — re-upload to enable">Open original ↗</button>') +
        '<button type="button" class="btn-del" id="det-delete">Delete file</button>' +
        '<button type="button" class="btn-ghost-mini" id="det-unscope">Clear selection</button>' +
      "</div>" +
      '<div class="det-hint">Search is scoped to this file — clear to search everything.</div>';
    document.getElementById("det-delete").addEventListener("click", function () { deleteOne(doc.id, doc.filename); });
    var detOpen = document.getElementById("det-open");
    if (detOpen) detOpen.addEventListener("click", function () { openOriginal(doc.id); });
    document.getElementById("det-unscope").addEventListener("click", function () { setDocScope(null); });
  } else {
    var byType = { pdf: 0, docx: 0, txt: 0, image: 0 };
    var chars = 0;
    state.docs.forEach(function (d) { byType[kindOf(d)]++; chars += d.chars || 0; });
    detBody.innerHTML =
      '<div class="statgrid">' +
        '<div class="stat"><div class="n">' + state.docs.length + '</div><div class="l">documents</div></div>' +
        '<div class="stat"><div class="n">' + state.workspaces.length + '</div><div class="l">workspaces</div></div>' +
        '<div class="stat"><div class="n">' + byType.pdf + '</div><div class="l">PDF</div></div>' +
        '<div class="stat"><div class="n">' + byType.docx + '</div><div class="l">DOCX</div></div>' +
        '<div class="stat"><div class="n">' + byType.txt + '</div><div class="l">TXT</div></div>' +
        '<div class="stat"><div class="n">' + byType.image + '</div><div class="l">images</div></div>' +
      "</div>" +
      '<div class="det-card"><div class="det-kv"><span class="k">Indexed text</span><span class="v">' + fmtChars(chars) + "</span></div>" +
      '<div class="det-kv"><span class="k">Storage</span><span class="v">local · waraq.db</span></div></div>' +
      '<div class="det-hint">Select a file in the library to see its details, or click one to search inside it.</div>';
  }
}

function renderAll() { renderWorkspaces(); renderDocs(); renderDetails(); }

// The server streams the stored copy back; the browser renders PDFs and images
// inline and downloads anything it cannot display.
function openOriginal(id) {
  window.open("/documents/" + id + "/open", "_blank", "noopener");
}

// ---- scope + selection ----------------------------------------------------
function setDocScope(id) {
  state.docId = (id != null && state.docId === id) ? null : id;   // click again to clear
  renderDocs(); renderDetails();
  rerunSearch();
}

function setWorkspace(name) {
  state.workspace = name;
  state.docId = null;
  renderAll();
  rerunSearch();
}

// ---- deletion flows --------------------------------------------------------
function afterMutation() {
  return refreshLibrary().then(function () { rerunSearch(); });
}

function deleteOne(id, name) {
  confirmDelete(name).then(function (yes) {
    if (!yes) return;
    fetch("/documents/" + id, { method: "DELETE" })
      .then(function (res) { return res.json().then(function (d) { if (!res.ok) throw new Error((d && d.detail) || res.status); return d; }); })
      .then(function () {
        state.selected.delete(id);
        if (state.docId === id) state.docId = null;
        setStatus("🗑️ Deleted <b>" + escapeHtml(name) + "</b> from the index.");
        return afterMutation();
      })
      .catch(function (err) { setStatus("Delete failed: " + escapeHtml(err.message)); });
  });
}

function deleteSelected() {
  var ids = Array.from(state.selected);
  if (!ids.length) return;
  confirmDelete(ids.length + " selected files").then(function (yes) {
    if (!yes) return;
    fetch("/documents/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids })
    })
      .then(function (res) { return res.json().then(function (d) { if (!res.ok) throw new Error((d && d.detail) || res.status); return d; }); })
      .then(function (d) {
        state.selected.clear();
        if (ids.indexOf(state.docId) > -1) state.docId = null;
        setStatus("🗑️ Deleted <b>" + d.deleted + "</b> files from the index.");
        return afterMutation();
      })
      .catch(function (err) { setStatus("Bulk delete failed: " + escapeHtml(err.message)); });
  });
}

function deleteWorkspaceFlow(name) {
  var ws = state.workspaces.find(function (w) { return w.name === name; });
  var n = ws ? ws.count : "its";
  confirmDelete('Workspace "' + name + '"', "<br>All <b>" + n + " files</b> inside it will be removed in one shot.").then(function (yes) {
    if (!yes) return;
    fetch("/workspaces/" + encodeURIComponent(name), { method: "DELETE" })
      .then(function (res) { return res.json().then(function (d) { if (!res.ok) throw new Error((d && d.detail) || res.status); return d; }); })
      .then(function (d) {
        if (state.workspace === name) state.workspace = "";
        state.docId = null;
        setStatus("🗑️ Deleted workspace <b>" + escapeHtml(name) + "</b> (" + d.deleted + " files).");
        return afterMutation();
      })
      .catch(function (err) { setStatus("Workspace delete failed: " + escapeHtml(err.message)); });
  });
}

// ---- data ------------------------------------------------------------------
export function refreshLibrary() {
  return Promise.all([
    fetch("/documents").then(function (r) { return r.json(); }),
    fetch("/workspaces").then(function (r) { return r.json(); })
  ]).then(function (both) {
    state.docs = (both[0] && both[0].documents) || [];
    state.workspaces = (both[1] && both[1].workspaces) || [];
    // drop stale ids (deleted elsewhere)
    var alive = new Set(state.docs.map(function (d) { return d.id; }));
    state.selected.forEach(function (id) { if (!alive.has(id)) state.selected.delete(id); });
    if (state.docId != null && !alive.has(state.docId)) state.docId = null;
    if (state.workspace && !state.workspaces.some(function (w) { return w.name === state.workspace; })) state.workspace = "";
    renderAll();
  }).catch(function () { /* the library list is non-critical; search still works */ });
}

export function initFiles() {
  refreshLibrary();

  wsList.addEventListener("click", function (e) {
    var del = e.target.closest("[data-del-ws]");
    if (del) { e.stopPropagation(); deleteWorkspaceFlow(del.getAttribute("data-del-ws")); return; }
    var row = e.target.closest("[data-ws]");
    if (row) setWorkspace(row.getAttribute("data-ws"));
  });

  typeChips.addEventListener("click", function (e) {
    var chip = e.target.closest(".fchip");
    if (!chip) return;
    typeChips.querySelectorAll(".fchip").forEach(function (c) { c.classList.remove("active"); });
    chip.classList.add("active");
    state.typeFilter = chip.getAttribute("data-type");
    renderDocs();
  });

  fileFilter.addEventListener("input", function () {
    state.nameFilter = fileFilter.value.trim().toLowerCase();
    renderDocs();
  });

  docList.addEventListener("click", function (e) {
    var check = e.target.closest("[data-check]");
    if (check) {
      var cid = parseInt(check.getAttribute("data-check"), 10);
      if (check.checked) state.selected.add(cid); else state.selected.delete(cid);
      renderSelBar();
      return;                                   // checkbox click ≠ scope click
    }
    var open = e.target.closest("[data-open]");
    if (open) { openOriginal(parseInt(open.getAttribute("data-open"), 10)); return; }
    var del = e.target.closest("[data-del]");
    if (del) {
      var didNum = parseInt(del.getAttribute("data-del"), 10);
      var doc = state.docs.find(function (d) { return d.id === didNum; });
      deleteOne(didNum, doc ? doc.filename : "#" + didNum);
      return;
    }
    var row = e.target.closest(".doc-row");
    if (row) setDocScope(parseInt(row.getAttribute("data-id"), 10));
  });

  selDelete.addEventListener("click", deleteSelected);
  selClear.addEventListener("click", function () { state.selected.clear(); renderDocs(); });
  scopeClear.addEventListener("click", function () {
    state.docId = null; state.workspace = "";
    renderAll(); rerunSearch();
  });

  // Workspace name suggestions for the upload input
  workspaceInput.addEventListener("focus", function () {
    if (!workspaceInput.getAttribute("list")) {
      var dl = document.createElement("datalist");
      dl.id = "ws-suggestions";
      document.body.appendChild(dl);
      workspaceInput.setAttribute("list", "ws-suggestions");
    }
    var dlEl = document.getElementById("ws-suggestions");
    dlEl.innerHTML = state.workspaces.map(function (w) {
      return '<option value="' + escapeHtml(w.name) + '">';
    }).join("");
  });
}
