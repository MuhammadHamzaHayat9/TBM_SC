# -*- coding: utf-8 -*-
"""
Recipe: agg_kpi_summary
Inputs : fact_first_step, fact_conf_bc, fact_conf_ac, fact_nc_scrap
Output : agg_kpi_summary
"""

import dataiku
import pandas as pd

prod  = dataiku.Dataset("fact_first_step").get_dataframe()
bc    = dataiku.Dataset("fact_conf_bc").get_dataframe()
ac    = dataiku.Dataset("fact_conf_ac").get_dataframe()
scrap = dataiku.Dataset("fact_nc_scrap").get_dataframe()

for df in (prod, bc, ac, scrap):
    df.columns = [c.upper() for c in df.columns]

GROUP_KEYS = ["BU", "CREW", "PROD_YEAR", "PROD_WEEK"]

prod_agg = (prod.groupby(GROUP_KEYS, dropna=False)
                .agg(TIRES_BUILT=("TIRES_BUILT", "sum"),
                     OPERATORS=("OP_ID", "nunique"))
                .reset_index())

bc_agg = (bc.dropna(subset=["CQ_CODE_STR"])
            .groupby(GROUP_KEYS, dropna=False).size().reset_index(name="BC_COUNT"))

ac_agg = (ac.dropna(subset=["CQ_CODE_STR"])
            .groupby(GROUP_KEYS, dropna=False).size().reset_index(name="AC_COUNT"))

scrap_agg = (scrap.groupby(GROUP_KEYS, dropna=False)
                  .agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum"),
                       SCRAP_TIRES=("OP_TIRES", "sum"))
                  .reset_index())

agg = prod_agg.merge(bc_agg, on=GROUP_KEYS, how="left") \
              .merge(ac_agg, on=GROUP_KEYS, how="left") \
              .merge(scrap_agg, on=GROUP_KEYS, how="left")

for col in ["BC_COUNT", "AC_COUNT", "SCRAP_LBS", "SCRAP_TIRES"]:
    agg[col] = agg[col].fillna(0)

agg["BC_PCT"]    = (agg["BC_COUNT"]  / agg["TIRES_BUILT"].replace(0, pd.NA)) * 100
agg["AC_PCT"]    = (agg["AC_COUNT"]  / agg["TIRES_BUILT"].replace(0, pd.NA)) * 100
agg["SCRAP_PCT"] = (agg["SCRAP_LBS"] / agg["TIRES_BUILT"].replace(0, pd.NA))

for col in ["BC_PCT", "AC_PCT", "SCRAP_PCT"]:
    agg[col] = agg[col].astype(float).round(3)

print(f"agg_kpi_summary rows: {len(agg):,}")
dataiku.Dataset("agg_kpi_summary").write_with_schema(agg)
