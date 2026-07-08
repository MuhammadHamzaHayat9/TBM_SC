# -*- coding: utf-8 -*-
"""
Recipe: agg_top_performers_fin   (2nd-Step / Finishing operator leaderboard)
Inputs : fact_second_step, fact_conf_bc, fact_conf_ac, fact_nc_scrap, fact_uniformity
Output : agg_top_performers_fin   (same columns the webapp reads from agg_top_performers)

Memory-safe: each input is read with only the columns this recipe needs
(get_dataframe(columns=...)), and uniformity comes from the slim, pre-built
fact_uniformity instead of the wide raw uniformity_breakdown — so the whole
recipe stays small even though the underlying tables are large.

- TIRES_BUILT / SHIFTS_WORKED : from fact_second_step (2nd-step production)
- BC_COUNT / AC_COUNT         : Before/After-Cure CQs where CQ_RELATES_TO='Finishing'
- SCRAP_LBS                   : from fact_nc_scrap
- UNI_TESTED / UNI_RFT / RFT_PCT : uniformity keyed on FINISHING_OPERATOR_ID
- QUALITY_SCORE / RANK        : normalised composite (lower = better)
"""

import dataiku
import pandas as pd

def read(name, cols):
    """Read only the needed columns; fall back to a full read + subset if the
    column list doesn't match the stored schema exactly."""
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

prod  = read("fact_second_step", ["OP_ID", "OPERATOR_NAME", "BU", "CREW",
                                   "SUPERVISOR_CHORUS_ID", "TIRES_BUILT", "PROD_DATE"])
bc    = read("fact_conf_bc", ["OP_ID", "CQ_CODE_STR", "CQ_RELATES_TO"])
ac    = read("fact_conf_ac", ["OP_ID", "CQ_CODE_STR", "CQ_RELATES_TO"])
scrap = read("fact_nc_scrap", ["OP_ID", "OP_SCRAP_LBS_BY_TIRES"])
uni   = read("fact_uniformity", ["FINISHING_OPERATOR_ID", "BARCODE", "IS_RFT"])

for df in (prod, bc, ac, scrap):
    if "OP_ID" in df.columns:
        df["OP_ID"] = norm_ids(df["OP_ID"])

# Keep only Finishing-related CQs
def fin_only(df):
    if "CQ_RELATES_TO" in df.columns:
        df = df[df["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == "finishing"]
    return df
bc, ac = fin_only(bc), fin_only(ac)

op_base = (prod.groupby(["OP_ID", "OPERATOR_NAME", "BU", "CREW", "SUPERVISOR_CHORUS_ID"], dropna=False)
               .agg(TIRES_BUILT=("TIRES_BUILT", "sum"), SHIFTS_WORKED=("PROD_DATE", "nunique"))
               .reset_index())
bc_agg = bc.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="BC_COUNT")
ac_agg = ac.dropna(subset=["CQ_CODE_STR"]).groupby("OP_ID").size().reset_index(name="AC_COUNT")
scrap_agg = scrap.groupby("OP_ID").agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum")).reset_index()

# Finishing uniformity per operator (one RFT flag per barcode, then per operator)
uni["OP_ID"] = norm_ids(uni["FINISHING_OPERATOR_ID"])
uni["IS_RFT"] = pd.to_numeric(uni.get("IS_RFT"), errors="coerce").fillna(0)
per_tire = uni.groupby(["OP_ID", "BARCODE"], dropna=False)["IS_RFT"].max().reset_index()
uni_agg = (per_tire.groupby("OP_ID")
                   .agg(UNI_TESTED=("BARCODE", "nunique"), UNI_RFT=("IS_RFT", "sum"))
                   .reset_index())

agg = (op_base.merge(bc_agg, on="OP_ID", how="left").merge(ac_agg, on="OP_ID", how="left")
              .merge(scrap_agg, on="OP_ID", how="left").merge(uni_agg, on="OP_ID", how="left"))
for c in ["BC_COUNT", "AC_COUNT", "SCRAP_LBS", "UNI_TESTED", "UNI_RFT"]:
    agg[c] = agg[c].fillna(0)

_den = agg["TIRES_BUILT"].replace(0, float("nan"))
agg["BC_PCT"]    = (agg["BC_COUNT"] / _den * 100).round(3)
agg["AC_PCT"]    = (agg["AC_COUNT"] / _den * 100).round(3)
agg["SCRAP_PCT"] = (agg["SCRAP_LBS"] / _den).round(3)
agg["RFT_PCT"]   = (agg["UNI_RFT"] / agg["UNI_TESTED"].replace(0, float("nan")) * 100).round(3)

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
