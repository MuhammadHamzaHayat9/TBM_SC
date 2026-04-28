# -*- coding: utf-8 -*-
"""
Recipe: fact_uniformity
Inputs : uniformity_breakdown, dim_operator
Output : fact_uniformity

One row per tire uniformity test, joined to the operator who BUILT
the tire (CONFECTION_OPERATOR_ID -> OP_ID).

Adds:
  - IS_RFT      = 1 if tire passed first time (RUN_TYPE='N' AND no defect)
  - IS_REPAIRED = 1 if tire needed a repair
  - PROD_DATE / WEEK / MONTH / YEAR derived from CONFECTION_TIMESTAMP
"""

import dataiku
import pandas as pd

uni = dataiku.Dataset("uniformity_breakdown").get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()

uni.columns = [c.upper() for c in uni.columns]
dim.columns = [c.upper() for c in dim.columns]

# ---------- Normalize OP_ID ----------
def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

uni["OP_ID"]  = uni["CONFECTION_OPERATOR_ID"].apply(norm_op_id)
dim["OP_ID"]  = dim["OP_ID"].astype(str).str.strip().str.upper()

# ---------- Slim down: keep only useful columns ----------
keep = [
    "OP_ID",
    "BARCODE",
    "GREENTIRE",
    "CAI",
    "TUO",                       # test machine
    "VENTILATION",
    "RUN_TYPE",                  # N=normal, A=after repair, etc.
    "OGU2_GRADE",                # defect category (NULL = passed)
    "UNI_REPAIR",                # repair code (NULL = no repair)
    "CQ_CODE",
    "TEST_DATETIME",
    "CONFECTION_TIMESTAMP",
    "CONFECTION_MACHINE",
    "FINISHING_TIMESTAMP",
    "FINISHING_MACHINE",
    "FINISHING_OPERATOR_ID",
    "CURING_TIMESTAMP",
    "CURING_PRESS",
    "CURING_OPERATOR_ID",
    "MOULD",
]
uni = uni[[c for c in keep if c in uni.columns]].copy()

# ---------- Rename for consistency with rest of the flow ----------
uni = uni.rename(columns={
    "CONFECTION_MACHINE":   "TBM",
    "OGU2_GRADE":           "UNI_GRADE",
    "TEST_DATETIME":        "TEST_DATE",
    "CQ_CODE":              "CQ_CODE_STR",
})

# ---------- Derived flags ----------
uni["IS_RFT"]      = ((uni["RUN_TYPE"] == "N") & (uni["UNI_GRADE"].isna())).astype(int)
uni["IS_REPAIRED"] = uni["UNI_REPAIR"].notna().astype(int)

# ---------- Derive PROD_DATE / YEAR / MONTH / WEEK from when tire was BUILT ----------
uni["CONFECTION_TIMESTAMP"] = pd.to_datetime(uni["CONFECTION_TIMESTAMP"], errors="coerce")
uni["PROD_DATE"]  = uni["CONFECTION_TIMESTAMP"].dt.normalize()
uni["PROD_YEAR"]  = uni["CONFECTION_TIMESTAMP"].dt.year
uni["PROD_MONTH"] = uni["CONFECTION_TIMESTAMP"].dt.month
uni["PROD_WEEK"]  = uni["CONFECTION_TIMESTAMP"].dt.isocalendar().week.astype("Int64")

# ---------- Join operator info ----------
dim_slim = dim[[
    "OP_ID","CHORUS_ID","OPERATOR_NAME","BU","CREW",
    "SUPERVISOR_CHORUS_ID","COST_CENTER","POSITION","IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = uni.merge(dim_slim, on="OP_ID", how="left")

# ---------- Diagnostics ----------
print(f"fact_uniformity rows: {len(fact):,}")
print(f"  unique tires (BARCODE)        : {fact['BARCODE'].nunique():,}")
print(f"  matched to operator           : {fact['OPERATOR_NAME'].notna().sum():,}")
print(f"  matched to BU                 : {fact['BU'].notna().sum():,}")
print(f"  Right-First-Time (IS_RFT=1)   : {fact['IS_RFT'].sum():,}  ({fact['IS_RFT'].mean()*100:.1f}%)")
print(f"  Repaired (IS_REPAIRED=1)      : {fact['IS_REPAIRED'].sum():,}  ({fact['IS_REPAIRED'].mean()*100:.1f}%)")
print(f"  PROD_DATE range               : {fact['PROD_DATE'].min()}  ->  {fact['PROD_DATE'].max()}")

print("\nTop UNI_GRADE (defect category):")
print(fact["UNI_GRADE"].value_counts(dropna=False).head(10).to_string())

print("\nRows per BU:")
print(fact["BU"].value_counts(dropna=False).head(10).to_string())

dataiku.Dataset("fact_uniformity").write_with_schema(fact)
