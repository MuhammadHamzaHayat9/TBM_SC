# -*- coding: utf-8 -*-
"""
Recipe: agg_uniformity_fin   (2nd-Step / Finishing uniformity RFT)
Inputs : uniformity_breakdown, dim_operator
Output : agg_uniformity_fin
         Same shape as agg_uniformity (BU x CREW x WEEK: TIRES_TESTED,
         RFT_COUNT, REPAIR_COUNT, RFT_PCT, REPAIR_PCT), but attributed to the
         FINISHING operator (FINISHING_OPERATOR_ID) and dated by when the tire
         was finished (FINISHING_TIMESTAMP).
"""

import dataiku
import pandas as pd

uni = dataiku.Dataset("uniformity_breakdown").get_dataframe()
dim = dataiku.Dataset("dim_operator").get_dataframe()
uni.columns = [c.upper() for c in uni.columns]
dim.columns = [c.upper() for c in dim.columns]

def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

op_col = "FINISHING_OPERATOR_ID" if "FINISHING_OPERATOR_ID" in uni.columns else "CONFECTION_OPERATOR_ID"
uni["OP_ID"] = uni[op_col].apply(norm_op_id)
dim["OP_ID"] = dim["OP_ID"].astype(str).str.strip().str.upper()

# One row per barcode (drop uniformity re-tests)
if {"BARCODE", "TEST_DATETIME"}.issubset(uni.columns):
    uni = uni.sort_values(["BARCODE", "TEST_DATETIME"]).drop_duplicates("BARCODE", keep="first")

# RFT / repair flags
grade_col = "OGU2_GRADE" if "OGU2_GRADE" in uni.columns else ("UNI_GRADE" if "UNI_GRADE" in uni.columns else None)
uni["IS_RFT"]    = ((uni.get("RUN_TYPE") == "N") & (uni[grade_col].isna())).astype(int) if grade_col else 0
uni["IS_REPAIR"] = uni["UNI_REPAIR"].notna().astype(int) if "UNI_REPAIR" in uni.columns else 0

# Date parts from finishing timestamp
ts = "FINISHING_TIMESTAMP" if "FINISHING_TIMESTAMP" in uni.columns else "CONFECTION_TIMESTAMP"
uni[ts] = pd.to_datetime(uni[ts], errors="coerce")
uni["PROD_YEAR"] = uni[ts].dt.year
uni["PROD_WEEK"] = uni[ts].dt.isocalendar().week.astype("Int64")

dim_slim = dim[["OP_ID", "BU", "CREW"]].drop_duplicates("OP_ID")
uni = uni.merge(dim_slim, on="OP_ID", how="left")

agg = (uni.groupby(["BU", "CREW", "PROD_YEAR", "PROD_WEEK"], dropna=False)
          .agg(TIRES_TESTED=("BARCODE", "nunique"),
               RFT_COUNT=("IS_RFT", "sum"),
               REPAIR_COUNT=("IS_REPAIR", "sum"))
          .reset_index())
_den = agg["TIRES_TESTED"].replace(0, float("nan"))
agg["RFT_PCT"]    = (agg["RFT_COUNT"]    / _den * 100).round(3)
agg["REPAIR_PCT"] = (agg["REPAIR_COUNT"] / _den * 100).round(3)

print(f"agg_uniformity_fin rows: {len(agg):,}")
dataiku.Dataset("agg_uniformity_fin").write_with_schema(agg)
