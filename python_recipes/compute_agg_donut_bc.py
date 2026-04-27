# -*- coding: utf-8 -*-
"""
Recipe: agg_donut_bc
Input  : fact_conf_bc
Output : agg_donut_bc
"""

import dataiku
import pandas as pd

bc = dataiku.Dataset("fact_conf_bc").get_dataframe()
bc.columns = [c.upper() for c in bc.columns]
bc = bc.dropna(subset=["CQ_CODE_STR"]).copy()

agg = (bc.groupby(["BU","CREW","CQ_CODE_STR","CQ_DESCRIPTION","CQ_RELATES_TO","CQ_TYPE_TIER"],
                  dropna=False).size().reset_index(name="CQ_COUNT")
         .sort_values("CQ_COUNT", ascending=False))

agg["BU_CREW_TOTAL"] = agg.groupby(["BU","CREW"])["CQ_COUNT"].transform("sum")
agg["PCT_OF_SLICE"]  = (agg["CQ_COUNT"] / agg["BU_CREW_TOTAL"] * 100).round(2)

print(f"agg_donut_bc rows: {len(agg):,}")
dataiku.Dataset("agg_donut_bc").write_with_schema(agg)
