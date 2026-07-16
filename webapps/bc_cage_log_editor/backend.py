# -*- coding: utf-8 -*-
"""
BC Cage Log Editor — Standard Webapp backend (Python tab)

Paste into the Python tab of a Dataiku Code Webapp (Standard).
`app` (a Flask app) is provided by the Dataiku backend.

Endpoints:
  GET  /schema  -> columns of the log (name + label + type + input + derived)
  GET  /data    -> current rows of Bc_Cage_SP (incl. row_id key)
  POST /save    -> per-row writes to Bc_Cage_SP: INSERT for new rows,
                   UPDATE ... WHERE row_id = ... for edited rows

Data model:
  * Bc_Cage_SP is a SINGLE editable PostgreSQL dataset (synced once from
    bc_cage_log_prepared, then given a `row_id` integer key). The app reads
    it and writes ONLY the changed rows via SQL — no whole-table rewrite.
  * `row_id` is the stable key; it is hidden from the grid/form. New rows get
    the next id (max+1) assigned server-side on insert.
  * Status is DERIVED, never typed: "Open" while "Date Removed" is blank
    (still in the cage), "Closed" once it has a date. Recomputed on save.

Requires: `row_id` column present in Bc_Cage_SP (add it once with the setup
script), and Read/Write on Bc_Cage_SP in the webapp Settings > Security.
"""

import json
import traceback

import dataiku
import pandas as pd
from dataiku import SQLExecutor2
from flask import request, jsonify

# Single editable PostgreSQL dataset, read + per-row SQL writes.
INPUT_DATASET = "Bc_Cage_SP"
OUTPUT_DATASET = "Bc_Cage_SP"

# Stable integer key (hidden from the UI) used to target UPDATEs.
KEY_COL = "row_id"

# Derived column: computed from "Date Removed", never entered by the user.
STATUS_COL = "Status"
DATE_REMOVED_COL = "Date Removed"
DERIVED_COLS = {STATUS_COL}
HIDDEN_COLS = {KEY_COL}

# Dataiku storage types that map to an HTML number input
_NUMERIC_TYPES = {"tinyint", "smallint", "int", "bigint", "float", "double"}
_DATE_TYPES = {"date"}

# Compact display labels so long Excel headers don't hog grid width.
# The full name still shows as a tooltip on the column header.
SHORT_LABELS = {
    "RACK ID": "Rack",
    "Date (START HERE)": "Date In",
    "Release/Repair Removal Date < 10 days": "Removal Date",
    "Person Responsible for Disposition": "Responsible",
    "Person Entering in Product or Rack": "Entered By",
    "Quantity": "Qty",
    "Tire Code(s)": "Tire Code",
    "CQ or Condition": "CQ / Condition",
    "Location (cage / overflow)": "Location",
    "Disposition": "Disposition",
    "Max. Date For Recoup <30 days": "Recoup By",
    "Comments / Notes": "Comments",
    "Person Removing Product or Rack": "Removed By",
    "Date Removed": "Date Out",
    "Status": "Status",
}


def _short_label(name):
    if name in SHORT_LABELS:
        return SHORT_LABELS[name]
    n = " ".join(str(name).split())
    return n if len(n) <= 14 else n[:13] + "…"


def _apply_status(df):
    """(Re)derive Status from Date Removed: Open while blank, else Closed."""
    if DATE_REMOVED_COL not in df.columns:
        return df
    dr = df[DATE_REMOVED_COL].astype("string").str.strip()
    is_closed = dr.notna() & (dr.str.len() > 0)
    df[STATUS_COL] = is_closed.map({True: "Closed", False: "Open"})
    return df


def _schema_cols():
    """Schema of the log: prefer the output dataset (it may have been saved
    already and is the source of truth), fall back to the original import."""
    for name in (OUTPUT_DATASET, INPUT_DATASET):
        try:
            cols = dataiku.Dataset(name).read_schema()
            if cols:
                return cols
        except Exception:
            continue
    return []


def _ensure_output_dataset():
    """Create OUTPUT_DATASET as a managed dataset if it doesn't exist yet,
    reusing the storage connection of an existing dataset in the project.
    Lets the app work script-only, with nothing to create by hand."""
    client = dataiku.api_client()
    project = client.get_default_project()
    if OUTPUT_DATASET in [d["name"] for d in project.list_datasets()]:
        return
    conn = None
    for probe in (INPUT_DATASET, "bc_cage_log_prepared", "agg_top_performers"):
        try:
            raw_settings = project.get_dataset(probe).get_settings().get_raw()
            conn = raw_settings.get("params", {}).get("connection")
            if conn:
                break
        except Exception:
            pass
    conn = conn or "filesystem_managed"
    builder = project.new_managed_dataset(OUTPUT_DATASET)
    builder.with_store_into(conn)
    builder.create()


def _load_base():
    """Rows to show/extend: previously saved output if it has rows
    (original + past additions), otherwise the original import."""
    try:
        df = dataiku.Dataset(OUTPUT_DATASET).get_dataframe(infer_with_pandas=False)
        if len(df) > 0:
            return df, OUTPUT_DATASET
    except Exception:
        pass
    df = dataiku.Dataset(INPUT_DATASET).get_dataframe(infer_with_pandas=False)
    return df, INPUT_DATASET


def _json_safe(df):
    """DataFrame -> list of dicts that json can serialize (no NaN/NaT/Timestamp)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    out = out.astype(object).where(pd.notnull(out), None)
    return out.to_dict(orient="records")


# columns with at most this many distinct values get suggestion values
# (used for autocomplete on text filters and for dropdown filters in the UI)
_SUGGEST_MAX_DISTINCT = 500


def _suggestions(df):
    """For each low-variety column, the real distinct values (most common
    first) so the form can offer them as autocomplete — without locking the
    field, so unusual values can still be typed."""
    out = {}
    if df is None or df.empty:
        return out
    for c in df.columns:
        vc = df[c].dropna().astype(str).str.strip()
        vc = vc[vc != ""]
        counts = vc.value_counts()
        if 0 < len(counts) <= _SUGGEST_MAX_DISTINCT:
            out[c] = list(counts.index[:_SUGGEST_MAX_DISTINCT])
    return out


@app.route("/schema")
def schema():
    try:
        base, _ = _load_base()
    except Exception:
        base = pd.DataFrame()
    suggest = _suggestions(base)

    cols = []
    for c in _schema_cols():
        if c["name"] in HIDDEN_COLS:
            continue
        t = (c.get("type") or "string").lower()
        if t in _NUMERIC_TYPES:
            input_type = "number"
        elif t in _DATE_TYPES:
            input_type = "date"
        else:
            input_type = "text"
        cols.append({
            "name": c["name"],
            "label": _short_label(c["name"]),
            "type": t,
            "input": input_type,
            "derived": c["name"] in DERIVED_COLS,
            "suggest": suggest.get(c["name"], []),
        })
    return jsonify({"columns": cols, "input": INPUT_DATASET, "output": OUTPUT_DATASET})


@app.route("/data")
def data():
    try:
        df, source = _load_base()
        return jsonify({
            "source": source,
            "count": len(df),
            "rows": _json_safe(df),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================
# SQL helpers for per-row INSERT / UPDATE
# ============================================================

def _all_db_cols():
    """Every column in the table, including row_id and Status."""
    return [c["name"] for c in dataiku.Dataset(OUTPUT_DATASET).read_schema()]


def _qident(name):
    """Quote a SQL identifier (handles spaces, (), /, < in the header names)."""
    return '"' + str(name).replace('"', '""') + '"'


def _lit(v):
    """SQL literal for a text value; blank/None -> NULL."""
    if v is None:
        return "NULL"
    s = str(v)
    if s.strip() == "":
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def _key_lit(v):
    """Integer literal for row_id."""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return "NULL"


def _table_name():
    """Resolved, quoted table name for Bc_Cage_SP (e.g. "PROJ_bc_cage_sp")."""
    info = dataiku.Dataset(OUTPUT_DATASET).get_location_info(sensitive_info=True).get("info", {})
    tbl = info.get("table")
    sch = info.get("schema")
    q = _qident(tbl)
    if sch:
        q = _qident(sch) + "." + q
    return q


def _with_status(row):
    """Return a copy of the row with Status derived from Date Removed."""
    r = dict(row)
    dr = r.get(DATE_REMOVED_COL)
    r[STATUS_COL] = "Closed" if (dr is not None and str(dr).strip() != "") else "Open"
    return r


@app.route("/save", methods=["POST"])
def save():
    """Per-row writes: INSERT each new row (row_id assigned max+1), UPDATE each
    edited row by row_id. All statements run in one transaction with COMMIT."""
    try:
        payload = json.loads(request.data or "{}")
        inserts = payload.get("inserts") or []
        updates = payload.get("updates") or []
        if not inserts and not updates:
            return jsonify({"error": "Nothing to save."}), 400

        cols = _all_db_cols()
        set_cols = [c for c in cols if c != KEY_COL]  # updatable columns
        table = _table_name()
        executor = SQLExecutor2(dataset=OUTPUT_DATASET)

        # next id for inserts
        next_id = 0
        if inserts:
            mdf = executor.query_to_df(
                "SELECT COALESCE(MAX(%s), 0) AS m FROM %s" % (_qident(KEY_COL), table))
            next_id = int(mdf["m"].iloc[0]) + 1

        stmts = []
        for row in inserts:
            r = _with_status(row)
            r[KEY_COL] = next_id
            next_id += 1
            names = ", ".join(_qident(c) for c in cols)
            vals = ", ".join(
                _key_lit(r.get(c)) if c == KEY_COL else _lit(r.get(c)) for c in cols)
            stmts.append("INSERT INTO %s (%s) VALUES (%s)" % (table, names, vals))

        for row in updates:
            r = _with_status(row)
            sets = ", ".join("%s = %s" % (_qident(c), _lit(r.get(c))) for c in set_cols)
            stmts.append("UPDATE %s SET %s WHERE %s = %s" % (
                table, sets, _qident(KEY_COL), _key_lit(r.get(KEY_COL))))

        # run all DML then COMMIT (DSS rolls back otherwise)
        executor.query_to_df("SELECT 1", pre_queries=stmts, post_queries=["COMMIT"])

        return jsonify({"inserted": len(inserts), "updated": len(updates)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
