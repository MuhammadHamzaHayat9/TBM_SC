# -*- coding: utf-8 -*-
"""
Tire Building Scorecard — Dash Webapp (v3 — full Power BI rebuild)

A faithful Dash port of the "TB ScoreCard" Power BI report. The Power BI
report has 13 pages organised into two mirror-image domains — CONFECTION
(1st Step) and FINISHING (2nd Step) — plus a shared Uniformity focus page:

    Confection ScoreCard   Finishing ScoreCard
    Conf C1P Leak Details  Fin C1P Leak Details
    Conf BC Details        Fin BC Details
    Conf AC Details        Fin AC Details
    Conf UNIF Details      Fin UNIF Details
    Conf Rankings          Fin Rankings
    Uniformity Non-1st Focus (shared)

Every ScoreCard page carries: KPI cards (Tires, Counter Verifier %, Before
Cure %, After Cure %, Uniformity RFT), Counter-Verifier / Before-Cure /
After-Cure donuts, a Uniformity RFT gauge, a "Previous Weeks" combo chart,
and two leaderboards (Total Quality + NC Scrap). Click an operator name on
any leaderboard / ranking table to drill the whole app to that operator.

Paste into the Python tab of a Dataiku Code Webapp (Dash). The webapp `app`
object is provided by the Dataiku backend.

To wire the Finishing domain, point the dataset names in DOMAINS["Finishing"]
at your real 2nd-Step datasets. Any dataset that isn't built yet simply
renders "No data" — the rest of the app keeps working.
"""

import dataiku
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, State, ALL, ctx, no_update

# ============================================================
# 0. DOMAIN CONFIG  (Confection = 1st Step, Finishing = 2nd Step)
# ============================================================
DOMAINS = {
    "Confection": {
        "label":  "Confection — 1st Step",
        "tires":  "TIRES_BUILT",
        "prod":   "fact_first_step",
        "bc":     "fact_conf_bc",
        "ac":     "fact_conf_ac",
        "cv":     "fact_counter_verifier",
        "uni":    "fact_uniformity",
        "scrap":  "fact_nc_scrap",
        "top":    "agg_top_performers",
    },
    "Finishing": {
        "label":  "Finishing — 2nd Step",
        "tires":  "TIRES_BUILT",
        # 2nd-Step datasets built by the compute_fact_fin_* / compute_fact_second_step
        # recipes. Any dataset not built yet simply renders "No data".
        "prod":   "fact_second_step",
        "bc":     "fact_fin_bc",
        "ac":     "fact_fin_ac",
        "cv":     "fact_fin_counter_verifier",
        "uni":    "fact_uniformity_fin",   # uniformity keyed on the finishing operator
        "scrap":  "fact_nc_scrap",
        "top":    "agg_top_performers_fin",
    },
}

# ============================================================
# 1. LOAD DATASETS  (LAZY — a dataset is read only when a page needs it)
# ============================================================
# The webapp backend has a limited memory / startup budget, so we never load
# every dataset up front. Each dataset is read + normalised at most once, the
# first time some page asks for it, then cached. Only the Confection
# production table is touched at startup, purely to build the filter dropdowns.
_RAW  = {}   # name -> raw dataframe (columns upper-cased)
_NORM = {}   # name -> normalised dataframe (OP_ID zero-padded, de-duped)

def _load_raw(name):
    if name not in _RAW:
        try:
            df = dataiku.Dataset(name).get_dataframe()
            df.columns = [c.upper() for c in df.columns]
        except Exception as e:
            print(f"[warn] dataset '{name}' not available: {e}")
            df = pd.DataFrame()
        _RAW[name] = df
    return _RAW[name]

# keep a backward-compatible alias
def load(name):
    return _load_raw(name)

def _norm_op_series(s):
    """Vectorised OP_ID normaliser: zero-pad to 6 chars, strip trailing '.0'."""
    txt = s.astype("string").str.strip()
    txt = txt.str.replace(r"\.0+$", "", regex=True)   # '12345.0' -> '12345'
    txt = txt.str.zfill(6)
    return txt.where(s.notna(), None)

def _load_norm(name):
    """Load + normalise a dataset once (OP_ID + uniformity de-dupe), then cache."""
    if name not in _NORM:
        df = _load_raw(name)
        if not df.empty:
            df = df.copy()
            if "OP_ID" in df.columns:
                df["OP_ID"] = _norm_op_series(df["OP_ID"])
            # uniformity arrives one row per test — keep one row per barcode
            if {"BARCODE", "TEST_DATE"}.issubset(df.columns):
                df = (df.sort_values(["BARCODE", "TEST_DATE"])
                        .drop_duplicates("BARCODE", keep="first"))
        _NORM[name] = df
    return _NORM[name]

def get(domain, key):
    """Return the normalised dataframe for a domain/role, e.g. get('Confection','bc')."""
    return _load_norm(DOMAINS[domain][key])

# Operator display names + filter option lists (built off Confection production).
# This is the ONLY dataset read at startup.
_PROD = get("Confection", "prod")
OP_NAME = {}
if not _PROD.empty and "OPERATOR_NAME" in _PROD.columns:
    OP_NAME = (_PROD.dropna(subset=["OPERATOR_NAME"])
                    .drop_duplicates("OP_ID")
                    .set_index("OP_ID")["OPERATOR_NAME"].to_dict())

def _opts(df, col, cast=None):
    if df.empty or col not in df.columns:
        return []
    vals = df[col].dropna().unique().tolist()
    if cast:
        try: vals = [cast(v) for v in vals]
        except Exception: pass
    return sorted(vals)

BU_OPTIONS   = _opts(_PROD, "BU")
CREW_OPTIONS = _opts(_PROD, "CREW", int)
WEEK_OPTIONS = _opts(_PROD, "PROD_WEEK", int)

# ============================================================
# 2. STYLES
# ============================================================
COLORS = {
    "bg":       "#F5F7FA",
    "card":     "#FFFFFF",
    "primary":  "#0033A0",
    "accent":   "#FFCC00",
    "danger":   "#E63946",
    "good":     "#2A9D8F",
    "muted":    "#6C757D",
    "sidebar":  "#0A1F44",
}
CARD = {"backgroundColor": COLORS["card"], "padding": "16px",
        "borderRadius": "10px", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)",
        "margin": "8px"}

# Page registry: (page_id, sidebar label, domain, kind)
PAGES = [
    ("conf_score",   "📋 ScoreCard",         "Confection", "scorecard"),
    ("conf_cv",      "💧 C1P Leak Details",  "Confection", "cv"),
    ("conf_bc",      "🔵 BC Details",        "Confection", "bc"),
    ("conf_ac",      "🟠 AC Details",        "Confection", "ac"),
    ("conf_uni",     "⚙️ UNIF Details",      "Confection", "uni"),
    ("conf_rank",    "🏅 Rankings",          "Confection", "rankings"),
    ("fin_score",    "📋 ScoreCard",         "Finishing",  "scorecard"),
    ("fin_cv",       "💧 C1P Leak Details",  "Finishing",  "cv"),
    ("fin_bc",       "🔵 BC Details",        "Finishing",  "bc"),
    ("fin_ac",       "🟠 AC Details",        "Finishing",  "ac"),
    ("fin_uni",      "⚙️ UNIF Details",      "Finishing",  "uni"),
    ("fin_rank",     "🏅 Rankings",          "Finishing",  "rankings"),
    ("unif_focus",   "🔬 Uniformity Non-1st Focus", "Confection", "unif_focus"),
]
PAGE_MAP = {p[0]: p for p in PAGES}

# ============================================================
# 3. FILTER HELPERS
# ============================================================
def apply_filters(df, bus, crews, weeks, op_id):
    if df.empty:
        return df
    d = df
    if bus and "BU" in d.columns:                d = d[d["BU"].isin(bus)]
    if crews and "CREW" in d.columns:            d = d[d["CREW"].isin(crews)]
    if weeks and "PROD_WEEK" in d.columns:       d = d[d["PROD_WEEK"].isin(weeks)]
    if op_id and "OP_ID" in d.columns:           d = d[d["OP_ID"] == str(op_id)]
    return d

def domain_frames(domain, bus, crews, weeks, op_id):
    out = {}
    for key in ("prod", "bc", "ac", "cv", "uni", "scrap"):
        out[key] = apply_filters(get(domain, key), bus, crews, weeks, op_id)
    return out

# ============================================================
# 4. VISUAL BUILDERS
# ============================================================
def kpi_tile(label, value, suffix="", color=None):
    color = color or COLORS["primary"]
    return html.Div(style=CARD, children=[
        html.Div(label, style={"color": COLORS["muted"], "fontSize": "12px",
                               "textTransform": "uppercase", "letterSpacing": "1px"}),
        html.Div(f"{value}{suffix}", style={"color": color, "fontSize": "30px",
                                            "fontWeight": "700", "marginTop": "6px"}),
    ])

def empty_fig(msg="No data", height=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16, color=COLORS["muted"]))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig

def make_donut(df, label_col, value_col=None, dropna_col=None, height=300):
    if df.empty or label_col not in df.columns:
        return empty_fig(height=height)
    d = df.copy()
    if dropna_col and dropna_col in d.columns:
        d = d.dropna(subset=[dropna_col])
    if value_col and value_col in d.columns:
        grp = d.groupby(label_col)[value_col].sum()
    else:
        grp = d.groupby(label_col).size()
    grp = grp.sort_values(ascending=False).head(10)
    if grp.empty:
        return empty_fig(height=height)
    fig = go.Figure(data=[go.Pie(
        labels=grp.index.astype(str), values=grp.values, hole=0.55, textinfo="percent",
        hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>")])
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=height, showlegend=True,
                      legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)),
                      annotations=[dict(text=f"{int(grp.sum()):,}", x=0.5, y=0.5,
                                        font_size=16, showarrow=False)])
    return fig

def gauge_fig(pct, title="Uniformity RFT", target=90, height=260):
    good = pct >= target
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(pct, 1),
        number={"suffix": "%"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": COLORS["good"] if good else COLORS["danger"]},
               "threshold": {"line": {"color": COLORS["primary"], "width": 3},
                             "thickness": 0.75, "value": target}}))
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=10, b=10))
    return fig

def op_link(op_id, name):
    return html.A(name, id={"type": "op-link", "index": str(op_id)}, n_clicks=0,
                  style={"color": COLORS["primary"], "cursor": "pointer",
                         "textDecoration": "underline"})

def styled_table(header, rows):
    thead = html.Tr([html.Th(h, style={"padding": "6px", "textAlign": "left"}) for h in header],
                    style={"backgroundColor": COLORS["primary"], "color": "white",
                           "position": "sticky", "top": 0})
    return html.Table([thead] + rows,
                      style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

# ---------- Counter-Verifier metrics ----------
def cv_metrics(cv):
    if cv.empty:
        return 0.0, 0.0, 0.0
    total = float(len(cv))
    leaks = float(cv["IS_LEAK"].sum()) if "IS_LEAK" in cv.columns else 0.0
    pct = (leaks / total * 100) if total else 0.0
    return total, leaks, pct

def uni_metrics(uni):
    if uni.empty:
        return 0.0, 0.0, 0.0
    total = float(uni["BARCODE"].nunique()) if "BARCODE" in uni.columns else float(len(uni))
    rft = float(uni["IS_RFT"].sum()) if "IS_RFT" in uni.columns else 0.0
    pct = (rft / total * 100) if total else 0.0
    return total, rft, pct

# ============================================================
# 5. PAGE: SCORECARD
# ============================================================
def page_scorecard(domain, bus, crews, weeks, op_id):
    f = domain_frames(domain, bus, crews, weeks, op_id)
    prod, bc, ac, cv, uni, scrap = f["prod"], f["bc"], f["ac"], f["cv"], f["uni"], f["scrap"]
    tcol = DOMAINS[domain]["tires"]

    tires   = float(prod[tcol].sum()) if (not prod.empty and tcol in prod.columns) else 0.0
    bc_cnt  = float(bc.dropna(subset=["CQ_CODE_STR"]).shape[0]) if ("CQ_CODE_STR" in bc.columns) else 0.0
    ac_cnt  = float(ac.dropna(subset=["CQ_CODE_STR"]).shape[0]) if ("CQ_CODE_STR" in ac.columns) else 0.0
    _, _, cv_pct   = cv_metrics(cv)
    _, _, rft_pct  = uni_metrics(uni)
    bc_pct = (bc_cnt / tires * 100) if tires else 0
    ac_pct = (ac_cnt / tires * 100) if tires else 0

    kpis = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)",
                           "gap": "8px"}, children=[
        kpi_tile("Tires Built",      f"{tires:,.0f}", color=COLORS["primary"]),
        kpi_tile("Counter Verifier %", f"{cv_pct:.2f}", "%",
                 color=COLORS["danger"] if cv_pct > 8 else COLORS["good"]),
        kpi_tile("Before Cure %",    f"{bc_pct:.2f}", "%",
                 color=COLORS["danger"] if bc_pct > 5 else COLORS["good"]),
        kpi_tile("After Cure %",     f"{ac_pct:.2f}", "%",
                 color=COLORS["danger"] if ac_pct > 5 else COLORS["good"]),
        kpi_tile("Uniformity RFT",   f"{rft_pct:.1f}", "%",
                 color=COLORS["good"] if rft_pct >= 90 else COLORS["danger"]),
    ])

    # Donuts: Counter Verifier (by type/station), Before Cure, After Cure
    cv_label = "CV_TYPE" if "CV_TYPE" in cv.columns else (
               "COUNTER_VERIFIER_ID" if "COUNTER_VERIFIER_ID" in cv.columns else None)
    donut_cv = make_donut(cv, cv_label) if cv_label else empty_fig()
    donut_bc = make_donut(bc, "CQ_DESCRIPTION", dropna_col="CQ_CODE_STR")
    donut_ac = make_donut(ac, "CQ_DESCRIPTION", dropna_col="CQ_CODE_STR")

    donut_row = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)",
                                "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[html.H4("Counter Verifier Results", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_cv, config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("Before Cure Results", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_bc, config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("After Cure Results", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_ac, config={"displayModeBar": False})]),
    ])

    # Uniformity gauge + weekly combo trend
    gauge = dcc.Graph(figure=gauge_fig(rft_pct), config={"displayModeBar": False})
    trend = dcc.Graph(figure=weekly_trend_fig(prod, bc, ac, uni, tcol),
                      config={"displayModeBar": False})
    mid_row = html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 2fr",
                              "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[html.H4("Uniformity RFT", style={"margin": "0 0 8px 0"}), gauge]),
        html.Div(style=CARD, children=[html.H4("Previous Weeks Results", style={"margin": "0 0 8px 0"}), trend]),
    ])

    # Leaderboards
    lead_row = html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                               "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[html.H4("🏆 Total Quality — Top Performers", style={"margin": "0 0 8px 0"}),
                 leaderboard_quality(domain, bus, crews, op_id)]),
        html.Div(style=CARD, children=[html.H4("♻️ Top Performers — NC Scrap", style={"margin": "0 0 8px 0"}),
                 leaderboard_scrap(scrap)]),
    ])

    return html.Div([kpis, donut_row, mid_row, lead_row])

def weekly_trend_fig(prod, bc, ac, uni, tcol):
    keys = ["PROD_YEAR", "PROD_WEEK"]
    if prod.empty or not set(keys).issubset(prod.columns):
        return empty_fig("No weekly data", height=340)
    p_w = prod.groupby(keys, dropna=False)[tcol].sum().reset_index()
    def cnt(df, name):
        if df.empty or "CQ_CODE_STR" not in df.columns:
            return pd.DataFrame(columns=keys + [name])
        return (df.dropna(subset=["CQ_CODE_STR"]).groupby(keys, dropna=False)
                  .size().reset_index(name=name))
    bc_w, ac_w = cnt(bc, "BC_COUNT"), cnt(ac, "AC_COUNT")
    if not uni.empty and "IS_RFT" in uni.columns and set(keys).issubset(uni.columns):
        uni_w = (uni.groupby(keys, dropna=False)
                    .agg(UNI_TESTED=("BARCODE", "nunique"), UNI_RFT=("IS_RFT", "sum"))
                    .reset_index())
    else:
        uni_w = pd.DataFrame(columns=keys + ["UNI_TESTED", "UNI_RFT"])

    t = p_w.merge(bc_w, on=keys, how="left").merge(ac_w, on=keys, how="left").merge(uni_w, on=keys, how="left")
    for c in ["BC_COUNT", "AC_COUNT", "UNI_TESTED", "UNI_RFT"]:
        if c in t.columns: t[c] = t[c].fillna(0)
    t["BC_PCT"]  = (t.get("BC_COUNT", 0) / t[tcol].replace(0, float("nan")) * 100).round(3)
    t["AC_PCT"]  = (t.get("AC_COUNT", 0) / t[tcol].replace(0, float("nan")) * 100).round(3)
    t["RFT_PCT"] = (t.get("UNI_RFT", 0) / t.get("UNI_TESTED", pd.Series(0)).replace(0, float("nan")) * 100).round(3)
    t["WEEK_LABEL"] = (t["PROD_YEAR"].astype("Int64").astype(str)
                       + "-W" + t["PROD_WEEK"].astype("Int64").astype(str).str.zfill(2))
    t = t.sort_values(keys)

    fig = go.Figure()
    fig.add_bar(x=t["WEEK_LABEL"], y=t[tcol], name="Tires Built",
                marker_color=COLORS["primary"], opacity=0.55, yaxis="y1")
    fig.add_scatter(x=t["WEEK_LABEL"], y=t["BC_PCT"], name="BC%", mode="lines+markers",
                    line=dict(color=COLORS["danger"], width=3), yaxis="y2")
    fig.add_scatter(x=t["WEEK_LABEL"], y=t["AC_PCT"], name="AC%", mode="lines+markers",
                    line=dict(color=COLORS["accent"], width=3), yaxis="y2")
    fig.add_scatter(x=t["WEEK_LABEL"], y=t["RFT_PCT"], name="RFT%", mode="lines+markers",
                    line=dict(color=COLORS["good"], width=3), yaxis="y2")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=340,
                      yaxis=dict(title="Tires Built"),
                      yaxis2=dict(title="Quality %", overlaying="y", side="right"),
                      xaxis=dict(title="Week"), legend=dict(orientation="h", y=-0.25))
    return fig

def leaderboard_quality(domain, bus, crews, op_id):
    top = get(domain, "top")
    if top.empty:
        return html.Div("No leaderboard data", style={"color": COLORS["muted"]})
    d = top.copy()
    if "RANKABLE" in d.columns:       d = d[d["RANKABLE"] == True]
    if "OPERATOR_NAME" in d.columns:  d = d[d["OPERATOR_NAME"].notna()]
    if bus and "BU" in d.columns:     d = d[d["BU"].isin(bus)]
    if crews and "CREW" in d.columns: d = d[d["CREW"].isin(crews)]
    if op_id and "OP_ID" in d.columns:d = d[d["OP_ID"] == str(op_id)]
    if "QUALITY_SCORE" in d.columns:  d = d.sort_values("QUALITY_SCORE").head(10)
    else:                             d = d.head(10)
    rows = []
    for _, r in d.iterrows():
        rft = f"{r['RFT_PCT']:.0f}%" if pd.notna(r.get("RFT_PCT")) else "—"
        rows.append(html.Tr([
            html.Td(int(r["RANK"]) if pd.notna(r.get("RANK")) else "", style={"padding": "6px"}),
            html.Td(op_link(r["OP_ID"], r["OPERATOR_NAME"]), style={"padding": "6px"}),
            html.Td(r.get("BU", ""), style={"padding": "6px"}),
            html.Td(int(r["CREW"]) if pd.notna(r.get("CREW")) else "", style={"padding": "6px"}),
            html.Td(f"{int(r['TIRES_BUILT']):,}" if pd.notna(r.get("TIRES_BUILT")) else "—",
                    style={"padding": "6px"}),
            html.Td(rft, style={"padding": "6px"}),
            html.Td(f"{r['QUALITY_SCORE']:.1f}" if pd.notna(r.get("QUALITY_SCORE")) else "—",
                    style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    return styled_table(["#", "Operator", "BU", "Crew", "Tires", "RFT%", "Score"], rows)

def leaderboard_scrap(scrap):
    if scrap.empty or "OP_SCRAP_LBS_BY_TIRES" not in scrap.columns:
        return html.Div("No scrap data", style={"color": COLORS["muted"]})
    g = (scrap.groupby(["OP_ID", "OPERATOR_NAME"], dropna=False)
              .agg(SCRAP_LBS=("OP_SCRAP_LBS_BY_TIRES", "sum"),
                   SHIFTS=("PROD_DATE", "nunique"))
              .reset_index())
    g["NC_PER_SHIFT"] = (g["SCRAP_LBS"] / g["SHIFTS"].replace(0, float("nan"))).round(1)
    g = g.sort_values("SCRAP_LBS", ascending=False).head(10)
    rows = []
    for _, r in g.iterrows():
        name = r["OPERATOR_NAME"] if pd.notna(r.get("OPERATOR_NAME")) else str(r["OP_ID"])
        rows.append(html.Tr([
            html.Td(op_link(r["OP_ID"], name), style={"padding": "6px"}),
            html.Td(f"{r['SCRAP_LBS']:,.0f}", style={"padding": "6px"}),
            html.Td(f"{r['NC_PER_SHIFT']:.1f}" if pd.notna(r["NC_PER_SHIFT"]) else "—",
                    style={"padding": "6px"}),
            html.Td(int(r["SHIFTS"]) if pd.notna(r["SHIFTS"]) else "", style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    return styled_table(["Operator", "Scrap lbs", "NC/Shift", "Shifts"], rows)

# ============================================================
# 6. PAGE: DETAIL (CV / BC / AC / UNIF)
# ============================================================
def page_detail(domain, kind, bus, crews, weeks, op_id):
    f = domain_frames(domain, bus, crews, weeks, op_id)
    if kind == "cv":
        df = f["cv"]
        label = "CV_TYPE" if "CV_TYPE" in df.columns else "COUNTER_VERIFIER_ID"
        title = "Counter Verifier (C1P) Leak Details"
        group_cols = [c for c in ["COUNTER_VERIFIER_ID", "CV_TYPE"] if c in df.columns]
        chart = make_donut(df, label) if label in df.columns else empty_fig()
        chart_title = "Leaks by station / type"
        table = detail_breakdown_table(df, group_cols or [label] if label in df.columns else [])
    elif kind in ("bc", "ac"):
        df = f[kind].dropna(subset=["CQ_CODE_STR"]) if "CQ_CODE_STR" in f[kind].columns else f[kind]
        title = "Before Cure CQ Details" if kind == "bc" else "After Cure CQ Details"
        chart = make_donut(df, "CQ_DESCRIPTION", dropna_col="CQ_CODE_STR")
        chart_title = "CQ breakdown"
        table = detail_breakdown_table(df, [c for c in ["CQ_CODE_STR", "CQ_DESCRIPTION",
                                            "CQ_RELATES_TO", "CQ_TYPE_TIER"] if c in df.columns])
    else:  # uni
        df = f["uni"]
        title = "Uniformity Defect Details"
        chart = make_donut(df, "UNI_GRADE", dropna_col="UNI_GRADE") if "UNI_GRADE" in df.columns else empty_fig()
        chart_title = "Defects by grade"
        table = detail_breakdown_table(df, [c for c in ["UNI_GRADE", "TBM", "FINISHING_MACHINE"] if c in df.columns])

    return html.Div([
        html.Div(style=CARD, children=[html.H3(f"{DOMAINS[domain]['label']} — {title}",
                 style={"margin": "0 0 4px 0", "color": COLORS["primary"]})]),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                        "gap": "8px", "marginTop": "8px"}, children=[
            html.Div(style=CARD, children=[html.H4(chart_title, style={"margin": "0 0 8px 0"}),
                     dcc.Graph(figure=chart, config={"displayModeBar": False})]),
            html.Div(style={**CARD, "maxHeight": "420px", "overflowY": "auto"},
                     children=[html.H4("Breakdown", style={"margin": "0 0 8px 0"}), table]),
        ]),
    ])

def detail_breakdown_table(df, cols):
    if df.empty or not cols:
        return html.Div("No data", style={"color": COLORS["muted"]})
    g = df.groupby(cols, dropna=False).size().reset_index(name="COUNT")
    g = g.sort_values("COUNT", ascending=False).head(50)
    total = g["COUNT"].sum()
    rows = []
    for _, r in g.iterrows():
        cells = [html.Td(str(r[c]), style={"padding": "6px"}) for c in cols]
        cells.append(html.Td(f"{int(r['COUNT']):,}", style={"padding": "6px"}))
        cells.append(html.Td(f"{r['COUNT']/total*100:.1f}%", style={"padding": "6px"}))
        rows.append(html.Tr(cells, style={"borderBottom": "1px solid #eee"}))
    return styled_table([c.replace("_", " ").title() for c in cols] + ["Count", "% of total"], rows)

# ============================================================
# 7. PAGE: RANKINGS
# ============================================================
def page_rankings(domain, bus, crews, weeks, op_id, topn=10):
    top = get(domain, "top")
    if top.empty:
        return html.Div(style=CARD, children=[html.H3("No ranking data available",
                        style={"color": COLORS["muted"]})])
    d = top.copy()
    if "OPERATOR_NAME" in d.columns:  d = d[d["OPERATOR_NAME"].notna()]
    if bus and "BU" in d.columns:     d = d[d["BU"].isin(bus)]
    if crews and "CREW" in d.columns: d = d[d["CREW"].isin(crews)]
    if "QUALITY_SCORE" in d.columns:  d = d.sort_values("QUALITY_SCORE")
    d = d.head(topn)

    header = ["Operator", "Tires", "BC%", "AC%", "RFT%", "Scrap%", "Score"]
    rows = []
    for _, r in d.iterrows():
        def num(c, fmt):
            return fmt.format(r[c]) if pd.notna(r.get(c)) else "—"
        rows.append(html.Tr([
            html.Td(op_link(r["OP_ID"], r["OPERATOR_NAME"]), style={"padding": "6px"}),
            html.Td(num("TIRES_BUILT", "{:,.0f}"), style={"padding": "6px"}),
            html.Td(num("BC_PCT", "{:.2f}"), style={"padding": "6px"}),
            html.Td(num("AC_PCT", "{:.2f}"), style={"padding": "6px"}),
            html.Td(num("RFT_PCT", "{:.0f}"), style={"padding": "6px"}),
            html.Td(num("SCRAP_PCT", "{:.3f}"), style={"padding": "6px"}),
            html.Td(num("QUALITY_SCORE", "{:.1f}"), style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    table = styled_table(header, rows)

    def rank_bar(col, title, ascending):
        if col not in d.columns:
            return empty_fig(f"No {title}", height=300)
        s = d.dropna(subset=[col]).sort_values(col, ascending=ascending).head(topn)
        fig = go.Figure(go.Bar(x=s[col], y=s["OPERATOR_NAME"], orientation="h",
                               marker_color=COLORS["primary"]))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(autorange="reversed"), xaxis_title=title)
        return fig

    bars = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)",
                           "gap": "8px", "marginTop": "8px"}, children=[
        html.Div(style=CARD, children=[html.H4("Top RFT%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=rank_bar("RFT_PCT", "RFT%", False), config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("Lowest AC%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=rank_bar("AC_PCT", "AC%", True), config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("Lowest BC%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=rank_bar("BC_PCT", "BC%", True), config={"displayModeBar": False})]),
    ])

    return html.Div([
        html.Div(style={**CARD, "maxHeight": "360px", "overflowY": "auto"}, children=[
            html.H3(f"{DOMAINS[domain]['label']} — Operator Rankings (Top {topn})",
                    style={"margin": "0 0 8px 0", "color": COLORS["primary"]}), table]),
        bars,
    ])

# ============================================================
# 8. PAGE: UNIFORMITY NON-1ST FOCUS
# ============================================================
def page_unif_focus(domain, bus, crews, weeks, op_id):
    uni = apply_filters(get(domain, "uni"), bus, crews, weeks, op_id)
    grade_col = "TUO_GRADE" if "TUO_GRADE" in uni.columns else (
                "UNI_GRADE" if "UNI_GRADE" in uni.columns else None)
    if uni.empty or not grade_col:
        fig = empty_fig("No uniformity data", height=420)
    else:
        g = uni.dropna(subset=[grade_col]).groupby(grade_col).size().sort_values(ascending=False)
        fig = go.Figure(go.Bar(x=g.index.astype(str), y=g.values, marker_color=COLORS["primary"]))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis_title="Grade", yaxis_title="Count")
    return html.Div(style=CARD, children=[
        html.H3("Uniformity — Non-1st Focus", style={"margin": "0 0 8px 0", "color": COLORS["primary"]}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
    ])

# ============================================================
# 9. ROUTER
# ============================================================
def render_page(page_id, bus, crews, weeks, op_id, topn):
    pid, label, domain, kind = PAGE_MAP.get(page_id, PAGES[0])
    if kind == "scorecard":   return page_scorecard(domain, bus, crews, weeks, op_id)
    if kind == "rankings":    return page_rankings(domain, bus, crews, weeks, op_id, topn or 10)
    if kind == "unif_focus":  return page_unif_focus(domain, bus, crews, weeks, op_id)
    return page_detail(domain, kind, bus, crews, weeks, op_id)

# ============================================================
# 10. SIDEBAR + LAYOUT
# ============================================================
def sidebar():
    items = [html.Div("🏭 TB ScoreCard", style={"color": "white", "fontSize": "18px",
             "fontWeight": "700", "padding": "12px 16px"})]
    last_domain = None
    for pid, label, domain, kind in PAGES:
        if domain != last_domain and kind != "unif_focus":
            items.append(html.Div(DOMAINS[domain]["label"].upper(),
                         style={"color": COLORS["accent"], "fontSize": "11px",
                                "letterSpacing": "1px", "padding": "12px 16px 4px"}))
            last_domain = domain
        if kind == "unif_focus":
            items.append(html.Div("SHARED", style={"color": COLORS["accent"], "fontSize": "11px",
                         "letterSpacing": "1px", "padding": "12px 16px 4px"}))
        items.append(html.Button(label, id={"type": "nav", "page": pid}, n_clicks=0,
                     style={"display": "block", "width": "100%", "textAlign": "left",
                            "background": "transparent", "border": "none", "color": "#CBD5E1",
                            "padding": "8px 16px", "cursor": "pointer", "fontSize": "13px"}))
    return html.Div(items, style={"backgroundColor": COLORS["sidebar"], "width": "220px",
                                  "minHeight": "100vh", "flexShrink": 0})

app.layout = html.Div(style={"display": "flex", "fontFamily": "Segoe UI, Arial, sans-serif",
                             "backgroundColor": COLORS["bg"]}, children=[
    sidebar(),
    html.Div(style={"flex": 1, "padding": "16px", "minHeight": "100vh"}, children=[
        # Header + operator chip
        html.Div(style={"display": "flex", "alignItems": "center",
                        "justifyContent": "space-between", "marginBottom": "12px"}, children=[
            html.H2(id="page-title", style={"color": COLORS["primary"], "margin": 0}),
            html.Div(id="f-op-display", style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        ]),
        # Filters
        html.Div(style={**CARD, "display": "flex", "gap": "16px", "alignItems": "flex-end"}, children=[
            html.Div(style={"flex": 1}, children=[
                html.Label("Business Unit", style={"fontSize": "12px", "color": COLORS["muted"]}),
                dcc.Dropdown(id="f-bu", options=[{"label": b, "value": b} for b in BU_OPTIONS],
                             multi=True, placeholder="All BUs")]),
            html.Div(style={"flex": 1}, children=[
                html.Label("Crew", style={"fontSize": "12px", "color": COLORS["muted"]}),
                dcc.Dropdown(id="f-crew", options=[{"label": f"Crew {c}", "value": c} for c in CREW_OPTIONS],
                             multi=True, placeholder="All Crews")]),
            html.Div(style={"flex": 1}, children=[
                html.Label("Week", style={"fontSize": "12px", "color": COLORS["muted"]}),
                dcc.Dropdown(id="f-week", options=[{"label": f"W{w:02d}", "value": w} for w in WEEK_OPTIONS],
                             multi=True, placeholder="All Weeks")]),
            html.Div(style={"flex": 1}, children=[
                html.Label("Rankings Top N", style={"fontSize": "12px", "color": COLORS["muted"]}),
                dcc.Dropdown(id="f-topn", options=[{"label": f"Top {n}", "value": n} for n in (5, 10, 15, 20)],
                             value=10, clearable=False)]),
        ]),
        # Stores + page content
        dcc.Store(id="current-page", data="conf_score"),
        dcc.Store(id="f-op", data=None),
        html.Div(id="page-content", style={"marginTop": "12px"}),
    ]),
])

# ============================================================
# 11. CALLBACKS
# ============================================================
@app.callback(
    Output("current-page", "data"),
    Input({"type": "nav", "page": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def nav_click(_clicks):
    trig = ctx.triggered_id
    if isinstance(trig, dict) and trig.get("type") == "nav":
        if any(c and c > 0 for c in (_clicks or [])):
            return trig["page"]
    return no_update

@app.callback(
    Output("f-op", "data"),
    Input({"type": "op-link", "index": ALL}, "n_clicks"),
    Input("clear-op", "n_clicks"),
    prevent_initial_call=True,
)
def select_operator(_clicks, _clear):
    trig = ctx.triggered_id
    if trig == "clear-op":
        return None
    if isinstance(trig, dict) and trig.get("type") == "op-link":
        if any(c and c > 0 for c in (_clicks or [])):
            return trig["index"]
    return no_update

@app.callback(
    Output("f-op-display", "children"),
    Input("f-op", "data"),
)
def render_op_chip(op_id):
    if not op_id:
        return [html.Span("All operators", style={"color": COLORS["muted"], "fontSize": "13px"}),
                html.Button(id="clear-op", n_clicks=0, style={"display": "none"})]
    name = OP_NAME.get(op_id, op_id)
    return [
        html.Span(f"👤 {name}", style={"backgroundColor": COLORS["primary"], "color": "white",
                  "padding": "6px 10px", "borderRadius": "6px", "fontSize": "13px"}),
        html.Button("✕ Clear", id="clear-op", n_clicks=0,
                    style={"border": "none", "background": "transparent", "color": COLORS["danger"],
                           "cursor": "pointer", "fontSize": "12px"}),
    ]

@app.callback(
    Output("page-title", "children"),
    Output("page-content", "children"),
    Input("current-page", "data"),
    Input("f-bu", "value"),
    Input("f-crew", "value"),
    Input("f-week", "value"),
    Input("f-op", "data"),
    Input("f-topn", "value"),
)
def route(page_id, bus, crews, weeks, op_id, topn):
    pid, label, domain, kind = PAGE_MAP.get(page_id, PAGES[0])
    title = f"{DOMAINS[domain]['label']}  ·  {label.split(' ', 1)[-1]}" if kind != "unif_focus" \
            else "Uniformity — Non-1st Focus"
    return title, render_page(page_id, bus, crews, weeks, op_id, topn)
