/* BC Cage Log — BFGoodrich-themed data grid (JS tab).
 * Reads schema + rows from the Python backend, renders a sortable, per-column
 * filterable grid, and adds/saves new entries via a modal dialog. */

(function () {
  "use strict";

  var MAX_RENDER = 1500;              // cap DOM rows for snappy filtering
  var columns = [];                  // [{name,label,type,input,derived,suggest}]
  var savedRows = [];                // rows already in the dataset
  var pendingRows = [];              // rows added in the UI, not yet saved
  var statusCol = null;              // name of derived Status column, if any
  var colFilters = {};               // colName -> filter text/value
  var sort = { name: null, dir: 1 }; // active sort column + direction

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

  // ---------- build header, filter row, datalists ----------

  function buildDatalists() {
    var box = document.getElementById("datalists");
    box.innerHTML = columns.map(function (c, i) {
      if (!c.suggest || !c.suggest.length) return "";
      return '<datalist id="dl-' + i + '">' +
        c.suggest.map(function (v) { return '<option value="' + esc(v) + '">'; }).join("") +
        "</datalist>";
    }).join("");
  }

  function buildHead() {
    var head = document.getElementById("head-row");
    head.innerHTML = columns.map(function (c) {
      var ind = "";
      if (sort.name === c.name) ind = '<span class="sort-ind">' + (sort.dir > 0 ? "▲" : "▼") + "</span>";
      return '<th data-col="' + esc(c.name) + '" title="' + esc(c.name) + '">' +
        esc(c.label || c.name) + ind + "</th>";
    }).join("");
    head.querySelectorAll("th").forEach(function (th) {
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
    var row = document.getElementById("filter-row");
    row.innerHTML = columns.map(function (c, i) {
      if (c.name === statusCol) {
        var opts = ['<option value="">All</option>']
          .concat((c.suggest || ["Open", "Closed"]).map(function (v) {
            return '<option value="' + esc(v) + '">' + esc(v) + "</option>";
          }));
        return "<th><select data-col=\"" + esc(c.name) + "\">" + opts.join("") + "</select></th>";
      }
      var list = (c.suggest && c.suggest.length) ? ' list="dl-' + i + '"' : "";
      return '<th><input data-col="' + esc(c.name) + '"' + list +
        ' placeholder="filter…"></th>';
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

  // ---------- filtering + sorting ----------

  function passesFilters(row, global) {
    for (var name in colFilters) {
      if (!colFilters.hasOwnProperty(name)) continue;
      var f = colFilters[name];
      var cell = val(row, name).toLowerCase();
      if (name === statusCol) { if (val(row, name) !== f) return false; }
      else if (cell.indexOf(f.toLowerCase()) === -1) return false;
    }
    if (global) {
      var hit = columns.some(function (c) {
        return val(row, c.name).toLowerCase().indexOf(global) !== -1;
      });
      if (!hit) return false;
    }
    return true;
  }

  function sortRows(rows) {
    if (!sort.name) return rows;
    var name = sort.name, dir = sort.dir;
    return rows.slice().sort(function (a, b) {
      var av = val(a, name), bv = val(b, name);
      if (av === "" && bv === "") return 0;
      if (av === "") return 1;            // blanks always last
      if (bv === "") return -1;
      var an = parseFloat(av), bn = parseFloat(bv);
      var numeric = !isNaN(an) && !isNaN(bn) &&
        /^-?\d/.test(av) && /^-?\d/.test(bv);
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

    var pend = pendingRows.filter(function (r) { return passesFilters(r, global); });
    var saved = savedRows.filter(function (r) { return passesFilters(r, global); });
    saved = sortRows(saved);

    var rows = pend.map(function (r) { return { r: r, p: true }; })
      .concat(saved.map(function (r) { return { r: r, p: false }; }));

    var shown = rows.slice(0, MAX_RENDER);
    var tbody = document.querySelector("#grid tbody");
    tbody.innerHTML = shown.map(function (o) {
      var tds = columns.map(function (c) { return cellHtml(c, o.r); }).join("");
      return "<tr" + (o.p ? ' class="pending"' : "") + ">" + tds + "</tr>";
    }).join("");

    document.getElementById("empty-note").hidden = rows.length !== 0;

    var total = savedRows.length + pendingRows.length;
    var matched = rows.length;
    var capped = matched > MAX_RENDER ? " (showing first " + MAX_RENDER + ")" : "";
    document.getElementById("row-count").textContent =
      "Showing " + Math.min(matched, MAX_RENDER) + " of " + total + " rows" + capped +
      (pendingRows.length ? " · " + pendingRows.length + " unsaved" : "");

    document.getElementById("save-btn").disabled = pendingRows.length === 0;
    document.getElementById("save-btn").textContent =
      pendingRows.length ? "Save changes (" + pendingRows.length + ")" : "Save changes";
  }

  // ---------- add-entry modal ----------

  function buildForm() {
    var wrap = document.getElementById("form-fields");
    wrap.innerHTML = columns.filter(function (c) { return !c.derived; })
      .map(function (c) {
        var idx = columns.indexOf(c);
        var step = c.input === "number" ? ' step="any"' : "";
        var list = (c.suggest && c.suggest.length) ? ' list="dl-' + idx + '"' : "";
        return '<div class="field">' +
          "<label title=\"" + esc(c.name) + "\">" + esc(c.label || c.name) + "</label>" +
          '<input name="' + esc(c.name) + '" type="' + c.input + '"' + step + list + ">" +
          "</div>";
      }).join("");
  }

  function openModal() {
    document.getElementById("add-form").reset();
    setMsg(document.getElementById("modal-msg"), "");
    document.getElementById("modal").hidden = false;
  }
  function closeModal() { document.getElementById("modal").hidden = true; }

  // ---------- events ----------

  document.getElementById("add-btn").addEventListener("click", openModal);
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", function (e) {
    if (e.target === this) closeModal();
  });

  document.getElementById("add-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var row = {}, empty = true;
    columns.forEach(function (c) {
      if (c.derived) { row[c.name] = null; return; }
      var input = this.querySelector('input[name="' + cssEsc(c.name) + '"]');
      var v = input ? input.value.trim() : "";
      if (v !== "") empty = false;
      row[c.name] = v === "" ? null : v;
    }, this);
    if (empty) { setMsg(document.getElementById("modal-msg"), "Fill in at least one field.", "warn"); return; }
    pendingRows.unshift(row);
    closeModal();
    setMsg(document.getElementById("status-msg"), pendingRows.length + " unsaved — click Save changes.", "warn");
    render();
  });

  document.getElementById("save-btn").addEventListener("click", function () {
    if (!pendingRows.length) return;
    var btn = this;
    btn.disabled = true;
    setMsg(document.getElementById("status-msg"), "Saving…");
    fetch(backend("/save"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: pendingRows })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || res.j.error) throw new Error(res.j.error || "Save failed");
        setMsg(document.getElementById("status-msg"),
          "Saved " + res.j.saved + " row(s) — " + res.j.total + " total.", "ok");
        pendingRows = [];
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

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !document.getElementById("modal").hidden) closeModal();
  });

  // querySelector needs escaped attribute values; names have spaces/()/. etc.
  function cssEsc(s) { return s.replace(/["\\]/g, "\\$&"); }

  // ---------- boot ----------

  function loadData() {
    return fetch(backend("/data"))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) throw new Error(j.error);
        savedRows = j.rows || [];
        document.getElementById("source-line").textContent =
          j.count + " records · source: " + j.source;
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
      document.getElementById("source-line").textContent = "Error: " + err.message;
    });
})();
