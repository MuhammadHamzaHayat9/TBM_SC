# -*- coding: utf-8 -*-
"""
Recipe: agg_donut_bc
Input  : fact_conf_bc
Output : agg_donut_bc  (BU x CREW x WEEK x CQ — drives the Before-Cure donut)

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

bc = read("fact_conf_bc", ["BU", "CREW", "PROD_YEAR", "PROD_WEEK",
                           "CQ_CODE_STR", "CQ_DESCRIPTION", "CQ_RELATES_TO", "CQ_TYPE_TIER"])
bc = bc.dropna(subset=["CQ_CODE_STR"]).copy()

# PROD_YEAR/PROD_WEEK are included so the webapp can filter the donut by week.
agg = (bc.groupby(["BU", "CREW", "PROD_YEAR", "PROD_WEEK",
                   "CQ_CODE_STR", "CQ_DESCRIPTION", "CQ_RELATES_TO", "CQ_TYPE_TIER"],
                  dropna=False).size().reset_index(name="CQ_COUNT")
         .sort_values("CQ_COUNT", ascending=False))

agg["BU_CREW_TOTAL"] = agg.groupby(["BU", "CREW"])["CQ_COUNT"].transform("sum")
agg["PCT_OF_SLICE"]  = (agg["CQ_COUNT"] / agg["BU_CREW_TOTAL"] * 100).round(2)

print(f"agg_donut_bc rows: {len(agg):,}")
dataiku.Dataset("agg_donut_bc").write_with_schema(agg)
