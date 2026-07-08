# -*- coding: utf-8 -*-
"""
Recipe: agg_weekly_trend_fin   (2nd-Step / Finishing weekly trend)
Inputs : fact_second_step, fact_conf_bc, fact_conf_ac
Output : agg_weekly_trend_fin   (same columns as agg_weekly_trend)

Weekly 2nd-step tires built + Finishing Before/After-Cure CQ %, with a
BU='ALL' overall row set plus per-BU rows (CREW='ALL'), matching how the
webapp reads agg_weekly_trend.
"""

import dataiku
import pandas as pd

def read(name, cols):
    """Read only the needed columns (keeps the recipe memory-safe)."""
    ds = dataiku.Dataset(name)
    try:
        df = ds.get_dataframe(columns=cols)
    except Exception:
        df = ds.get_dataframe()
        want = {c.upper() for c in cols}
        df = df[[c for c in df.columns if c.upper() in want]]
    df.columns = [c.upper() for c in df.columns]
    return df

prod = read("fact_second_step", ["BU", "PROD_YEAR", "PROD_WEEK", "TIRES_BUILT"])
bc   = read("fact_conf_bc", ["BU", "PROD_YEAR", "PROD_WEEK", "CQ_CODE_STR", "CQ_RELATES_TO"])
ac   = read("fact_conf_ac", ["BU", "PROD_YEAR", "PROD_WEEK", "CQ_CODE_STR", "CQ_RELATES_TO"])

def fin_only(df):
    if "CQ_RELATES_TO" in df.columns:
        df = df[df["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == "finishing"]
    return df.dropna(subset=["CQ_CODE_STR"]) if "CQ_CODE_STR" in df.columns else df
bc, ac = fin_only(bc), fin_only(ac)

keys = ["PROD_YEAR", "PROD_WEEK"]

def weekly(prod, bc, ac, by_bu):
    gk = (["BU"] + keys) if by_bu else keys
    p = prod.groupby(gk, dropna=False)["TIRES_BUILT"].sum().reset_index()
    b = bc.groupby(gk, dropna=False).size().reset_index(name="BC_COUNT")
    a = ac.groupby(gk, dropna=False).size().reset_index(name="AC_COUNT")
    t = p.merge(b, on=gk, how="left").merge(a, on=gk, how="left")
    if not by_bu:
        t["BU"] = "ALL"
    t["CREW"] = "ALL"
    return t

trend = pd.concat([weekly(prod, bc, ac, False), weekly(prod, bc, ac, True)], ignore_index=True)
for c in ["BC_COUNT", "AC_COUNT"]:
    trend[c] = trend[c].fillna(0)
trend["SCRAP_LBS"] = 0.0
trend["BC_PCT"] = (trend["BC_COUNT"] / trend["TIRES_BUILT"].replace(0, pd.NA) * 100).astype(float).round(3)
trend["AC_PCT"] = (trend["AC_COUNT"] / trend["TIRES_BUILT"].replace(0, pd.NA) * 100).astype(float).round(3)
trend["SCRAP_PCT"] = 0.0
trend["WEEK_LABEL"] = (trend["PROD_YEAR"].astype("Int64").astype(str)
                       + "-W" + trend["PROD_WEEK"].astype("Int64").astype(str).str.zfill(2))
trend = trend.sort_values(["BU", "PROD_YEAR", "PROD_WEEK"]).reset_index(drop=True)

print(f"agg_weekly_trend_fin rows: {len(trend):,}")
dataiku.Dataset("agg_weekly_trend_fin").write_with_schema(trend)
