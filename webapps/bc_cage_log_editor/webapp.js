/* BC Cage Log — BFGoodrich-themed editable data grid (JS tab).
 * Reads Bc_Cage_SP into memory, lets the user add and edit rows, and saves
 * the whole table back to Bc_Cage_SP. The in-memory `rows` array is the
 * source of truth; every save sends all rows and the backend overwrites. */

(function () {
  "use strict";

  var MAX_RENDER = 1500;             // cap DOM rows for snappy filtering
  var DROPDOWN_MAX = 40;             // <= this many distinct values -> dropdown filter
  var DATE_OUT_COL = "Date Removed"; // drives the derived Status client-side

  var columns = [];                  // [{name,label,type,input,derived,suggest}]
  var rows = [];                     // all rows (objects) — the source of truth
  var newSet = new Set();            // rows added in the UI, not yet saved
  var editSet = new Set();           // existing rows edited, not yet saved
  var statusCol = null;              // name of derived Status column, if any
  var colFilters = {};               // colName -> filter text/value
  var exactCols = {};                // colName -> true when its filter is a dropdown
  var sort = { name: null, dir: 1 }; // active sort column + direction
  var editingRow = null;             // row object being edited (null = add mode)

  function backend(p) { return getWebAppBackendUrl(p); }

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function val(row, name) {
    var v = row[name];
    return (v === null || v === undefined) ? "" : String(v);
  }
  function setMsg(el, msg, kind) {
    el.textContent = msg || "";
    el.className = "status-msg" + (kind ? " " + kind : "");
  }
  function cssEsc(s) { return s.replace(/["\\]/g, "\\$&"); }

  // Status derivation, mirrored client-side so the pill updates immediately.
  function clientStatus(row) {
    if (!statusCol) return;
    var v = row[DATE_OUT_COL];
    var closed = v !== null && v !== undefined && String(v).trim() !== "";
    row[statusCol] = closed ? "Closed" : "Open";
  }

  // ---------- build header / filter row / datalists ----------

  function buildDatalists() {
    document.getElementById("datalists").innerHTML = columns.map(function (c, i) {
      if (!c.suggest || !c.suggest.length) return "";
      return '<datalist id="dl-' + i + '">' +
        c.suggest.map(function (v) { return '<option value="' + esc(v) + '">'; }).join("") +
        "</datalist>";
    }).join("");
  }

  function buildHead() {
    var head = document.getElementById("head-row");
    head.innerHTML = '<th class="col-actions"></th>' + columns.map(function (c) {
      var ind = (sort.name === c.name) ? '<span class="sort-ind">' + (sort.dir > 0 ? "▲" : "▼") + "</span>" : "";
      return '<th data-col="' + esc(c.name) + '" title="' + esc(c.name) + '">' +
        esc(c.label || c.name) + ind + "</th>";
    }).join("");
    head.querySelectorAll("th[data-col]").forEach(function (th) {
      th.addEventListener("click", function () {
        var name = th.getAttribute("data-col");
        if (sort.name === name) sort.dir = -sort.dir;
        else { sort.name = name; sort.dir = 1; }
        buildHead();
        render();
      });
    });
  }

  function buildFilterRow() {
    exactCols = {};
    var row = document.getElementById("filter-row");
    row.innerHTML = '<th class="col-actions"></th>' + columns.map(function (c, i) {
      var sug = c.suggest || [];
      var asDropdown = (c.name === statusCol) || (sug.length >= 1 && sug.length <= DROPDOWN_MAX);
      if (asDropdown) {
        exactCols[c.name] = true;
        var vals = (sug.length ? sug.slice() : ["Open", "Closed"]).sort(function (a, b) {
          return String(a).localeCompare(String(b), undefined, { numeric: true });
        });
        var opts = ['<option value="">All</option>'].concat(vals.map(function (v) {
          return '<option value="' + esc(v) + '">' + esc(v) + "</option>";
        }));
        return '<th><select data-col="' + esc(c.name) + '">' + opts.join("") + "</select></th>";
      }
      var list = sug.length ? ' list="dl-' + i + '"' : "";
      return '<th><input data-col="' + esc(c.name) + '"' + list + ' placeholder="filter…"></th>';
    }).join("");
    row.querySelectorAll("input,select").forEach(function (el) {
      var ev = el.tagName === "SELECT" ? "change" : "input";
      el.addEventListener(ev, function () {
        var name = el.getAttribute("data-col");
        var v = el.value.trim();
        if (v) colFilters[name] = v; else delete colFilters[name];
        render();
      });
    });
  }

  // ---------- filter + sort ----------

  function passesFilters(row, global) {
    for (var name in colFilters) {
      if (!colFilters.hasOwnProperty(name)) continue;
      var f = colFilters[name];
      if (exactCols[name]) { if (val(row, name) !== f) return false; }
      else if (val(row, name).toLowerCase().indexOf(f.toLowerCase()) === -1) return false;
    }
    if (global) {
      var hit = columns.some(function (c) {
        return val(row, c.name).toLowerCase().indexOf(global) !== -1;
      });
      if (!hit) return false;
    }
    return true;
  }

  function sortShown(list) {
    if (!sort.name) return list;
    var name = sort.name, dir = sort.dir;
    return list.slice().sort(function (a, b) {
      var av = val(a, name), bv = val(b, name);
      if (av === "" && bv === "") return 0;
      if (av === "") return 1;
      if (bv === "") return -1;
      var an = parseFloat(av), bn = parseFloat(bv);
      var numeric = !isNaN(an) && !isNaN(bn) && /^-?\d/.test(av) && /^-?\d/.test(bv);
      if (numeric) return (an - bn) * dir;
      return av.localeCompare(bv, undefined, { numeric: true }) * dir;
    });
  }

  // ---------- render ----------

  function cellHtml(c, row) {
    var text = val(row, c.name);
    if (c.name === statusCol && text) {
      var cls = text.toLowerCase() === "open" ? "pill pill-open" : "pill pill-closed";
      return '<td><span class="' + cls + '">' + esc(text) + "</span></td>";
    }
    return '<td title="' + esc(text) + '">' + esc(text) + "</td>";
  }

  function render() {
    var global = (document.getElementById("global-search").value || "").trim().toLowerCase();

    var shown = sortShown(rows.filter(function (r) { return passesFilters(r, global); }));
    var slice = shown.slice(0, MAX_RENDER);

    var tbody = document.querySelector("#grid tbody");
    tbody.innerHTML = slice.map(function (r) {
      var idx = rows.indexOf(r);
      var cls = newSet.has(r) ? " pending" : (editSet.has(r) ? " edited" : "");
      var tds = columns.map(function (c) { return cellHtml(c, r); }).join("");
      return "<tr class=\"row" + cls + "\" data-i=\"" + idx + "\">" +
        '<td class="col-actions"><button class="row-edit" title="Edit row">✎</button></td>' +
        tds + "</tr>";
    }).join("");

    document.getElementById("empty-note").hidden = shown.length !== 0;

    var dirty = newSet.size + editSet.size;
    var capped = shown.length > MAX_RENDER ? " (showing first " + MAX_RENDER + ")" : "";
    document.getElementById("row-count").textContent =
      "Showing " + Math.min(shown.length, MAX_RENDER) + " of " + rows.length + " rows" + capped +
      (dirty ? " · " + dirty + " unsaved" : "");

    var save = document.getElementById("save-btn");
    save.disabled = dirty === 0;
    save.textContent = dirty ? "Save changes (" + dirty + ")" : "Save changes";
  }

  // ---------- add / edit modal ----------

  function buildForm() {
    document.getElementById("form-fields").innerHTML =
      columns.filter(function (c) { return !c.derived; }).map(function (c) {
        var idx = columns.indexOf(c);
        var step = c.input === "number" ? ' step="any"' : "";
        var list = (c.suggest && c.suggest.length) ? ' list="dl-' + idx + '"' : "";
        return '<div class="field">' +
          "<label title=\"" + esc(c.name) + "\">" + esc(c.label || c.name) + "</label>" +
          '<input name="' + esc(c.name) + '" type="' + c.input + '"' + step + list + ">" +
          "</div>";
      }).join("");
  }

  function openModal(rowObj) {
    editingRow = rowObj || null;
    var form = document.getElementById("add-form");
    form.reset();
    setMsg(document.getElementById("modal-msg"), "");
    document.getElementById("modal-title").textContent =
      editingRow ? "Edit cage log entry" : "Add cage log entry";
    document.getElementById("modal-submit").textContent =
      editingRow ? "Save row" : "Add to grid";
    if (editingRow) {
      columns.forEach(function (c) {
        if (c.derived) return;
        var input = form.querySelector('input[name="' + cssEsc(c.name) + '"]');
        if (input) input.value = val(editingRow, c.name);
      });
    }
    document.getElementById("modal").hidden = false;
  }
  function closeModal() { document.getElementById("modal").hidden = true; editingRow = null; }

  // ---------- events ----------

  document.getElementById("add-btn").addEventListener("click", function () { openModal(null); });
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", function (e) {
    if (e.target === this) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !document.getElementById("modal").hidden) closeModal();
  });

  // open editor when an ✎ button is clicked
  document.querySelector("#grid tbody").addEventListener("click", function (e) {
    var btn = e.target.closest(".row-edit");
    if (!btn) return;
    var tr = btn.closest("tr");
    var idx = parseInt(tr.getAttribute("data-i"), 10);
    if (!isNaN(idx) && rows[idx]) openModal(rows[idx]);
  });

  document.getElementById("add-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var form = this;
    var values = {}, empty = true;
    columns.forEach(function (c) {
      if (c.derived) return;
      var input = form.querySelector('input[name="' + cssEsc(c.name) + '"]');
      var v = input ? input.value.trim() : "";
      if (v !== "") empty = false;
      values[c.name] = v === "" ? null : v;
    });
    if (empty) { setMsg(document.getElementById("modal-msg"), "Fill in at least one field.", "warn"); return; }

    if (editingRow) {
      columns.forEach(function (c) { if (!c.derived) editingRow[c.name] = values[c.name]; });
      clientStatus(editingRow);
      if (!newSet.has(editingRow)) editSet.add(editingRow);   // new rows stay "new"
    } else {
      var row = {};
      columns.forEach(function (c) { row[c.name] = c.derived ? null : values[c.name]; });
      clientStatus(row);
      rows.unshift(row);
      newSet.add(row);
    }
    closeModal();
    render();
  });

  document.getElementById("save-btn").addEventListener("click", function () {
    var dirty = newSet.size + editSet.size;
    if (!dirty) return;
    var btn = this;
    btn.disabled = true;
    setMsg(document.getElementById("status-msg"), "Saving…");
    // send only the changed rows: new rows -> INSERT, edited rows -> UPDATE
    var inserts = Array.from(newSet);
    var updates = Array.from(editSet);
    fetch(backend("/save"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inserts: inserts, updates: updates })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || res.j.error) throw new Error(res.j.error || "Save failed");
        setMsg(document.getElementById("status-msg"),
          "Saved — " + res.j.inserted + " added, " + res.j.updated + " updated.", "ok");
        return loadData();
      })
      .catch(function (err) {
        setMsg(document.getElementById("status-msg"), "Error: " + err.message, "err");
        btn.disabled = false;
      });
  });

  document.getElementById("global-search").addEventListener("input", render);
  document.getElementById("clear-filters").addEventListener("click", function () {
    colFilters = {};
    document.getElementById("global-search").value = "";
    document.querySelectorAll("#filter-row input, #filter-row select").forEach(function (el) { el.value = ""; });
    render();
  });

  // ---------- boot ----------

  function loadData() {
    return fetch(backend("/data"))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) throw new Error(j.error);
        rows = j.rows || [];
        newSet = new Set();
        editSet = new Set();
        render();
      });
  }

  var logo = document.getElementById("brand-logo");
  logo.addEventListener("error", function () { this.style.display = "none"; });

  fetch(backend("/schema"))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      columns = j.columns || [];
      if (!columns.length) throw new Error("Could not read the schema of " + j.input);
      var derived = columns.filter(function (c) { return c.derived; })[0];
      statusCol = derived ? derived.name : null;
      buildDatalists();
      buildHead();
      buildFilterRow();
      buildForm();
      return loadData();
    })
    .catch(function (err) {
      setMsg(document.getElementById("status-msg"), "Error: " + err.message, "err");
    });
})();
