# -*- coding: utf-8 -*-
"""
Recipe: fact_conf_bc
Inputs : conf_bc_grq2, dim_operator, meta_cq_descriptions (TBM6)
Output : fact_conf_bc
         One row per Before-Cure CQ event, enriched with operator + CQ description.

Same memory-safe pattern as fact_conf_ac: chunked read of only the 3 needed
columns, vectorised normalisation, keep only CQ-event rows, join small lookups.
"""

import dataiku
import pandas as pd

SRC = "conf_bc_grq2"
CHUNK = 200_000
MIN_PROD_DATE = "2026-05-01"   # only keep events on/after this date (set None to disable)

def norm_op_series(s):
    txt = s.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True).str.zfill(6)
    return txt.where(s.notna(), None)

def cq_str_series(s):
    """Vectorised f'{float(x):g}' ('75.10'->'75.1', '777.0'->'777'); non-numeric kept as-is."""
    num = pd.to_numeric(s, errors="coerce")
    txt = (num.astype("string")
              .str.replace(r"(\.\d*?)0+$", r"\1", regex=True)
              .str.replace(r"\.$", "", regex=True))
    raw = s.astype("string").str.strip()
    return txt.where(num.notna(), raw)

ds = dataiku.Dataset(SRC)

# Detect which source columns to read (operator id, CQ code, date).
try:
    up = {c["name"].upper(): c["name"] for c in ds.read_schema()}
    op_o   = up.get("OP_ID")  or next((up[u] for u in up if u.endswith("OP_ID")), None)
    cq_o   = up.get("CQ_CODE") or next((up[u] for u in up if "CQ" in u and "CODE" in u), None)
    date_o = next((up[u] for u in up if "PROD_DATE" in u or u == "DATE"), None)
    read_cols = [c for c in [op_o, cq_o, date_o] if c] or None
except Exception:
    read_cols = None

def process_chunk(df):
    df.columns = [c.upper() for c in df.columns]
    opc = next((c for c in df.columns if c.endswith("OP_ID") or c == "OP_ID"), None)
    cqc = "CQ_CODE" if "CQ_CODE" in df.columns else next((c for c in df.columns if "CQ" in c and "CODE" in c), None)
    dtc = next((c for c in df.columns if "PROD_DATE" in c or c == "DATE"), None)
    out = pd.DataFrame({"OP_ID": norm_op_series(df[opc]),
                        "CQ_CODE_STR": cq_str_series(df[cqc])})
    if dtc:
        out["PROD_DATE"] = pd.to_datetime(df[dtc], errors="coerce").values
    out = out[out["CQ_CODE_STR"].notna()]    # keep only CQ events
    if MIN_PROD_DATE and "PROD_DATE" in out.columns:
        out = out[out["PROD_DATE"] >= pd.Timestamp(MIN_PROD_DATE)]
    return out

def read_chunks(use_cols):
    collected = []
    it = (ds.iter_dataframes(chunksize=CHUNK, columns=use_cols) if use_cols
          else ds.iter_dataframes(chunksize=CHUNK))
    for chunk in it:
        collected.append(process_chunk(chunk))
    return collected

# Prefer the column-projected read; if projection breaks the stream for this
# dataset (some connectors raise TypeError/IndexError), fall back to reading
# every column per chunk — chunking still bounds memory and process_chunk picks
# the columns it needs.
try:
    parts = read_chunks(read_cols)
except Exception as e:
    print(f"[info] column-projected chunk read failed ({e}); retrying without projection")
    parts = read_chunks(None)
bc = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["OP_ID", "CQ_CODE_STR"])
del parts

# ---- small lookup tables ----
dim = dataiku.Dataset("dim_operator").get_dataframe()
dim.columns = [c.upper() for c in dim.columns]
dim["OP_ID"] = dim["OP_ID"].astype(str).str.strip().str.upper()
dim_slim = dim[["OP_ID", "OPERATOR_NAME", "BU", "CREW"]].drop_duplicates("OP_ID")

try:
    cq = dataiku.Dataset("meta_cq_descriptions").get_dataframe()
except Exception:
    cq = dataiku.Dataset("TBM6").get_dataframe()
cq.columns = [c.upper() for c in cq.columns]
cq["CQ_STR"] = cq_str_series(cq["CQ"])
cq_slim = (cq[["CQ_STR", "CQ_CODE_DESCRIPTION", "RELATES TO", "TYPES"]]
           .rename(columns={"CQ_CODE_DESCRIPTION": "CQ_DESCRIPTION",
                            "RELATES TO": "CQ_RELATES_TO", "TYPES": "CQ_TYPE_TIER"})
           .drop_duplicates("CQ_STR"))

fact = (bc.merge(dim_slim, on="OP_ID", how="left")
          .merge(cq_slim, left_on="CQ_CODE_STR", right_on="CQ_STR", how="left")
          .drop(columns=["CQ_STR"], errors="ignore"))

if "PROD_DATE" in fact.columns:
    fact["PROD_DATE"]  = pd.to_datetime(fact["PROD_DATE"], errors="coerce")
    fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
    fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
    fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")

keep = ["OP_ID", "OPERATOR_NAME", "BU", "CREW", "CQ_CODE_STR", "CQ_DESCRIPTION",
        "CQ_RELATES_TO", "CQ_TYPE_TIER", "PROD_DATE", "PROD_YEAR", "PROD_MONTH", "PROD_WEEK"]
fact = fact[[c for c in keep if c in fact.columns]]

print(f"fact_conf_bc rows (CQ events): {len(fact):,}")
dataiku.Dataset("fact_conf_bc").write_with_schema(fact)
