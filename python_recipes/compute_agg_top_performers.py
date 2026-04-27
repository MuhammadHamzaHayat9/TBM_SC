# -*- coding: utf-8 -*-
"""
Recipe: agg_top_performers
Inputs : fact_first_step, fact_conf_bc, fact_conf_ac, fact_nc_scrap
Output : agg_top_performers
"""

import dataiku
import pandas as pd

prod  = dataiku.Dataset("fact_first_step").get_dataframe()
bc    = dataiku.Dataset("fact_conf_bc").get_dataframe()
ac    = dataiku.Dataset("fact_conf_ac").get_dataframe()
scrap = dataiku.Dataset("fact_nc_scrap").get_dataframe()

for df in (prod, bc, ac, scrap):
    df.columns = [c.upper() for c in df.columns]

def norm_op_id(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

for df in (prod, bc, ac, scrap):
    df["OP_ID"] = df["OP_ID"].apply(norm_op_id)

op_base = (prod.groupby(["OP_ID","OPERATOR_NAME","BU","CREW","SUPERVISOR_CHORUS_ID"], dropna=False)
               .agg(TIRES_BUILT=("TIRES_BUILT","sum"),
                    SHIFTS_WORKED=("PROD_DATE","nunique"))
               .reset_index())

bc_agg = bc.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="BC_COUNT")
ac_agg = ac.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="AC_COUNT")
scrap_agg = scrap.groupby("OP_ID").agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES","sum")).reset_index()

agg = op_base.merge(bc_agg, on="OP_ID", how="left") \
             .merge(ac_agg, on="OP_ID", how="left") \
             .merge(scrap_agg, on="OP_ID", how="left")

for col in ["BC_COUNT","AC_COUNT","SCRAP_LBS"]:
    agg[col] = agg[col].fillna(0)

agg["BC_PCT"]    = (agg["BC_COUNT"]  / agg["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
agg["AC_PCT"]    = (agg["AC_COUNT"]  / agg["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
agg["SCRAP_PCT"] = (agg["SCRAP_LBS"] / agg["TIRES_BUILT"].replace(0, pd.NA)).round(3)

MIN_TIRES = 100
agg["RANKABLE"] = agg["TIRES_BUILT"] >= MIN_TIRES

def norm(s):
    rng = s.max() - s.min()
    return (s - s.min()) / rng if rng else 0

agg["BC_NORM"]    = norm(agg["BC_PCT"].fillna(0))
agg["AC_NORM"]    = norm(agg["AC_PCT"].fillna(0))
agg["SCRAP_NORM"] = norm(agg["SCRAP_PCT"].fillna(0))
agg["QUALITY_SCORE"] = ((agg["BC_NORM"] + agg["AC_NORM"] + agg["SCRAP_NORM"]) / 3 * 100).round(2)
agg["RANK"] = agg["QUALITY_SCORE"].where(agg["RANKABLE"]).rank(method="min").astype("Int64")
agg = agg.sort_values(["RANKABLE","QUALITY_SCORE"], ascending=[False, True])

print(f"agg_top_performers rows: {len(agg):,}")
dataiku.Dataset("agg_top_performers").write_with_schema(agg)
