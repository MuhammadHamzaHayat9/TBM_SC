# -*- coding: utf-8 -*-
"""
Recipe: fact_conf_bc
Inputs : conf_bc_grq2, dim_operator, meta_cq_descriptions (TBM6)
Output : fact_conf_bc
         One row per Before-Cure CQ event, enriched with operator + CQ description.

Memory-safe: reads only the 3 columns needed from the raw source, normalises
vectorised (no row-wise .apply), joins the small lookup tables, writes slim.
"""

import dataiku
import pandas as pd

SRC = "conf_bc_grq2"

def norm_op_series(s):
    txt = s.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True).str.zfill(6)
    return txt.where(s.notna(), None)

def cq_str_series(s):
    """Vectorised equivalent of f'{float(x):g}' (e.g. '75.10' -> '75.1', '777.0' -> '777'),
    keeping non-numeric codes as their trimmed string."""
    num = pd.to_numeric(s, errors="coerce")
    txt = (num.astype("string")
              .str.replace(r"(\.\d*?)0+$", r"\1", regex=True)
              .str.replace(r"\.$", "", regex=True))
    raw = s.astype("string").str.strip()
    return txt.where(num.notna(), raw)

# ---- read only the columns we need from the source ----
ds = dataiku.Dataset(SRC)
try:
    orig = [c["name"] for c in ds.read_schema()]
    up = {c.upper(): c for c in orig}
    op_o   = up.get("OP_ID")  or next((up[u] for u in up if u.endswith("OP_ID")), None)
    cq_o   = up.get("CQ_CODE") or next((up[u] for u in up if "CQ" in u and "CODE" in u), None)
    date_o = next((up[u] for u in up if "PROD_DATE" in u or u == "DATE"), None)
    cols = [c for c in [op_o, cq_o, date_o] if c]
    bc = ds.get_dataframe(columns=cols) if cols else ds.get_dataframe()
except Exception:
    bc = ds.get_dataframe()
bc.columns = [c.upper() for c in bc.columns]

op_col   = next((c for c in bc.columns if c.endswith("OP_ID") or c == "OP_ID"), None)
date_col = next((c for c in bc.columns if "PROD_DATE" in c or c == "DATE"), None)
cq_col   = "CQ_CODE" if "CQ_CODE" in bc.columns else next((c for c in bc.columns if "CQ" in c and "CODE" in c), None)
assert op_col and cq_col, f"Required op/cq columns missing in {SRC}: {list(bc.columns)}"

bc["OP_ID"]       = norm_op_series(bc[op_col])
bc["CQ_CODE_STR"] = cq_str_series(bc[cq_col])

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

if date_col:
    fact["PROD_DATE"]  = pd.to_datetime(fact[date_col], errors="coerce")
    fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
    fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
    fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")

keep = ["OP_ID", "OPERATOR_NAME", "BU", "CREW", "CQ_CODE_STR", "CQ_DESCRIPTION",
        "CQ_RELATES_TO", "CQ_TYPE_TIER", "PROD_DATE", "PROD_YEAR", "PROD_MONTH", "PROD_WEEK"]
fact = fact[[c for c in keep if c in fact.columns]]

print(f"fact_conf_bc rows: {len(fact):,}")
dataiku.Dataset("fact_conf_bc").write_with_schema(fact)
