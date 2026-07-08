# -*- coding: utf-8 -*-
"""
Recipe: agg_top_performers_fin   (2nd-Step / Finishing operator leaderboard)
Inputs : fact_second_step, fact_conf_bc, fact_conf_ac, fact_nc_scrap,
         uniformity_breakdown, dim_operator
Output : agg_top_performers_fin   (same columns the webapp reads from
         agg_top_performers)

- TIRES_BUILT / SHIFTS_WORKED : from fact_second_step (2nd-step production)
- UNI_TESTED / UNI_RFT / RFT_PCT : uniformity keyed on FINISHING_OPERATOR_ID
- BC_COUNT / AC_COUNT : the Before/After-Cure CQs whose CQ_RELATES_TO = 'Finishing'
- SCRAP_LBS : from fact_nc_scrap
- QUALITY_SCORE / RANK : normalised composite (lower = better), like the 1st-step recipe
"""

import dataiku
import pandas as pd

prod  = dataiku.Dataset("fact_second_step").get_dataframe()
bc    = dataiku.Dataset("fact_conf_bc").get_dataframe()
ac    = dataiku.Dataset("fact_conf_ac").get_dataframe()
scrap = dataiku.Dataset("fact_nc_scrap").get_dataframe()
uni   = dataiku.Dataset("uniformity_breakdown").get_dataframe()
for df in (prod, bc, ac, scrap, uni):
    df.columns = [c.upper() for c in df.columns]

def norm(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

for df in (prod, bc, ac, scrap):
    df["OP_ID"] = df["OP_ID"].apply(norm)

# Only Finishing-related CQs
if "CQ_RELATES_TO" in bc.columns:
    bc = bc[bc["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == "finishing"]
if "CQ_RELATES_TO" in ac.columns:
    ac = ac[ac["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == "finishing"]

op_base = (prod.groupby(["OP_ID", "OPERATOR_NAME", "BU", "CREW", "SUPERVISOR_CHORUS_ID"], dropna=False)
               .agg(TIRES_BUILT=("TIRES_BUILT", "sum"), SHIFTS_WORKED=("PROD_DATE", "nunique"))
               .reset_index())
bc_agg = bc.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="BC_COUNT")
ac_agg = ac.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="AC_COUNT")
scrap_agg = scrap.groupby("OP_ID").agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum")).reset_index()

# Finishing uniformity per operator
fin_op = "FINISHING_OPERATOR_ID" if "FINISHING_OPERATOR_ID" in uni.columns else "CONFECTION_OPERATOR_ID"
uni["OP_ID"] = uni[fin_op].apply(norm)
grade = "OGU2_GRADE" if "OGU2_GRADE" in uni.columns else "UNI_GRADE"
if {"BARCODE", "TEST_DATETIME"}.issubset(uni.columns):
    uni = uni.sort_values(["BARCODE", "TEST_DATETIME"]).drop_duplicates("BARCODE", keep="first")
uni["IS_RFT"] = ((uni.get("RUN_TYPE") == "N") & (uni[grade].isna())).astype(int) if grade in uni.columns else 0
uni_agg = (uni.groupby("OP_ID").agg(UNI_TESTED=("BARCODE", "nunique"), UNI_RFT=("IS_RFT", "sum")).reset_index())

agg = (op_base.merge(bc_agg, on="OP_ID", how="left").merge(ac_agg, on="OP_ID", how="left")
              .merge(scrap_agg, on="OP_ID", how="left").merge(uni_agg, on="OP_ID", how="left"))
for c in ["BC_COUNT", "AC_COUNT", "SCRAP_LBS", "UNI_TESTED", "UNI_RFT"]:
    agg[c] = agg[c].fillna(0)

agg["BC_PCT"]    = (agg["BC_COUNT"] / agg["TIRES_BUILT"].replace(0, pd.NA) * 100).astype(float).round(3)
agg["AC_PCT"]    = (agg["AC_COUNT"] / agg["TIRES_BUILT"].replace(0, pd.NA) * 100).astype(float).round(3)
agg["SCRAP_PCT"] = (agg["SCRAP_LBS"] / agg["TIRES_BUILT"].replace(0, pd.NA)).astype(float).round(3)
agg["RFT_PCT"]   = (agg["UNI_RFT"] / agg["UNI_TESTED"].replace(0, pd.NA) * 100).astype(float).round(3)

MIN_TIRES = 100
agg["RANKABLE"] = agg["TIRES_BUILT"] >= MIN_TIRES

def nrm(s):
    rng = s.max() - s.min()
    return (s - s.min()) / rng if rng else 0
agg["BC_NORM"]    = nrm(agg["BC_PCT"].fillna(0))
agg["AC_NORM"]    = nrm(agg["AC_PCT"].fillna(0))
agg["SCRAP_NORM"] = nrm(agg["SCRAP_PCT"].fillna(0))
agg["UNI_NORM"]   = nrm((100 - agg["RFT_PCT"]).fillna(0))
agg["QUALITY_SCORE"] = ((agg["BC_NORM"] + agg["AC_NORM"] + agg["SCRAP_NORM"] + agg["UNI_NORM"]) / 4 * 100).round(2)
agg["RANK"] = agg["QUALITY_SCORE"].where(agg["RANKABLE"]).rank(method="min").astype("Int64")
agg = agg.sort_values(["RANKABLE", "QUALITY_SCORE"], ascending=[False, True])

print(f"agg_top_performers_fin rows: {len(agg):,}   tires: {agg['TIRES_BUILT'].sum():,.0f}")
dataiku.Dataset("agg_top_performers_fin").write_with_schema(agg)
