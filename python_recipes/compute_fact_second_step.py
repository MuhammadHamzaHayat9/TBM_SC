# -*- coding: utf-8 -*-
"""
Recipe: fact_second_step   (FINISHING / 2nd Step — mirror of fact_first_step)
Inputs : second_step_prod, dim_operator
Output : fact_second_step
         One row per operator/day/TBM with TIRES_BUILT and operator info.

The tires-built column in second_step_prod is auto-detected (TIRES_BUILT /
TIRES / TOTAL_TIRES / 2ND_STEP_TIRES). Adjust TIRES_COL below if needed.
"""

import dataiku
import pandas as pd

SRC = "second_step_prod"

prod = dataiku.Dataset(SRC).get_dataframe()
dim  = dataiku.Dataset("dim_operator").get_dataframe()
prod.columns = [c.upper() for c in prod.columns]
dim.columns  = [c.upper() for c in dim.columns]

def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

op_col = next((c for c in prod.columns if c == "OP_ID" or c.endswith("OP_ID")), "OP_ID")
prod["OP_ID"] = prod[op_col].apply(norm_op_id)
dim["OP_ID"]  = dim["OP_ID"].astype(str).str.strip().str.upper()

# tires column
TIRES_COL = next((c for c in ["TIRES_BUILT", "TIRES", "TOTAL_TIRES", "2ND_STEP_TIRES", "SECOND_STEP_TIRES"]
                  if c in prod.columns), None)
if TIRES_COL and TIRES_COL != "TIRES_BUILT":
    prod = prod.rename(columns={TIRES_COL: "TIRES_BUILT"})
elif TIRES_COL is None:
    raise ValueError(f"No tires column found in {SRC}; columns = {list(prod.columns)}")

dim_slim = dim[[
    "OP_ID", "CHORUS_ID", "OPERATOR_NAME", "BU", "CREW",
    "SUPERVISOR_CHORUS_ID", "COST_CENTER", "POSITION", "IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = prod.merge(dim_slim, on="OP_ID", how="left")

date_col = next((c for c in fact.columns if "PROD_DATE" in c or c == "DATE"), "PROD_DATE")
fact["PROD_DATE"]  = pd.to_datetime(fact[date_col], errors="coerce")
fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")

MIN_PROD_DATE = "2026-05-01"   # only keep production on/after this date (set None to disable)
if MIN_PROD_DATE:
    fact = fact[fact["PROD_DATE"] >= pd.Timestamp(MIN_PROD_DATE)]

print(f"fact_second_step rows: {len(fact):,}   tires: {fact['TIRES_BUILT'].sum():,.0f}")
dataiku.Dataset("fact_second_step").write_with_schema(fact)
