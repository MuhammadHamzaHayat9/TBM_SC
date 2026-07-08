# -*- coding: utf-8 -*-
"""
Recipe: fact_uniformity_fin   (FINISHING view of uniformity)
Inputs : uniformity_breakdown, dim_operator
Output : fact_uniformity_fin

Same uniformity source as fact_uniformity, but attributed to the operator
who FINISHED the tire (FINISHING_OPERATOR_ID) and dated by when it was
finished (FINISHING_TIMESTAMP) — this is the "Dist_OP_ID_Fin" view in the
Power BI model. Confection uses fact_uniformity (CONFECTION_OPERATOR_ID).
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

# Key on the FINISHING operator (fall back to confection if absent)
fin_op_col = "FINISHING_OPERATOR_ID" if "FINISHING_OPERATOR_ID" in uni.columns else "CONFECTION_OPERATOR_ID"
uni["OP_ID"]  = uni[fin_op_col].apply(norm_op_id)
dim["OP_ID"]  = dim["OP_ID"].astype(str).str.strip().str.upper()

keep = [
    "OP_ID", "BARCODE", "GREENTIRE", "CAI", "TUO", "VENTILATION", "RUN_TYPE",
    "OGU2_GRADE", "UNI_REPAIR", "CQ_CODE", "TEST_DATETIME",
    "CONFECTION_TIMESTAMP", "CONFECTION_MACHINE",
    "FINISHING_TIMESTAMP", "FINISHING_MACHINE", "FINISHING_OPERATOR_ID",
    "CURING_TIMESTAMP", "CURING_PRESS", "CURING_OPERATOR_ID", "MOULD",
]
uni = uni[[c for c in keep if c in uni.columns]].copy()

uni = uni.rename(columns={
    "FINISHING_MACHINE":    "TBM",
    "OGU2_GRADE":           "UNI_GRADE",
    "TEST_DATETIME":        "TEST_DATE",
    "CQ_CODE":              "CQ_CODE_STR",
})

uni["IS_RFT"]      = ((uni["RUN_TYPE"] == "N") & (uni["UNI_GRADE"].isna())).astype(int)
uni["IS_REPAIRED"] = uni["UNI_REPAIR"].notna().astype(int)

# Derive date parts from when the tire was FINISHED
fin_ts = "FINISHING_TIMESTAMP" if "FINISHING_TIMESTAMP" in uni.columns else "CONFECTION_TIMESTAMP"
uni[fin_ts]       = pd.to_datetime(uni[fin_ts], errors="coerce")
uni["PROD_DATE"]  = uni[fin_ts].dt.normalize()
uni["PROD_YEAR"]  = uni[fin_ts].dt.year
uni["PROD_MONTH"] = uni[fin_ts].dt.month
uni["PROD_WEEK"]  = uni[fin_ts].dt.isocalendar().week.astype("Int64")

dim_slim = dim[[
    "OP_ID","CHORUS_ID","OPERATOR_NAME","BU","CREW",
    "SUPERVISOR_CHORUS_ID","COST_CENTER","POSITION","IS_ACTIVE",
]].drop_duplicates(subset=["OP_ID"])

fact = uni.merge(dim_slim, on="OP_ID", how="left")

print(f"fact_uniformity_fin rows: {len(fact):,}")
print(f"  unique tires (BARCODE)      : {fact['BARCODE'].nunique():,}")
print(f"  Right-First-Time (IS_RFT=1) : {fact['IS_RFT'].sum():,}  ({fact['IS_RFT'].mean()*100:.1f}%)")

dataiku.Dataset("fact_uniformity_fin").write_with_schema(fact)
