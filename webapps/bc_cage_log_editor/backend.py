# -*- coding: utf-8 -*-
"""
BC Cage Log Editor — Standard Webapp backend (Python tab)

Paste into the Python tab of a Dataiku Code Webapp (Standard).
`app` (a Flask app) is provided by the Dataiku backend.

Endpoints:
  GET  /schema  -> columns of the log (name + type + suggested input type)
  GET  /data    -> current rows (saved output if it exists, else BC_Cage_Log)
  POST /save    -> append the submitted new rows and write everything
                   (original + additions) to BC_CAGE_LOG_UPDATED

Setup: create a managed output dataset named BC_Cage_Log_updated in the
Flow (e.g. +Dataset > Internal > Managed, filesystem connection) before
the first Save, and list both datasets in the webapp Settings > Security
(BC_Cage_Log: Read, BC_Cage_Log_updated: Write).
"""

import json
import traceback

import dataiku
import pandas as pd
from flask import request, jsonify

INPUT_DATASET = "BC_Cage_Log"
OUTPUT_DATASET = "BC_Cage_Log_updated"

# Dataiku storage types that map to an HTML number input
_NUMERIC_TYPES = {"tinyint", "smallint", "int", "bigint", "float", "double"}
_DATE_TYPES = {"date"}


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


@app.route("/schema")
def schema():
    cols = []
    for c in _schema_cols():
        t = (c.get("type") or "string").lower()
        if t in _NUMERIC_TYPES:
            input_type = "number"
        elif t in _DATE_TYPES:
            input_type = "date"
        else:
            input_type = "text"
        cols.append({"name": c["name"], "type": t, "input": input_type})
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
    try:
        payload = json.loads(request.data or "{}")
        new_rows = payload.get("rows") or []
        if not new_rows:
            return jsonify({"error": "No new rows to save."}), 400

        base, _ = _load_base()
        add = pd.DataFrame(new_rows)

        # Keep the base column order; ignore unknown keys, fill missing with NA
        add = add.reindex(columns=base.columns)

        # Coerce numeric columns so "12" from the form matches the base dtype
        for c in base.columns:
            if pd.api.types.is_numeric_dtype(base[c]):
                add[c] = pd.to_numeric(add[c], errors="coerce")

        full = pd.concat([base, add], ignore_index=True)

        out = dataiku.Dataset(OUTPUT_DATASET)
        out.write_with_schema(full)

        return jsonify({"saved": len(new_rows), "total": len(full)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
