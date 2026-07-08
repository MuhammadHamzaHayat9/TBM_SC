# -*- coding: utf-8 -*-
"""
Recipe: agg_donut_scrap
Input  : fact_nc_scrap
Output : agg_donut_scrap  (BU x CREW x WEEK x TBM — drives the NC-Scrap donut)

Memory-safe: reads only the columns the donut needs.
"""

import dataiku
import pandas as pd

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

sc = read("fact_nc_scrap", ["BU", "CREW", "PROD_YEAR", "PROD_WEEK", "TBM",
                            "OP_SCRAP_LBS_BY_TIRES", "OP_TIRES", "OP_ID"])

# PROD_YEAR/PROD_WEEK are included so the webapp can filter the donut by week.
agg = (sc.groupby(["BU", "CREW", "PROD_YEAR", "PROD_WEEK", "TBM"], dropna=False)
         .agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum"),
              TIRES=("OP_TIRES", "sum"),
              EVENTS=("OP_ID", "count"))
         .reset_index().sort_values("SCRAP_LBS", ascending=False))

agg["LBS_PER_TIRE"]  = (agg["SCRAP_LBS"] / agg["TIRES"].replace(0, float("nan"))).round(3)
agg["BU_CREW_TOTAL"] = agg.groupby(["BU", "CREW"])["SCRAP_LBS"].transform("sum")
agg["PCT_OF_SLICE"]  = (agg["SCRAP_LBS"] / agg["BU_CREW_TOTAL"] * 100).round(2)

print(f"agg_donut_scrap rows: {len(agg):,}")
dataiku.Dataset("agg_donut_scrap").write_with_schema(agg)
