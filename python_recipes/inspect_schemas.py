# -*- coding: utf-8 -*-
"""
inspect_schemas — READ-ONLY dataset explorer (writes nothing)

Paste this into a Dataiku **Python notebook** (or a Python recipe with no
output) and run it. For each dataset it prints:
  - shape (rows x cols)
  - every column with its dtype and a non-null sample value
  - the first 5 rows
  - a numeric summary (min/max/mean/…) for number columns

Then copy the whole output back so the webapp can be wired to these datasets.
"""

import dataiku
import pandas as pd

pd.set_option("display.max_columns", 200)
pd.set_option("display.width", 200)

DATASETS = [
    "agg_uniformity",
    "agg_donut_ac",
    "agg_donut_bc",
    "agg_donut_scrap",
    "agg_top_performers",
    "agg_weekly_trend",
    "fact_counter_verifier",
]

def sample_val(s):
    v = s.dropna()
    return repr(v.iloc[0]) if len(v) else "<all null>"

for name in DATASETS:
    print("=" * 80)
    print("DATASET:", name)
    try:
        df = dataiku.Dataset(name).get_dataframe()
    except Exception as e:
        print("  !! could not read:", e)
        continue

    df.columns = [c.upper() for c in df.columns]
    print(f"  shape: {df.shape[0]:,} rows x {df.shape[1]} cols")

    print("\n  COLUMNS  (name : dtype : sample value)")
    for c in df.columns:
        print(f"    - {c:32s} {str(df[c].dtype):12s} {sample_val(df[c])}")

    print("\n  HEAD (first 5 rows):")
    print(df.head(5).to_string())

    num = df.select_dtypes("number")
    if len(num.columns):
        print("\n  NUMERIC SUMMARY:")
        print(num.describe().T.to_string())
    print()

print("=" * 80)
print("Done — copy everything above and paste it back.")
