# -*- coding: utf-8 -*-
"""
Recipe: fact_fin_counter_verifier  (FINISHING — mirror of fact_counter_verifier)
Inputs : fin_counter_verifier, dim_operator
Output : fact_fin_counter_verifier

Same transform as fact_counter_verifier, for the 2nd-Step / Finishing
Counter Verifier (C1P) leak test.

>>> If your finishing counter-verifier source is named differently, change SRC below.
"""

import dataiku
import pandas as pd

SRC = "fin_counter_verifier"        # <-- finishing counter-verifier source dataset

cv  = dataiku.Dataset(SRC).get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()

cv.columns  = [c.upper() for c in cv.columns]
dim.columns = [c.upper() for c in dim.columns]

def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

op_col = next((c for c in cv.columns
               if c in ("OP_ID", "FINISHING_OPERATOR_ID", "MATRICULE", "OPERATOR_ID")), "OP_ID")
cv["OP_ID"]  = cv[op_col].apply(norm_op_id)
dim["OP_ID"] = dim["OP_ID"].astype(str).str.strip().str.upper()

date_col = next((c for c in cv.columns
                 if "PROD_DATE" in c or "FINISHING_TIMESTAMP" in c
                 or c in ("TEST_DATE", "TEST_DATETIME", "DATE")), None)
if date_col:
    cv["PROD_DATE"]  = pd.to_datetime(cv[date_col], errors="coerce")
    cv["PROD_YEAR"]  = cv["PROD_DATE"].dt.year
    cv["PROD_MONTH"] = cv["PROD_DATE"].dt.month
    cv["PROD_WEEK"]  = cv["PROD_DATE"].dt.isocalendar().week.astype("Int64")
    cv["YEAR"] = cv["PROD_YEAR"]
    cv["WEEK"] = cv["PROD_WEEK"]

result_col = next((c for c in cv.columns
                   if c in ("IS_LEAK", "LEAK", "RESULT", "CV_RESULT", "STATUS")), None)

def to_leak(v):
    if pd.isna(v): return 0
    s = str(v).strip().upper()
    if s in ("1", "Y", "YES", "TRUE", "LEAK", "NOK", "KO", "FAIL"):  return 1
    if s in ("0", "N", "NO", "FALSE", "OK", "PASS"):                 return 0
    try:    return 1 if float(s) > 0 else 0
    except: return 0

cv["IS_LEAK"] = cv[result_col].apply(to_leak) if result_col else 0

type_col = next((c for c in cv.columns
                 if c in ("CV_TYPE", "LEAK_TYPE", "TYPE", "SEVERITY")), None)
def to_type(row):
    if row["IS_LEAK"] == 0:
        return "OK"
    if type_col and pd.notna(row.get(type_col)):
        t = str(row[type_col]).strip()
        return f"Type {t}" if t.isdigit() else t
    return "Leak"
cv["CV_TYPE"] = cv.apply(to_type, axis=1)

if "COUNTER_VERIFIER_ID" not in cv.columns:
    station_col = next((c for c in cv.columns
                        if "VERIFIER" in c or "STATION" in c or "MACHINE" in c), None)
    if station_col:
        cv["COUNTER_VERIFIER_ID"] = cv[station_col]

dim_slim = dim[[
    "OP_ID", "CHORUS_ID", "OPERATOR_NAME", "BU", "CREW",
    "SUPERVISOR_CHORUS_ID", "COST_CENTER", "POSITION", "IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = cv.merge(dim_slim, on="OP_ID", how="left")

print(f"fact_fin_counter_verifier rows: {len(fact):,}")
print(f"  leaks (IS_LEAK=1)   : {int(fact['IS_LEAK'].sum()):,}  "
      f"({fact['IS_LEAK'].mean()*100:.2f}%)")

dataiku.Dataset("fact_fin_counter_verifier").write_with_schema(fact)
