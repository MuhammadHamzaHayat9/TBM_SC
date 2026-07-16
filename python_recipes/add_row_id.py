# -*- coding: utf-8 -*-
"""
One-time: add a stable `row_id` key to Bc_Cage_SP.

The BC Cage Log webapp writes per row (INSERT for new rows, UPDATE ... WHERE
row_id = ... for edits) instead of rewriting the whole PostgreSQL table. That
needs a unique key. This script adds `row_id` = 1..N as the first column and
writes it back once (a single full rewrite). Run it in a Dataiku notebook.

Safe to re-run: it drops any existing row_id and re-numbers.
"""

import dataiku

ds = dataiku.Dataset("Bc_Cage_SP")
df = ds.get_dataframe(infer_with_pandas=False)

df = df.drop(columns=[c for c in df.columns if c == "row_id"])
df.insert(0, "row_id", range(1, len(df) + 1))

ds.write_with_schema(df)
print(f"Added row_id — {len(df)} rows, ids 1..{len(df)}")
