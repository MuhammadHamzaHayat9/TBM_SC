# -*- coding: utf-8 -*-
"""
Recipe: agg_donut_ac
Input  : fact_conf_ac
Output : agg_donut_ac
"""

import dataiku
import pandas as pd

ac = dataiku.Dataset("fact_conf_ac").get_dataframe()
ac.columns = [c.upper() for c in ac.columns]
ac = ac.dropna(subset=["CQ_CODE_STR"]).copy()

agg = (ac.groupby(["BU","CREW","CQ_CODE_STR","CQ_DESCRIPTION","CQ_RELATES_TO","CQ_TYPE_TIER"],
                  dropna=False).size().reset_index(name="CQ_COUNT")
         .sort_values("CQ_COUNT", ascending=False))

agg["BU_CREW_TOTAL"] = agg.groupby(["BU","CREW"])["CQ_COUNT"].transform("sum")
agg["PCT_OF_SLICE"]  = (agg["CQ_COUNT"] / agg["BU_CREW_TOTAL"] * 100).round(2)

print(f"agg_donut_ac rows: {len(agg):,}")
dataiku.Dataset("agg_donut_ac").write_with_schema(agg)
