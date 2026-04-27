# -*- coding: utf-8 -*-
"""
Recipe: fact_nc_scrap
Inputs : nc_scrap, dim_operator
Output : fact_nc_scrap
"""

import dataiku
import pandas as pd

nc  = dataiku.Dataset("nc_scrap").get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()

nc.columns  = [c.upper() for c in nc.columns]
dim.columns = [c.upper() for c in dim.columns]

def to_op_id(x):
    if pd.isna(x): return None
    s = str(x).strip()
    try:    return str(int(float(s))).zfill(6)
    except: return s.zfill(6)

nc["OP_ID"]  = nc["OP_ID"].apply(to_op_id)
dim["OP_ID"] = dim["OP_ID"].astype(str).str.strip().str.upper()

dim_slim = dim[[
    "OP_ID","CHORUS_ID","OPERATOR_NAME","BU","CREW",
    "SUPERVISOR_CHORUS_ID","COST_CENTER","POSITION","IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = nc.merge(dim_slim, on="OP_ID", how="left")

fact["PROD_DATE"]  = pd.to_datetime(fact["PROD_DATE"], errors="coerce")
fact["PROD_YEAR"]  = fact["PROD_DATE"].dt.year
fact["PROD_MONTH"] = fact["PROD_DATE"].dt.month
fact["PROD_WEEK"]  = fact["PROD_DATE"].dt.isocalendar().week.astype("Int64")

print(f"fact_nc_scrap rows: {len(fact):,}")
dataiku.Dataset("fact_nc_scrap").write_with_schema(fact)
