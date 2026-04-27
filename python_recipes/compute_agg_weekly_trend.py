# -*- coding: utf-8 -*-
"""
Recipe: agg_weekly_trend
Input  : agg_kpi_summary
Output : agg_weekly_trend
"""

import dataiku
import pandas as pd

src = dataiku.Dataset("agg_kpi_summary").get_dataframe()
src.columns = [c.upper() for c in src.columns]

overall = (src.groupby(["PROD_YEAR","PROD_WEEK"], dropna=False)
              .agg(TIRES_BUILT=("TIRES_BUILT","sum"),
                   BC_COUNT=("BC_COUNT","sum"),
                   AC_COUNT=("AC_COUNT","sum"),
                   SCRAP_LBS=("SCRAP_LBS","sum"))
              .reset_index())
overall["BU"] = "ALL"
overall["CREW"] = "ALL"

per_bu = (src.groupby(["BU","PROD_YEAR","PROD_WEEK"], dropna=False)
             .agg(TIRES_BUILT=("TIRES_BUILT","sum"),
                  BC_COUNT=("BC_COUNT","sum"),
                  AC_COUNT=("AC_COUNT","sum"),
                  SCRAP_LBS=("SCRAP_LBS","sum"))
             .reset_index())
per_bu["CREW"] = "ALL"

trend = pd.concat([overall, per_bu], ignore_index=True)

trend["BC_PCT"]    = (trend["BC_COUNT"]  / trend["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
trend["AC_PCT"]    = (trend["AC_COUNT"]  / trend["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
trend["SCRAP_PCT"] = (trend["SCRAP_LBS"] / trend["TIRES_BUILT"].replace(0, pd.NA)).round(3)

trend["WEEK_LABEL"] = (trend["PROD_YEAR"].astype(int).astype(str)
                       + "-W" + trend["PROD_WEEK"].astype(int).astype(str).str.zfill(2))
trend = trend.sort_values(["BU","PROD_YEAR","PROD_WEEK"]).reset_index(drop=True)

print(f"agg_weekly_trend rows: {len(trend):,}")
dataiku.Dataset("agg_weekly_trend").write_with_schema(trend)
