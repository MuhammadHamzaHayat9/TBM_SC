# -*- coding: utf-8 -*-
"""
Recipe: fact_second_step   (FINISHING / 2nd Step — mirror of fact_first_step)
Inputs : second_step_prod, dim_operator
Output : fact_second_step
         One row per operator/day/TBM with TIRES_BUILT and operator info.

>>> If your 2nd-step production dataset is named differently, change SRC below.
"""

import dataiku
import pandas as pd

SRC = "second_step_prod"        # <-- 2nd-step production source dataset

prod = dataiku.Dataset(SRC).get_dataframe()
dim  = dataiku.Dataset("dim_operator").get_dataframe()

prod.columns = [c.upper() for c in prod.columns]
dim.columns  = [c.upper() for c in dim.columns]

def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

prod["OP_ID"] = prod["OP_ID"].apply(norm_op_id)
dim["OP_ID"]  = dim["OP_ID"].astype(str).str.strip().str.upper()

dim_slim = dim[[
    "OP_ID","CHORUS_ID","OPERATOR_NAME","BU","CREW",
    "SUPERVISOR_CHORUS_ID","COST_CENTER","POSITION","IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = prod.merge(dim_slim, on="OP_ID", how="left")

fact["PROD_DATE"]  = pd.to_datetime(fact["PROD_DATE"], errors="coerce")
fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")
fact["PROD_DOW"]   = fact["PROD_DATE"].dt.dayofweek

print(f"fact_second_step rows: {len(fact):,}")
print(f"  with operator info: {fact['OPERATOR_NAME'].notna().sum():,}")

dataiku.Dataset("fact_second_step").write_with_schema(fact)
