# -*- coding: utf-8 -*-
"""
Recipe: dim_operator
Inputs : view_employee, BU_data
Output : dim_operator
         One row per operator with HR info + BU/Crew assignment.
"""

import dataiku
import pandas as pd

emp = dataiku.Dataset("view_employee").get_dataframe()
bu  = dataiku.Dataset("BU_data").get_dataframe()

emp.columns = [c.upper() for c in emp.columns]
bu.columns  = [c.upper() for c in bu.columns]

# Normalize OP_ID
def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

emp["OP_ID"] = emp["OP_ID"].apply(norm_op_id)
bu["OP_ID"]  = bu["OP_ID"].apply(norm_op_id)

dim = emp.merge(bu, on="OP_ID", how="left")

print(f"dim_operator rows: {len(dim):,}")
print(f"  with BU info  : {dim['BU'].notna().sum():,}")

dataiku.Dataset("dim_operator").write_with_schema(dim)
