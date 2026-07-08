# -*- coding: utf-8 -*-
"""
Recipe: fact_counter_verifier
Inputs : counter_verifier (raw end-of-line Counter Verifier / C1P leak test),
         dim_operator
Output : fact_counter_verifier
         One row per verified tire, joined to the operator who BUILT it.

The Counter Verifier is the "C1P" (1st-Pass / Before-Cure) leak check in the
Power BI model (tables "Before Cure C1P" / "Confection Before Cure C1P").
Each tested tire is either OK (no leak) or leaks with a severity Type (1/2/3).

Adds:
  - IS_LEAK  = 1 if the tire leaked (not OK)
  - CV_TYPE  = "OK" / "Type 1" / "Type 2" / "Type 3"
  - PROD_DATE / WEEK / MONTH / YEAR derived from the build timestamp
"""

import dataiku
import pandas as pd

cv  = dataiku.Dataset("counter_verifier").get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()

cv.columns  = [c.upper() for c in cv.columns]
dim.columns = [c.upper() for c in dim.columns]

# ---------- Normalize OP_ID ----------
def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

# Operator who built the tire may arrive under a few different names
op_col = next((c for c in cv.columns
               if c in ("OP_ID", "CONFECTION_OPERATOR_ID", "MATRICULE", "OPERATOR_ID")), "OP_ID")
cv["OP_ID"]  = cv[op_col].apply(norm_op_id)
dim["OP_ID"] = dim["OP_ID"].astype(str).str.strip().str.upper()

# ---------- Build timestamp / date parts ----------
date_col = next((c for c in cv.columns
                 if "PROD_DATE" in c or "CONFECTION_TIMESTAMP" in c
                 or c in ("TEST_DATE", "TEST_DATETIME", "DATE")), None)
if date_col:
    cv["PROD_DATE"]  = pd.to_datetime(cv[date_col], errors="coerce")
    cv["PROD_YEAR"]  = cv["PROD_DATE"].dt.year
    cv["PROD_MONTH"] = cv["PROD_DATE"].dt.month
    cv["PROD_WEEK"]  = cv["PROD_DATE"].dt.isocalendar().week.astype("Int64")
    # legacy YEAR / WEEK aliases (kept for backward compatibility with older webapp)
    cv["YEAR"] = cv["PROD_YEAR"]
    cv["WEEK"] = cv["PROD_WEEK"]

# ---------- Leak flag + severity type ----------
# Prefer an explicit result / leak column if present, otherwise derive from Type.
result_col = next((c for c in cv.columns
                   if c in ("IS_LEAK", "LEAK", "RESULT", "CV_RESULT", "STATUS")), None)

def to_leak(v):
    if pd.isna(v): return 0
    s = str(v).strip().upper()
    if s in ("1", "Y", "YES", "TRUE", "LEAK", "NOK", "KO", "FAIL"):  return 1
    if s in ("0", "N", "NO", "FALSE", "OK", "PASS"):                 return 0
    # numeric leak type > 0 means a leak
    try:    return 1 if float(s) > 0 else 0
    except: return 0

if result_col:
    cv["IS_LEAK"] = cv[result_col].apply(to_leak)
else:
    cv["IS_LEAK"] = 0

# Severity type (Type 1/2/3) if the source carries it
type_col = next((c for c in cv.columns
                 if c in ("CV_TYPE", "LEAK_TYPE", "TYPE", "SEVERITY")), None)
def to_type(row):
    if row["IS_LEAK"] == 0:
        return "OK"
    if type_col and pd.notna(row.get(type_col)):
        t = str(row[type_col]).strip()
        # normalise "1" -> "Type 1"
        return f"Type {t}" if t.isdigit() else t
    return "Leak"
cv["CV_TYPE"] = cv.apply(to_type, axis=1)

# Counter Verifier station id (which machine flagged the leak)
if "COUNTER_VERIFIER_ID" not in cv.columns:
    station_col = next((c for c in cv.columns
                        if "VERIFIER" in c or "STATION" in c or "MACHINE" in c), None)
    if station_col:
        cv["COUNTER_VERIFIER_ID"] = cv[station_col]

# ---------- Join operator info ----------
dim_slim = dim[[
    "OP_ID", "CHORUS_ID", "OPERATOR_NAME", "BU", "CREW",
    "SUPERVISOR_CHORUS_ID", "COST_CENTER", "POSITION", "IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = cv.merge(dim_slim, on="OP_ID", how="left")

# ---------- Diagnostics ----------
print(f"fact_counter_verifier rows: {len(fact):,}")
print(f"  leaks (IS_LEAK=1)   : {int(fact['IS_LEAK'].sum()):,}  "
      f"({fact['IS_LEAK'].mean()*100:.2f}%)")
print(f"  matched to operator : {fact['OPERATOR_NAME'].notna().sum():,}")
print("\nCV_TYPE breakdown:")
print(fact["CV_TYPE"].value_counts(dropna=False).head(10).to_string())

dataiku.Dataset("fact_counter_verifier").write_with_schema(fact)
