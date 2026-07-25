// WaraqVault UI entry point — wires the search box, the uploader and the
// results list to the local API. Loaded as a module from index.html.

import { showEmpty } from "./dom.js";
import { initSearch } from "./search.js";
import { initUpload } from "./upload.js";
import { initShowMore } from "./results.js";

initSearch();
initUpload();
initShowMore();

showEmpty("Start by searching, or upload a new document.");
