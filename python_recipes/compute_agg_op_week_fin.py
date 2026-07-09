# -*- coding: utf-8 -*-
"""
Recipe: agg_op_week_fin   (2nd-Step / Finishing — operator x week building blocks)
Inputs : fact_second_step, fact_conf_bc, fact_conf_ac, fact_nc_scrap, fact_uniformity
Output : agg_op_week_fin

Same shape as agg_op_week but for the Finishing step:
  - TIRES_BUILT / SHIFTS      : from fact_second_step
  - BC_COUNT / AC_COUNT       : Finishing-related CQs (CQ_RELATES_TO='Finishing')
  - UNI_TESTED / UNI_RFT      : uniformity keyed on FINISHING_OPERATOR_ID,
                                dated by FINISHING_TIMESTAMP
Memory-safe: reads only the columns it needs.
"""

import dataiku
import pandas as pd

RELATES = "Finishing"
KEYS = ["PROD_YEAR", "PROD_WEEK"]

def read(name, cols):
    ds = dataiku.Dataset(name)
    try:
        df = ds.get_dataframe(columns=cols)
    except Exception:
        df = ds.get_dataframe()
        want = {c.upper() for c in cols}
        df = df[[c for c in df.columns if c.upper() in want]]
    df.columns = [c.upper() for c in df.columns]
    return df

def norm_ids(s):
    txt = s.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True).str.zfill(6)
    return txt.where(s.notna(), None)

prod  = read("fact_second_step", ["OP_ID", "OPERATOR_NAME", "BU", "CREW", "PROD_DATE",
                                  "PROD_YEAR", "PROD_WEEK", "TIRES_BUILT"])
bc    = read("fact_conf_bc", ["OP_ID", "CQ_CODE_STR", "CQ_RELATES_TO", "PROD_YEAR", "PROD_WEEK"])
ac    = read("fact_conf_ac", ["OP_ID", "CQ_CODE_STR", "CQ_RELATES_TO", "PROD_YEAR", "PROD_WEEK"])
scrap = read("fact_nc_scrap", ["OP_ID", "OP_SCRAP_LBS_BY_TIRES", "PROD_YEAR", "PROD_WEEK"])
uni   = read("fact_uniformity", ["FINISHING_OPERATOR_ID", "BARCODE", "IS_RFT", "PROD_YEAR", "PROD_WEEK"])

for df in (prod, bc, ac, scrap):
    if "OP_ID" in df.columns:
        df["OP_ID"] = norm_ids(df["OP_ID"])

def relates(df):
    if "CQ_RELATES_TO" in df.columns:
        df = df[df["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == RELATES.casefold()]
    return df
# Before-Cure = Finishing-related only; After-Cure = ALL after-cure CQs
# (no AC is tagged 'Finishing', so 2nd step counts every AC CQ by request).
bc = relates(bc)

# Operator identity (constant per operator) — re-attached after the merge so
# rows that exist only in a uniformity test-week still get BU / Crew / name.
ident = (prod.dropna(subset=["OPERATOR_NAME"])
             [["OP_ID", "OPERATOR_NAME", "BU", "CREW"]].drop_duplicates("OP_ID"))

prod_agg = (prod.groupby(["OP_ID"] + KEYS, dropna=False)
                .agg(TIRES_BUILT=("TIRES_BUILT", "sum"), SHIFTS=("PROD_DATE", "nunique")).reset_index())
bc_agg = bc.dropna(subset=["CQ_CODE_STR"]).groupby(["OP_ID"] + KEYS, dropna=False).size().reset_index(name="BC_COUNT")
ac_agg = ac.dropna(subset=["CQ_CODE_STR"]).groupby(["OP_ID"] + KEYS, dropna=False).size().reset_index(name="AC_COUNT")
scrap_agg = (scrap.groupby(["OP_ID"] + KEYS, dropna=False)
                  .agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum")).reset_index())

# Uniformity attributed to the FINISHING operator, dated by TEST week
# (fact_uniformity's PROD_YEAR/PROD_WEEK are now the test-date week).
uni["OP_ID"] = norm_ids(uni["FINISHING_OPERATOR_ID"])
uni["IS_RFT"] = pd.to_numeric(uni.get("IS_RFT"), errors="coerce").fillna(0)
per_tire = uni.groupby(["OP_ID"] + KEYS + ["BARCODE"], dropna=False)["IS_RFT"].max().reset_index()
uni_agg = (per_tire.groupby(["OP_ID"] + KEYS, dropna=False)
                   .agg(UNI_TESTED=("BARCODE", "nunique"), UNI_RFT=("IS_RFT", "sum")).reset_index())

# OUTER-merge so a uniformity test-week (tire built earlier) still appears; then
# attach the operator identity by OP_ID.
from functools import reduce
agg = reduce(lambda l, r: l.merge(r, on=["OP_ID"] + KEYS, how="outer"),
             [prod_agg, bc_agg, ac_agg, scrap_agg, uni_agg])
agg = agg.merge(ident, on="OP_ID", how="left")
for c in ["TIRES_BUILT", "SHIFTS", "BC_COUNT", "AC_COUNT", "SCRAP_LBS", "UNI_TESTED", "UNI_RFT"]:
    agg[c] = agg[c].fillna(0)

print(f"agg_op_week_fin rows: {len(agg):,}   tires: {agg['TIRES_BUILT'].sum():,.0f}")
dataiku.Dataset("agg_op_week_fin").write_with_schema(agg)
