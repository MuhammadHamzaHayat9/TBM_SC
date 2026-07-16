# -*- coding: utf-8 -*-
"""
Prepare BC_Cage_Log -> bc_cage_log_prepared

BC_Cage_Log is the uploaded cage log (re-imported cleanly: the Excel's three
banner/header rows are skipped at import time, and the header line-breaks were
flattened, so columns already carry the full names — "RACK ID",
"Date (START HERE)", ... "Date Removed").

This recipe:
  * drops ONLY completely-empty rows (keeps real records even when RACK ID is
    blank — there are ~30 such genuine entries);
  * trims stray whitespace and turns "" into NULL;
  * derives a Status column: "Open" while "Date Removed" is blank (item still
    in the cage / overflow), "Closed" once it has a date.

Dates are kept as text on purpose: the source dates ("26-May", "12-Nov") have
no year, so parsing them would guess the wrong one.

Run as a Dataiku Python recipe (input BC_Cage_Log, output
bc_cage_log_prepared) or paste into a notebook. If running in a notebook,
create the bc_cage_log_prepared dataset first (e.g. a PostgreSQL managed
dataset).
"""

import dataiku
import pandas as pd

INPUT = "BC_Cage_Log"
OUTPUT = "bc_cage_log_prepared"
DATE_REMOVED_COL = "Date Removed"

# --- input ---
df = dataiku.Dataset(INPUT).get_dataframe(infer_with_pandas=False)

# --- drop ONLY completely-empty rows (all columns blank/NaN) ---
def row_all_blank(r):
    return all(pd.isna(v) or str(v).strip() == "" for v in r)

mask_empty = df.apply(row_all_blank, axis=1)
clean = df[~mask_empty].reset_index(drop=True)

# --- tidy text: strip whitespace, turn "" into NULL ---
for c in clean.columns:
    s = clean[c].astype("string").str.strip()
    clean[c] = s.where(s.str.len() > 0, None)

# --- derive Status: Open (still in cage) vs Closed (removed) ---
if DATE_REMOVED_COL in clean.columns:
    dr = clean[DATE_REMOVED_COL].astype("string").str.strip()
    is_closed = dr.notna() & (dr.str.len() > 0)
    clean["Status"] = is_closed.map({True: "Closed", False: "Open"})

# --- report ---
print(f"Input rows : {len(df)}")
print(f"Dropped    : {int(mask_empty.sum())} empty rows")
print(f"Output rows: {len(clean)}")
if "Status" in clean.columns:
    print("\nStatus breakdown:")
    print(clean["Status"].value_counts().to_string())

# --- output ---
dataiku.Dataset(OUTPUT).write_with_schema(clean)
print(f"\nWrote {OUTPUT}")
