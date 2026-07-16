/* BC Cage Log Editor — JS tab of the Standard webapp.
 * Reads the schema + rows from the Python backend, renders the table,
 * builds the add-entry form from the schema, and saves everything
 * (original + pending additions) to the output dataset. */

(function () {
  "use strict";

  var columns = [];      // [{name, type, input}]
  var savedRows = [];    // rows already in the dataset
  var pendingRows = [];  // rows added in the UI, not yet saved

  function backend(path) {
    return getWebAppBackendUrl(path);
  }

  function setStatus(msg, kind) {
    var el = document.getElementById("status-msg");
    el.textContent = msg || "";
    el.className = "cage-status" + (kind ? " " + kind : "");
  }

  // ---------- rendering ----------

  function renderHeader() {
    var thead = document.querySelector("#log-table thead");
    var cells = columns.map(function (c) { return "<th>" + esc(c.name) + "</th>"; });
    thead.innerHTML = "<tr>" + cells.join("") + "</tr>";
  }

  function rowHtml(row, pending) {
    var cells = columns.map(function (c) {
      var v = row[c.name];
      return "<td>" + (v === null || v === undefined ? "" : esc(String(v))) + "</td>";
    });
    return "<tr" + (pending ? ' class="pending"' : "") + ">" + cells.join("") + "</tr>";
  }

  function renderTable() {
    var filter = (document.getElementById("table-filter").value || "").toLowerCase();
    var tbody = document.querySelector("#log-table tbody");

    function match(row) {
      if (!filter) return true;
      return columns.some(function (c) {
        var v = row[c.name];
        return v !== null && v !== undefined &&
          String(v).toLowerCase().indexOf(filter) !== -1;
      });
    }

    // pending rows first so new entries are visible without scrolling
    var html = "";
    pendingRows.filter(match).forEach(function (r) { html += rowHtml(r, true); });
    savedRows.filter(match).forEach(function (r) { html += rowHtml(r, false); });
    tbody.innerHTML = html;

    document.getElementById("row-count").textContent =
      savedRows.length + " saved" +
      (pendingRows.length ? " + " + pendingRows.length + " unsaved" : "");

    document.getElementById("save-btn").disabled = pendingRows.length === 0;
  }

  function renderForm() {
    var wrap = document.getElementById("form-fields");
    wrap.innerHTML = columns.map(function (c, i) {
      var step = c.input === "number" ? ' step="any"' : "";
      var suggest = c.suggest || [];
      var listAttr = "", datalist = "";
      if (suggest.length) {
        var listId = "dl-" + i;
        listAttr = ' list="' + listId + '"';
        datalist = '<datalist id="' + listId + '">' +
          suggest.map(function (v) { return '<option value="' + esc(String(v)) + '">'; }).join("") +
          "</datalist>";
      }
      return (
        '<label class="cage-field">' +
          '<span>' + esc(c.name) + '</span>' +
          '<input name="' + esc(c.name) + '" type="' + c.input + '"' + step + listAttr + '>' +
          datalist +
        "</label>"
      );
    }).join("");
  }

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---------- events ----------

  document.getElementById("add-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var row = {};
    var empty = true;
    columns.forEach(function (c) {
      var input = document.querySelector('#form-fields input[name="' + c.name + '"]');
      var v = input ? input.value.trim() : "";
      if (v !== "") empty = false;
      row[c.name] = v === "" ? null : v;
    });
    if (empty) { setStatus("Fill in at least one field.", "warn"); return; }
    pendingRows.unshift(row);
    e.target.reset();
    setStatus(pendingRows.length + " unsaved row(s) — click Save when done.", "warn");
    renderTable();
  });

  document.getElementById("save-btn").addEventListener("click", function () {
    if (!pendingRows.length) return;
    var btn = this;
    btn.disabled = true;
    setStatus("Saving…");
    fetch(backend("/save"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: pendingRows })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || res.j.error) throw new Error(res.j.error || "Save failed");
        setStatus("Saved " + res.j.saved + " row(s) — dataset now has " + res.j.total + " rows.", "ok");
        pendingRows = [];
        return loadData();
      })
      .catch(function (err) {
        setStatus("Error: " + err.message, "err");
        btn.disabled = false;
      });
  });

  document.getElementById("table-filter").addEventListener("input", renderTable);

  // ---------- boot ----------

  function loadData() {
    return fetch(backend("/data"))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) throw new Error(j.error);
        savedRows = j.rows || [];
        document.getElementById("source-line").textContent =
          j.count + " rows — reading from “" + j.source + "”";
        renderTable();
      });
  }

  fetch(backend("/schema"))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      columns = j.columns || [];
      document.getElementById("output-name").textContent = j.output;
      if (!columns.length) throw new Error("Could not read the schema of " + j.input);
      renderHeader();
      renderForm();
      return loadData();
    })
    .catch(function (err) {
      document.getElementById("source-line").textContent = "Error: " + err.message;
    });
})();
