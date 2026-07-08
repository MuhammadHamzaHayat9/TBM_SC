# -*- coding: utf-8 -*-
"""
Scenario step: refresh every dataset the Tire Building Scorecard webapp reads.

Put this in a Dataiku Scenario as an "Execute Python code" step.

How it works
------------
1) Force-refresh the raw SOURCE datasets so any new rows are pulled in
   (SQL/synced sources re-sync; uploaded files that can't be built are
   skipped automatically).
2) Smart *recursive* rebuild of everything the webapp reads. Because the
   sources were just refreshed, every downstream node is out-of-date and gets
   rebuilt exactly once, in dependency order — including intermediates like
   dim_operator, the fact_* tables, and agg_kpi_summary.

If you ever want a guaranteed full rebuild regardless of change detection,
set FORCE = True (slower: shared upstream may rebuild more than once).
"""

from dataiku.scenario import Scenario

scenario = Scenario()

FORCE = False
TERMINAL_MODE = "RECURSIVE_FORCED_BUILD" if FORCE else "RECURSIVE_BUILD"

# Raw inputs that feed the flow (force-built so new data flows through).
SOURCES = [
    "view_employee", "BU_data",
    "first_step_prod", "second_step_prod",
    "conf_bc_grq2", "conf_ac_grq2",
    "nc_scrap", "uniformity_breakdown",
    "counter_verifier", "TBM6",
]

# The dimension + fact layer. These MUST be force-rebuilt after the sources,
# otherwise a smart recursive build can treat them as "up to date" and the
# aggregates keep reading stale facts (e.g. 1st step stuck a week behind).
FACTS = [
    "dim_operator",
    "fact_first_step", "fact_second_step",
    "fact_conf_bc", "fact_conf_ac",
    "fact_nc_scrap", "fact_uniformity",
]

# Datasets the webapp ACTIVELY reads (v5+ reads operator x week + donuts + CV).
# The legacy period aggregates (agg_top_performers, agg_kpi_summary/agg_weekly_trend,
# agg_uniformity, and their _fin twins) were superseded by agg_op_week and load
# many big facts at once — rebuilding them here OOMs. The webapp only falls back
# to them if agg_op_week is missing, so we don't refresh them in the scenario.
WEBAPP_DATASETS = [
    "fact_counter_verifier",
    "agg_donut_bc", "agg_donut_ac", "agg_donut_scrap",
    # operator x week building blocks (drive KPIs / leaderboards / rankings / trend)
    "agg_op_week", "agg_op_week_fin",
]

failures = []

# 1) Refresh the raw sources (skip any that aren't buildable, e.g. uploads)
for ds in SOURCES:
    try:
        print(f"[source] force-building {ds}")
        scenario.build_dataset(ds, build_mode="NON_RECURSIVE_FORCED_BUILD")
    except Exception as e:
        print(f"[source] skip {ds} (not buildable or missing): {e}")

# 2) Force-rebuild the dimension + fact layer so they pick up the fresh sources
#    (dim_operator first, then the facts that depend on it).
for ds in FACTS:
    try:
        print(f"[fact] force-building {ds}")
        scenario.build_dataset(ds, build_mode="NON_RECURSIVE_FORCED_BUILD")
    except Exception as e:
        print(f"[fact] FAILED {ds}: {e}")
        failures.append(ds)

# 3) Rebuild everything the webapp reads (recursive -> whole sub-tree, once each)
for ds in WEBAPP_DATASETS:
    try:
        print(f"[webapp] building {ds} ({TERMINAL_MODE})")
        scenario.build_dataset(ds, build_mode=TERMINAL_MODE)
    except Exception as e:
        print(f"[webapp] FAILED {ds}: {e}")
        failures.append(ds)

if failures:
    raise Exception("Scorecard refresh failed for: " + ", ".join(failures))
print("Scorecard datasets refreshed successfully.")
