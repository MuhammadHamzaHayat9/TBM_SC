# TBM_SC — Tire Building Scorecard

Dataiku project that turns raw production / quality data into a **Dash webapp** scorecard — a Power BI replacement for tire-building operator quality monitoring.

> **v5 — Power BI look & feel.** `webapps/tire_scorecard/app.py` reads the
> small `agg_*` datasets (a few hundred to a few thousand rows each) plus
> `fact_counter_verifier`, and lays them out to mirror the "Operator Quality
> Score Card" Power BI report: centered title, a "Previous Weeks Results"
> combo chart (BC%/AC% bars + RFT% line), a Top-Performers panel, an NC-Scrap
> panel, and a bottom row of Counter Verifier / Before Cure / After Cure
> donuts + a Uniformity RFT gauge — each with a centre percentage and a
> 🙂/😐/☹️ status face. Reading the aggregates (not the raw million-row facts)
> also keeps the webapp backend well within memory.

## 🔀 1st Step / 2nd Step toggle

A **Step toggle** switches the whole ScoreCard between **1st Step (Confection)**
and **2nd Step (Finishing)**, like the old app's two score-card tabs:

- **Before / After Cure donuts** split immediately by the `CQ_RELATES_TO`
  (`Confection` / `Finishing`) field already present in `agg_donut_bc/ac` — no
  new data needed.
- **Tires / Uniformity / Leaderboard / Trend** for the 2nd step read the
  finishing aggregates below. Build these recipes to populate the 2nd-step
  tiles; until then those tiles show "No data" and the finishing donuts still work.

| 2nd-step recipe | Output | Source |
|---|---|---|
| `compute_fact_second_step.py` | `fact_second_step` | `second_step_prod` |
| `compute_agg_uniformity_fin.py` | `agg_uniformity_fin` | `uniformity_breakdown` (FINISHING_OPERATOR_ID) |
| `compute_agg_top_performers_fin.py` | `agg_top_performers_fin` | fact_second_step + finishing CQs + scrap + uniformity |
| `compute_agg_weekly_trend_fin.py` | `agg_weekly_trend_fin` | fact_second_step + finishing CQs |

## 🖥️ Webapp tabs

| Tab | Reads | Shows |
|---|---|---|
| **ScoreCard** | `agg_top_performers`, `agg_uniformity`, `agg_donut_bc/ac/scrap`, `agg_weekly_trend`, `fact_counter_verifier` | KPI cards (Tires, Before Cure %, After Cure %, Scrap lbs/tire, Uniformity RFT %, Counter Verifier %), BC / AC / Scrap donuts, weekly trend, Top-10 performers |
| **Counter Verifier** | `fact_counter_verifier` | Leak % KPIs, leaks-by-station donut, weekly leak-% trend, highest leak-rate operators |
| **Rankings** | `agg_top_performers` | Full operator ranking table + Top-N bar charts (RFT%, AC%, BC%) |

Filters: **BU, Crew, Week, Operator**. Click any operator name on a leaderboard
or ranking to drill the whole app to that operator. The week filter applies to
the weekly trends, Uniformity, and Counter Verifier; the operator KPI cards and
CQ donuts are period totals (the `agg_donut_*` and `agg_top_performers`
datasets are not week-grained).

## 📡 Datasets the webapp reads

| Dataset | Grain | Drives |
|---|---|---|
| `agg_top_performers` | operator | KPI cards, leaderboard, rankings |
| `agg_uniformity` | BU × Crew × Week | Uniformity RFT KPI + trend |
| `agg_donut_bc` | BU × Crew × CQ | Before-Cure donut |
| `agg_donut_ac` | BU × Crew × CQ | After-Cure donut |
| `agg_donut_scrap` | BU × Crew × TBM | NC Scrap donut |
| `agg_weekly_trend` | BU × Week | Weekly trend (tires + BC%/AC%) |
| `fact_counter_verifier` | tire | Counter Verifier % KPI, leaks-by-station, CV trend |

## 🗂️ Repo layout

```
webapps/
  tire_scorecard/
    app.py                        # Dash webapp (paste into Dataiku Code Webapp → Dash)
python_recipes/
  compute_dim_operator.py         # Dimension: operator master (HR + BU/Crew)
  compute_fact_first_step.py      # Fact: tires built per operator/day/TBM
  compute_fact_conf_bc.py         # Fact: Before-Cure CQ events
  compute_fact_conf_ac.py         # Fact: After-Cure CQ events
  compute_fact_nc_scrap.py        # Fact: NC scrap lbs per operator/day/TBM
  compute_fact_uniformity.py      # Fact: per-tire uniformity test (IRF4 / RFT)
  compute_agg_kpi_summary.py      # Aggregate: BU x Crew x Week KPIs
  compute_agg_donut_bc.py         # Aggregate: BC donut data
  compute_agg_donut_ac.py         # Aggregate: AC donut data
  compute_agg_donut_scrap.py      # Aggregate: Scrap donut data
  compute_agg_top_performers.py   # Aggregate: operator leaderboard
  compute_agg_weekly_trend.py     # Aggregate: weekly bar+line trend
  inspect_schemas.py              # Read-only helper: dump dataset columns / samples
```

> Note: the recipe files in `python_recipes/` document the flow, but the live
> Dataiku project may build some `agg_*` datasets with newer logic (e.g.
> `agg_top_performers` now carries uniformity columns and `agg_uniformity`
> exists). The webapp reads whatever columns the built datasets expose.

## 🔄 Flow (Dataiku)

```
view_employee  ┐
BU_data        ┴─► dim_operator ───────┐
first_step_prod ----------------------├─► fact_first_step ─┐
conf_bc_grq2 ┐                       │                    ├─► agg_* ─► Dash webapp
TBM6         ┴─► fact_conf_bc ───────│                    │
conf_ac_grq2 ┐                       │                    │
TBM6         ┴─► fact_conf_ac ───────│                    │
uniformity_breakdown ────────────────├─► fact_uniformity  │
nc_scrap ──────────────────────────┴─► fact_nc_scrap ────┘
counter_verifier ─────────────────────► fact_counter_verifier ─► Dash webapp
```
