# -*- coding: utf-8 -*-
"""
Recipe: fact_fin_ac   (FINISHING / 2nd Step — mirror of fact_conf_ac)
Inputs : fin_ac_grq2, dim_operator, meta_cq_descriptions (TBM6)
Output : fact_fin_ac
         One row per 2nd-Step After-Cure CQ event, enriched with operator + CQ description.

>>> If your finishing after-cure source is named differently, change SRC below.
"""

import dataiku
import pandas as pd

SRC = "fin_ac_grq2"        # <-- finishing after-cure CQ source dataset

ac  = dataiku.Dataset(SRC).get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()
try:
    cq = dataiku.Dataset("meta_cq_descriptions").get_dataframe()
except Exception:
    cq = dataiku.Dataset("TBM6").get_dataframe()

ac.columns  = [c.upper() for c in ac.columns]
dim.columns = [c.upper() for c in dim.columns]
cq.columns  = [c.upper() for c in cq.columns]

op_col   = next((c for c in ac.columns if c.endswith("OP_ID") or c == "OP_ID"), None)
date_col = next((c for c in ac.columns if "PROD_DATE" in c or c == "DATE"), None)
cq_col   = "CQ_CODE" if "CQ_CODE" in ac.columns else next((c for c in ac.columns if "CQ" in c and "CODE" in c), None)
assert op_col and date_col and cq_col, "Required columns missing"

def to_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

def to_cq_str(x):
    if pd.isna(x): return None
    s = str(x).strip()
    try:    return f"{float(s):g}"
    except: return s

ac["OP_ID"]       = ac[op_col].apply(to_op_id)
ac["CQ_CODE_STR"] = ac[cq_col].apply(to_cq_str)
dim["OP_ID"]      = dim["OP_ID"].astype(str).str.strip().str.upper()
cq["CQ_STR"]      = cq["CQ"].apply(to_cq_str)

dim_slim = dim[[
    "OP_ID","CHORUS_ID","OPERATOR_NAME","BU","CREW",
    "SUPERVISOR_CHORUS_ID","COST_CENTER","POSITION","IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

cq_slim = cq[["CQ_STR","CQ_CODE_DESCRIPTION","RELATES TO","TYPES"]] \
           .rename(columns={
               "CQ_CODE_DESCRIPTION": "CQ_DESCRIPTION",
               "RELATES TO":          "CQ_RELATES_TO",
               "TYPES":               "CQ_TYPE_TIER",
           }).drop_duplicates(subset=["CQ_STR"])

fact = ac.merge(dim_slim, on="OP_ID", how="left")
fact = fact.merge(cq_slim, left_on="CQ_CODE_STR", right_on="CQ_STR", how="left")
fact = fact.drop(columns=["CQ_STR"], errors="ignore")

fact[date_col]     = pd.to_datetime(fact[date_col], errors="coerce")
fact["PROD_DATE"]  = fact[date_col]
fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")

print(f"fact_fin_ac rows: {len(fact):,}")
dataiku.Dataset("fact_fin_ac").write_with_schema(fact)
