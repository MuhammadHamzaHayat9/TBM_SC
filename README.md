# TBM_SC — Tire Building Scorecard

Dataiku project that turns raw production / quality data into a **Dash webapp** scorecard — a Power BI replacement for tire-building operator quality monitoring.

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
  compute_agg_kpi_summary.py      # Aggregate: BU x Crew x Week KPIs
  compute_agg_donut_bc.py         # Aggregate: BC donut data
  compute_agg_donut_ac.py         # Aggregate: AC donut data
  compute_agg_donut_scrap.py      # Aggregate: Scrap donut data
  compute_agg_top_performers.py   # Aggregate: operator leaderboard
  compute_agg_weekly_trend.py     # Aggregate: weekly bar+line trend
notebooks/
  inspect_fact_first_step.py      # Quick data inspection
```

## 🔄 Flow (Dataiku)

```
view_employee  ┐
BU_data        ┴─► dim_operator ───────┐
first_step_prod ----------------------├─► fact_first_step ─┐
conf_bc_grq2 ┐                       │                    ├─► aggregates ─► Dash webapp
TBM6         ┴─► fact_conf_bc ───────│                    │
conf_ac_grq2 ┐                       │                    │
TBM6         ┴─► fact_conf_ac ───────│                    │
nc_scrap ──────────────────────────┴─► fact_nc_scrap ────┘
```

## 📊 Aggregates

| # | Dataset | Drives |
|---|---|---|
| 1 | `agg_kpi_summary` | KPI cards |
| 2 | `agg_donut_bc` | BC donut |
| 3 | `agg_donut_ac` | AC donut |
| 4 | `agg_donut_scrap` | Scrap donut |
| 5 | `agg_top_performers` | Leaderboard panel |
| 6 | `agg_weekly_trend` | Weekly bar+line chart |

## 🎨 Webapp features

- KPI cards: Tires Built, Before Cure %, After Cure %, Scrap lbs/tire, **Counter Verifier %**
- 4 donut charts: BC / AC / Scrap breakdown, **Counter Verifier leaks by station**
- Weekly trend (bars + lines), including **CV% line**
- Top 10 operator leaderboard with **clickable drill-down** (click name → entire dashboard filters to that operator)
- Filters: BU, Crew, Week, Operator

## 📡 Datasets

The webapp reads the following Dataiku datasets at runtime:

| Dataset | Description |
|---|---|
| `fact_first_step` | Tires built per operator/day/TBM |
| `fact_conf_bc` | Before-Cure CQ events |
| `fact_conf_ac` | After-Cure CQ events |
| `fact_nc_scrap` | NC scrap lbs per operator/day/TBM |
| `agg_top_performers` | Operator leaderboard scores |
| `fact_counter_verifier` | End-of-line Counter Verifier leak results — drives the Counter Verifier % KPI, leaks-by-station donut, and CV% trend line |
