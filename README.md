# TBM_SC — Tire Building Scorecard

Dataiku project that turns raw production / quality data into a **multi-page Dash webapp** scorecard — a Power BI replacement for tire-building operator quality monitoring.

> **v3 — full Power BI rebuild.** `webapps/tire_scorecard/app.py` now mirrors the
> 13-page **TB ScoreCard** Power BI report: two mirror-image domains
> (**Confection = 1st Step**, **Finishing = 2nd Step**), each with a ScoreCard,
> four detail pages, and a Rankings page, plus a shared Uniformity focus page.
> The **Counter Verifier (C1P)** KPI/donut is a first-class citizen again.

## 🗂️ Repo layout

```
webapps/
  tire_scorecard/
    app.py                          # Multi-page Dash webapp (paste into Dataiku Code Webapp → Dash)
python_recipes/
  compute_dim_operator.py           # Dimension: operator master (HR + BU/Crew)
  compute_fact_first_step.py        # Fact: tires built per operator/day/TBM
  compute_fact_conf_bc.py           # Fact: Before-Cure CQ events (Confection)
  compute_fact_conf_ac.py           # Fact: After-Cure CQ events (Confection)
  compute_fact_counter_verifier.py  # Fact: Counter Verifier (C1P) leak results (Confection)
  compute_fact_nc_scrap.py          # Fact: NC scrap lbs per operator/day/TBM
  compute_fact_uniformity.py        # Fact: per-tire uniformity test, confection-keyed (IRF4 / RFT)
  # --- Finishing / 2nd Step (mirror the Confection recipes) ---
  compute_fact_second_step.py       # Fact: 2nd-step tires built per operator/day/TBM
  compute_fact_fin_bc.py            # Fact: Before-Cure CQ events (Finishing)
  compute_fact_fin_ac.py            # Fact: After-Cure CQ events (Finishing)
  compute_fact_fin_counter_verifier.py # Fact: Counter Verifier (C1P) leak results (Finishing)
  compute_fact_uniformity_fin.py    # Fact: per-tire uniformity test, finishing-keyed
  compute_agg_top_performers_fin.py # Aggregate: 2nd-step operator leaderboard
  compute_agg_kpi_summary.py        # Aggregate: BU x Crew x Week KPIs
  compute_agg_donut_bc.py           # Aggregate: BC donut data
  compute_agg_donut_ac.py           # Aggregate: AC donut data
  compute_agg_donut_scrap.py        # Aggregate: Scrap donut data
  compute_agg_top_performers.py     # Aggregate: operator leaderboard
  compute_agg_weekly_trend.py       # Aggregate: weekly bar+line trend
```

## 🖥️ Webapp pages (mirrors the Power BI report)

The webapp has a left-hand sidebar that navigates the 13 report pages. The same
page builders serve both domains, parameterised by `DOMAINS` at the top of
`app.py` — repoint the **Finishing** dataset names there at your real 2nd-Step
datasets (any dataset not built yet simply renders "No data").

| Domain | Pages |
|---|---|
| **Confection (1st Step)** | ScoreCard · C1P Leak Details · BC Details · AC Details · UNIF Details · Rankings |
| **Finishing (2nd Step)** | ScoreCard · C1P Leak Details · BC Details · AC Details · UNIF Details · Rankings |
| **Shared** | Uniformity — Non-1st Focus |

### ScoreCard page
- **KPI cards:** Tires Built, **Counter Verifier %**, Before Cure %, After Cure %, Uniformity RFT %
- **Donuts:** Counter Verifier Results (leak type/station), Before Cure, After Cure
- **Uniformity RFT gauge** + **"Previous Weeks Results"** combo chart (BC% / AC% / RFT% lines over tires-built bars)
- **Two leaderboards:** Total Quality — Top Performers, and Top Performers — NC Scrap
- **Filters:** Business Unit, Crew, Week, Rankings Top-N; click any operator name to drill the whole app to that operator

### Detail pages
Chart + breakdown table for the Counter Verifier (C1P), Before Cure, After Cure, and Uniformity streams.

### Rankings page
Operator ranking table (Tires, BC%, AC%, RFT%, Scrap%, Score) plus Top-N bar charts (Top RFT%, Lowest AC%, Lowest BC%).

## 🔄 Flow (Dataiku)

```
view_employee  ┐
BU_data        ┴─► dim_operator ──────────┐
first_step_prod ------------------------├─► fact_first_step ──┐
conf_bc_grq2 ┐                          │                     │
TBM6         ┴─► fact_conf_bc ──────────│                     │
conf_ac_grq2 ┐                          │                     ├─► aggregates ─► Dash webapp
TBM6         ┴─► fact_conf_ac ──────────│                     │
counter_verifier ──────────────────────├─► fact_counter_verifier
uniformity_breakdown ──────────────────├─► fact_uniformity    │
nc_scrap ──────────────────────────────┴─► fact_nc_scrap ─────┘
```

## 📡 Datasets

The webapp reads the following Dataiku datasets at runtime:

| Dataset | Description |
|---|---|
| `fact_first_step` | Tires built per operator/day/TBM (Confection) |
| `fact_conf_bc` | Before-Cure CQ events |
| `fact_conf_ac` | After-Cure CQ events |
| `fact_counter_verifier` | End-of-line Counter Verifier (C1P) leak results — drives the Counter Verifier % KPI and leaks-by-type/station donut |
| `fact_uniformity` | Per-tire uniformity test — drives the Uniformity RFT % KPI, gauge, and RFT% trend line |
| `fact_nc_scrap` | NC scrap lbs per operator/day/TBM |
| `agg_top_performers` | Operator leaderboard scores |

### Finishing / 2nd-Step domain

The Finishing pages are driven by the `compute_fact_fin_*` /
`compute_fact_second_step` / `compute_agg_top_performers_fin` recipes, which
mirror the Confection recipes. Each recipe reads a 2nd-step **source** dataset,
declared as a `SRC = "..."` constant at the top — confirm these match your
Dataiku project (defaults follow the Confection naming convention):

| Finishing output | Source dataset (`SRC`) | Mirrors |
|---|---|---|
| `fact_second_step` | `second_step_prod` | `fact_first_step` |
| `fact_fin_bc` | `fin_bc_grq2` | `fact_conf_bc` |
| `fact_fin_ac` | `fin_ac_grq2` | `fact_conf_ac` |
| `fact_fin_counter_verifier` | `fin_counter_verifier` | `fact_counter_verifier` |
| `fact_uniformity_fin` | `uniformity_breakdown` (finishing-keyed) | `fact_uniformity` |
| `agg_top_performers_fin` | the four facts above | `agg_top_performers` |

Until these datasets are built, the Finishing pages render gracefully with "No data".
