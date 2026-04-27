# -*- coding: utf-8 -*-
"""
Recipe: agg_donut_scrap
Input  : fact_nc_scrap
Output : agg_donut_scrap
"""

import dataiku
import pandas as pd

sc = dataiku.Dataset("fact_nc_scrap").get_dataframe()
sc.columns = [c.upper() for c in sc.columns]

agg = (sc.groupby(["BU","CREW","TBM"], dropna=False)
         .agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES","sum"),
              TIRES=("OP_TIRES","sum"),
              EVENTS=("OP_ID","count"))
         .reset_index().sort_values("SCRAP_LBS", ascending=False))

agg["LBS_PER_TIRE"]  = (agg["SCRAP_LBS"] / agg["TIRES"].replace(0, pd.NA)).round(3)
agg["BU_CREW_TOTAL"] = agg.groupby(["BU","CREW"])["SCRAP_LBS"].transform("sum")
agg["PCT_OF_SLICE"]  = (agg["SCRAP_LBS"] / agg["BU_CREW_TOTAL"] * 100).round(2)

print(f"agg_donut_scrap rows: {len(agg):,}")
dataiku.Dataset("agg_donut_scrap").write_with_schema(agg)
