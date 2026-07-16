# -*- coding: utf-8 -*-
"""
Clean BC_Cage_Log -> BC_Cage_Log_clean

The raw BC_Cage_Log import is messy: the source Excel has three banner/
header rows on top, so Dataiku named the columns col_0..col_13 and pulled
the real headers ("RACK ID", "Date", ...) in as data rows.

This script renames the 14 columns BY POSITION (A..N of the Excel — robust
to the junk source names) and keeps only real entries (RACK ID is numeric),
which drops the two banner rows, the embedded header row, and blank rows.

Dates are kept as text on purpose: the source dates ("26-May", "12-Nov")
have no year, so parsing them would guess the wrong one.

Run in a Dataiku notebook (or paste into a Python recipe with input
BC_Cage_Log and output BC_Cage_Log_clean). Create the managed output
dataset BC_Cage_Log_clean first if it does not exist.
"""

import dataiku
import pandas as pd

# 14 real headers, in column order (A..N of the Excel)
CLEAN_COLS = [
    "RACK ID", "Date", "Removal Date", "Person Responsible",
    "Person Entering", "Quantity", "Tire Codes", "CQ or Condition",
    "Location", "Disposition", "Max Recoup Date", "Comments",
    "Person Removing", "Date Removed",
]

# read raw as stored (no type inference), keep everything as text
raw = dataiku.Dataset("BC_Cage_Log").get_dataframe(infer_with_pandas=False)

if raw.shape[1] != len(CLEAN_COLS):
    raise ValueError(
        f"Expected {len(CLEAN_COLS)} columns, got {raw.shape[1]}. "
        "Check the raw import before cleaning."
    )

# rename by POSITION (the raw header names are junk), so this is robust
df = raw.copy()
df.columns = CLEAN_COLS

# keep only real entries: RACK ID is always a number.
# drops the 'YELLOW SHADED...' banner row, the 'RACK ID' header row,
# and all the empty trailing rows in one shot.
rack = df["RACK ID"].astype("string").str.strip()
df = df[rack.str.fullmatch(r"\d+", na=False)].reset_index(drop=True)

# strip stray whitespace in every text cell
for c in df.columns:
    df[c] = df[c].astype("string").str.strip()

print(f"Clean rows: {len(df)}")
print(df.head(10).to_string(index=False))

# write to the clean dataset
dataiku.Dataset("BC_Cage_Log_clean").write_with_schema(df)
print("Wrote BC_Cage_Log_clean")
