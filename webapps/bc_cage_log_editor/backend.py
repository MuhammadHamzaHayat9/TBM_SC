# -*- coding: utf-8 -*-
"""
BC Cage Log Editor — Standard Webapp backend (Python tab)

Paste into the Python tab of a Dataiku Code Webapp (Standard).
`app` (a Flask app) is provided by the Dataiku backend.

Endpoints:
  GET  /schema  -> columns of the log (name + label + type + input + derived)
  GET  /data    -> current rows of Bc_Cage_SP
  POST /save    -> overwrite Bc_Cage_SP with the full table the frontend holds
                   (existing rows with edits + new rows)

Data model:
  * Bc_Cage_SP is a SINGLE editable dataset (synced once from
    bc_cage_log_prepared). The app both reads and writes it, so add and edit
    both rewrite the whole table here. The frontend's in-memory table is the
    source of truth — every save sends all rows and the backend overwrites.
  * Status is DERIVED, never typed: "Open" while "Date Removed" is blank
    (still in the cage), "Closed" once it has a date. Recomputed on save.

Note: save overwrites the whole dataset (last write wins), so this is best
for a single editor at a time. Use the reload after each save to pick up the
latest before editing.

Setup: grant Bc_Cage_SP Read/Write in the webapp Settings > Security.
"""

import json
import traceback

import dataiku
import pandas as pd
from flask import request, jsonify

# Single editable dataset: the app reads AND writes Bc_Cage_SP (synced once
# from bc_cage_log_prepared). Add and edit both rewrite the whole table here.
INPUT_DATASET = "Bc_Cage_SP"
OUTPUT_DATASET = "Bc_Cage_SP"

# Derived column: computed from "Date Removed", never entered by the user.
STATUS_COL = "Status"
DATE_REMOVED_COL = "Date Removed"
DERIVED_COLS = {STATUS_COL}

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


@app.route("/save", methods=["POST"])
def save():
    """Overwrite Bc_Cage_SP with the full table the frontend holds (existing
    rows with any edits + new rows). The frontend is the source of truth, so
    every row is sent every save; Status is recomputed server-side."""
    try:
        payload = json.loads(request.data or "{}")
        rows = payload.get("rows")
        if rows is None:
            return jsonify({"error": "No rows provided."}), 400
        # Guard against wiping the dataset by accident.
        if len(rows) == 0:
            return jsonify({"error": "Refusing to save an empty table."}), 400

        # Column order comes from the dataset schema (stable, ignores stray keys).
        base_cols = [c["name"] for c in _schema_cols()]
        df = pd.DataFrame(rows)
        if base_cols:
            df = df.reindex(columns=base_cols)

        # Status is derived, never trusted from the client.
        df = _apply_status(df)

        _ensure_output_dataset()
        dataiku.Dataset(OUTPUT_DATASET).write_with_schema(df)

        return jsonify({"saved": len(df), "total": len(df)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
