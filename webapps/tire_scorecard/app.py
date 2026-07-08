# -*- coding: utf-8 -*-
"""
Tire Building Scorecard — Dash Webapp (v5 — Power BI look & feel)

Reads the small aggregate datasets produced by the Dataiku flow plus
fact_counter_verifier, and lays them out to mirror the "Operator Quality
Score Card" Power BI report:

  • centered title + last-refresh line
  • left card: Top Performers — NC Scrap
  • center: "Previous Weeks Results" combo chart (BC% / AC% bars + RFT% line)
  • right: "Total Quality — Top Performers" list + Rankings button
  • bottom row: Counter Verifier / Before Cure / After Cure donuts + Uniformity
    RFT gauge, each with a centre percentage and a 🙂/😐/☹️ status face

Tabs: ScoreCard · Counter Verifier · Rankings.
Filters: BU, Crew, Week, Operator (click any name to drill).

Paste into the Python tab of a Dataiku Code Webapp (Dash). `app` is provided
by the Dataiku backend.
"""

import datetime
import dataiku
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, ALL, ctx, no_update

# ============================================================
# 1. LOAD AGGREGATES  (small — safe to load once at startup)
# ============================================================
_CACHE = {}

def load(name):
    if name in _CACHE:
        return _CACHE[name]
    try:
        df = dataiku.Dataset(name).get_dataframe()
        df.columns = [c.upper() for c in df.columns]
    except Exception as e:
        print(f"[warn] dataset '{name}' not available: {e}")
        df = pd.DataFrame()
    _CACHE[name] = df
    return df

def norm_op_series(s):
    txt = s.astype("string").str.strip()
    txt = txt.str.replace(r"\.0+$", "", regex=True)
    txt = txt.str.zfill(6)
    return txt.where(s.notna(), None)

def load_all():
    """(Re)load every dataset into module globals. Called once at import and
    again by the Refresh button, so the webapp can pick up newly-built data
    without restarting the backend."""
    global TOP, UNI, DBC, DAC, DSC, TREND, CV, TOP_FIN, UNI_FIN, TREND_FIN
    global OPWK, OPWK_FIN, STEP_DS, OP_NAME, REFRESH
    _CACHE.clear()
    # --- 1st Step (Confection) aggregates ---
    TOP   = load("agg_top_performers")
    UNI   = load("agg_uniformity")
    DBC   = load("agg_donut_bc")
    DAC   = load("agg_donut_ac")
    DSC   = load("agg_donut_scrap")
    TREND = load("agg_weekly_trend")
    CV    = load("fact_counter_verifier")
    # --- 2nd Step (Finishing) aggregates (built by compute_*_fin recipes) ---
    TOP_FIN   = load("agg_top_performers_fin")
    UNI_FIN   = load("agg_uniformity_fin")
    TREND_FIN = load("agg_weekly_trend_fin")
    # --- operator x week building blocks (drive week-aware KPIs / leaderboards) ---
    OPWK     = load("agg_op_week")
    OPWK_FIN = load("agg_op_week_fin")

    for _df in (TOP, TOP_FIN, CV, OPWK, OPWK_FIN):
        if not _df.empty and "OP_ID" in _df.columns:
            _df["OP_ID"] = norm_op_series(_df["OP_ID"])

    STEP_DS = {
        "1": {"label": "1st Step — Confection", "relates": "Confection",
              "top": TOP,     "uni": UNI,     "trend": TREND,     "opwk": OPWK},
        "2": {"label": "2nd Step — Finishing",  "relates": "Finishing",
              "top": TOP_FIN, "uni": UNI_FIN, "trend": TREND_FIN, "opwk": OPWK_FIN},
    }
    OP_NAME = {}
    for _t in (TOP, TOP_FIN, OPWK, OPWK_FIN):
        if not _t.empty and {"OP_ID", "OPERATOR_NAME"}.issubset(_t.columns):
            OP_NAME.update(_t.dropna(subset=["OPERATOR_NAME"]).drop_duplicates("OP_ID")
                             .set_index("OP_ID")["OPERATOR_NAME"].to_dict())
    REFRESH = datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p")

load_all()

def sds(step):
    return STEP_DS.get(str(step) if step else "1", STEP_DS["1"])

def _uniq(df, col, cast=None):
    if df.empty or col not in df.columns:
        return []
    vals = df[col].dropna().unique().tolist()
    if cast:
        out = []
        for v in vals:
            try: out.append(cast(v))
            except Exception: pass
        vals = out
    return sorted(set(vals))

BU_OPTIONS   = sorted(set(_uniq(TOP, "BU")) | set(_uniq(TOP_FIN, "BU"))
                      | set(_uniq(OPWK, "BU")) | set(_uniq(OPWK_FIN, "BU")))
CREW_OPTIONS = sorted(set(_uniq(TOP, "CREW", int)) | set(_uniq(TOP_FIN, "CREW", int))
                      | set(_uniq(OPWK, "CREW", int)) | set(_uniq(OPWK_FIN, "CREW", int)))
WEEK_OPTIONS = sorted(set(_uniq(TREND, "PROD_WEEK", int)) | set(_uniq(TREND_FIN, "PROD_WEEK", int))
                      | set(_uniq(OPWK, "PROD_WEEK", int)) | set(_uniq(OPWK_FIN, "PROD_WEEK", int))
                      | set(_uniq(CV, "WEEK", int)))
REFRESH = datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p")

# ============================================================
# 2. STYLES  (palette lifted from the Power BI CY22SU11 theme)
# ============================================================
COLORS = {
    "bg": "#EEF1F6", "card": "#FFFFFF", "ink": "#1A1A2E",
    "blue": "#118DFF", "navy": "#12239E", "orange": "#E66C37",
    "good": "#1AAB40", "danger": "#D64550", "warn": "#D9B300",
    "muted": "#8A93A6", "btn": "#1565C0",
}
# Categorical order for CQ donuts (fixed order, never cycled)
CAT = ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#D9B300",
       "#D64550", "#197278", "#1AAB40", "#E044A7", "#744EC2"]
CARD = {"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "10px",
        "boxShadow": "0 1px 4px rgba(0,0,0,0.10)", "margin": "6px",
        # min-width:0 lets a card shrink inside grid/flex so a re-mounted Plotly
        # graph can't force the row to overflow (which used to push cards off-screen)
        "minWidth": 0}
# Every dcc.Graph uses this so graphs refit their container after a tab switch.
GRAPH_CFG = {"displayModeBar": False, "responsive": True}

# ============================================================
# 3. FILTER HELPERS
# ============================================================
def filt(df, bus, crews, weeks=None, op_id=None, drop_bu_na=False):
    if df.empty:
        return df
    d = df
    if drop_bu_na and "BU" in d.columns:
        d = d[d["BU"].notna()]
    if bus and "BU" in d.columns:
        d = d[d["BU"].isin(bus)]
    if crews and "CREW" in d.columns:
        d = d[d["CREW"].isin(crews)]
    if weeks:
        wcol = "PROD_WEEK" if "PROD_WEEK" in d.columns else ("WEEK" if "WEEK" in d.columns else None)
        if wcol:
            d = d[d[wcol].isin(weeks)]
    if op_id and "OP_ID" in d.columns:
        d = d[d["OP_ID"] == str(op_id)]
    return d

def _nrm(s):
    rng = s.max() - s.min()
    return (s - s.min()) / rng if rng else 0

def op_rollup(step, bus, crews, weeks, op_id):
    """Roll the operator x week table up to one row per operator for the current
    filters, recomputing pcts + QUALITY_SCORE + RANK live (so Week/Crew/BU all
    apply). Falls back to the period-total agg_top_performers if agg_op_week
    hasn't been built yet."""
    cfg = sds(step)
    src = cfg.get("opwk")
    if src is None or src.empty:
        # fallback: pre-computed period leaderboard (no week grain)
        return filt(cfg["top"], bus, crews, op_id=op_id)
    d = filt(src, bus, crews, weeks, op_id)
    if d.empty:
        return d
    g = (d.groupby(["OP_ID", "OPERATOR_NAME", "BU", "CREW"], dropna=False)
           .agg(TIRES_BUILT=("TIRES_BUILT", "sum"), SHIFTS_WORKED=("SHIFTS", "sum"),
                BC_COUNT=("BC_COUNT", "sum"), AC_COUNT=("AC_COUNT", "sum"),
                SCRAP_LBS=("SCRAP_LBS", "sum"), UNI_TESTED=("UNI_TESTED", "sum"),
                UNI_RFT=("UNI_RFT", "sum"))
           .reset_index())
    den = g["TIRES_BUILT"].replace(0, float("nan"))
    g["BC_PCT"]    = (g["BC_COUNT"] / den * 100).round(3)
    g["AC_PCT"]    = (g["AC_COUNT"] / den * 100).round(3)
    g["SCRAP_PCT"] = (g["SCRAP_LBS"] / den).round(3)
    g["RFT_PCT"]   = (g["UNI_RFT"] / g["UNI_TESTED"].replace(0, float("nan")) * 100).round(3)
    g["RANKABLE"]  = g["TIRES_BUILT"] >= 100
    g["QUALITY_SCORE"] = ((_nrm(g["BC_PCT"].fillna(0)) + _nrm(g["AC_PCT"].fillna(0))
                           + _nrm(g["SCRAP_PCT"].fillna(0)) + _nrm((100 - g["RFT_PCT"]).fillna(0)))
                          / 4 * 100).round(2)
    g["RANK"] = g["QUALITY_SCORE"].where(g["RANKABLE"]).rank(method="min")
    return g

# ============================================================
# 4. VISUAL HELPERS
# ============================================================
def face(value, good_low=True, ok=0, bad=0):
    """Status face: 🙂 good / 😐 warning / ☹️ bad."""
    if value is None or (isinstance(value, float) and value != value):
        return "•"
    if good_low:
        return "🙂" if value <= ok else ("😐" if value <= bad else "☹️")
    return "🙂" if value >= ok else ("😐" if value >= bad else "☹️")

def empty_fig(msg="No data", height=250):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, showarrow=False,
                       font=dict(size=15, color=COLORS["muted"]))
    fig.update_layout(height=height, margin=dict(l=6, r=6, t=6, b=6),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def donut(labels, values, colors, center_text="", center_color=None, height=250):
    if len(values) == 0 or float(sum(values)) == 0:
        return empty_fig(height=height)
    fig = go.Figure(go.Pie(
        labels=[str(l) for l in labels], values=list(values), hole=0.66,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        sort=False, textinfo="percent", textposition="outside",
        hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>"))
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True, legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(text=center_text, x=0.5, y=0.5, showarrow=False,
                          font=dict(size=26, color=center_color or COLORS["ink"], family="Segoe UI"))])
    return fig

def gauge(pct, target=90, height=250):
    good = pct >= target
    col = COLORS["good"] if good else COLORS["danger"]
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(pct, 1),
        number={"suffix": "%", "font": {"size": 34, "color": col}},
        gauge={"shape": "angular",
               "axis": {"range": [0, 100], "tickvals": [0, 100], "ticksuffix": "%", "tickfont": {"size": 10}},
               "bar": {"color": col, "thickness": 0.75},
               "bgcolor": "#ECEFF3", "borderwidth": 0}))
    fig.update_layout(height=height, margin=dict(l=40, r=40, t=20, b=8),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

def cat_counts(df, dim_cols, value_col, cap=6):
    """Group by the first dim column that has >=2 real categories; cap the rest into 'Other'."""
    if df.empty or value_col not in df.columns:
        return [], []
    g = None
    for dim in dim_cols:
        if dim not in df.columns:
            continue
        d = df.dropna(subset=[dim]).copy()
        if d.empty:
            continue
        d[dim] = d[dim].astype("string")
        cur = d.groupby(dim)[value_col].sum().sort_values(ascending=False)
        if g is None:
            g = cur
        if cur.index.nunique() >= 2:      # prefer a field with real variety
            g = cur
            break
    if g is None or g.empty:
        return [], []
    if len(g) > cap:
        other = g.iloc[cap:].sum()
        g = g.iloc[:cap]
        if other > 0:
            g = pd.concat([g, pd.Series({"Other": other})])
    return list(g.index), list(g.values)

def by_relates(df, relates):
    """Keep only rows whose CQ_RELATES_TO matches the step; no-op if the split isn't present."""
    if df.empty or "CQ_RELATES_TO" not in df.columns or not relates:
        return df
    sub = df[df["CQ_RELATES_TO"].astype("string").str.strip().str.casefold() == relates.casefold()]
    return sub if not sub.empty else df   # fall back to all if this step has no tagged rows

def op_chip_link(op_id, name, color):
    return html.A(name, id={"type": "op-link", "index": str(op_id)}, n_clicks=0,
                  style={"color": color, "cursor": "pointer", "fontWeight": "700",
                         "textDecoration": "none"})

def nav_button(label, to):
    return html.Button(label, id={"type": "navbtn", "to": to}, n_clicks=0,
                       style={"backgroundColor": COLORS["btn"], "color": "white", "border": "none",
                              "borderRadius": "4px", "padding": "6px 18px", "cursor": "pointer",
                              "fontSize": "12px", "fontWeight": "600"})

def styled_table(header, rows, max_h=None):
    thead = html.Tr([html.Th(h, style={"padding": "6px", "textAlign": "left"}) for h in header],
                    style={"backgroundColor": COLORS["navy"], "color": "white"})
    tbl = html.Table([thead] + rows,
                     style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})
    return html.Div(tbl, style={"maxHeight": max_h, "overflowY": "auto"}) if max_h else tbl

def metric_card(face_emoji, title, figure):
    return html.Div(style=CARD, children=[
        html.Div([html.Span(face_emoji, style={"fontSize": "20px", "marginRight": "6px"}),
                  html.Span(title, style={"fontWeight": "600", "color": COLORS["ink"]})],
                 style={"textAlign": "center", "marginBottom": "2px"}),
        dcc.Graph(figure=figure, config=GRAPH_CFG),
    ])

# ============================================================
# 5. TAB: SCORECARD  (Power BI layout)
# ============================================================
def page_scorecard(step, bus, crews, weeks, op_id, topn=10):
    cfg = sds(step); relates = cfg["relates"]
    t = op_rollup(step, bus, crews, weeks, op_id)

    def s(col):
        return float(t[col].sum()) if (not t.empty and col in t.columns) else 0.0
    tires = s("TIRES_BUILT"); bc = s("BC_COUNT"); ac = s("AC_COUNT")
    uni_tested = s("UNI_TESTED"); uni_rft = s("UNI_RFT")
    cvf   = filt(CV, bus, crews, weeks, op_id)
    cv_leaks = float(cvf["IS_LEAK"].sum()) if (not cvf.empty and "IS_LEAK" in cvf.columns) else 0.0
    cv_ok    = float(len(cvf)) - cv_leaks
    cv_pct   = (cv_leaks / len(cvf) * 100) if len(cvf) else 0.0
    bc_pct   = (bc / tires * 100) if tires else 0
    ac_pct   = (ac / tires * 100) if tires else 0
    rft_pct  = (uni_rft / uni_tested * 100) if uni_tested else 0

    # ---- Bottom donuts / gauge (CQ donuts split by step via CQ_RELATES_TO) ----
    cv_fig = donut(["OK", "Leak"], [cv_ok, cv_leaks], [COLORS["good"], COLORS["danger"]],
                   center_text=f"{cv_pct:.1f}%", center_color=COLORS["danger"] if cv_pct > 8 else COLORS["good"])
    dbc_s = by_relates(filt(DBC, bus, crews, weeks, drop_bu_na=True), relates)
    dac_s = by_relates(filt(DAC, bus, crews, weeks, drop_bu_na=True), relates)
    bl, bv = cat_counts(dbc_s, ["CQ_TYPE_TIER", "CQ_DESCRIPTION", "CQ_CODE_STR"], "CQ_COUNT")
    bc_fig = donut(bl, bv, CAT, center_text=f"{bc_pct:.2f}%", center_color=COLORS["danger"])
    al, av = cat_counts(dac_s, ["CQ_TYPE_TIER", "CQ_DESCRIPTION", "CQ_CODE_STR"], "CQ_COUNT")
    ac_fig = donut(al, av, CAT, center_text=f"{ac_pct:.2f}%", center_color=COLORS["danger"])
    uni_fig = gauge(rft_pct)

    bottom = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)",
                             "gap": "6px", "marginTop": "8px"}, children=[
        metric_card(face(cv_pct, True, 3, 8),   "Counter Verifier Results", cv_fig),
        metric_card(face(bc_pct, True, 0.5, 2), "Before Cure Results",      bc_fig),
        metric_card(face(ac_pct, True, 5, 20),  "After Cure Results",       ac_fig),
        metric_card(face(rft_pct, False, 95, 90), "Uniformity RFT",         uni_fig),
    ])

    # ---- Top row: NC scrap | combo | performers ----
    top_row = html.Div(style={"display": "grid", "gridTemplateColumns": "0.9fr 2.5fr 1.1fr",
                              "gap": "6px"}, children=[
        html.Div(style=CARD, children=[
            html.H4("Top Performers — NC Scrap", style={"margin": "0 0 8px 0", "textAlign": "center",
                    "color": COLORS["ink"]}),
            nc_scrap_panel(step, bus, crews, weeks, op_id, topn)]),
        html.Div(style=CARD, children=[
            html.H4("Previous Weeks Results", style={"margin": "0 0 4px 0", "textAlign": "center",
                    "color": COLORS["ink"]}),
            dcc.Graph(figure=trend_fig(step, bus, crews, weeks, op_id), config=GRAPH_CFG)]),
        html.Div(style=CARD, children=[
            html.H4("Total Quality — Top Performers", style={"margin": "0 0 8px 0", "textAlign": "center",
                    "color": COLORS["ink"]}),
            quality_panel(step, bus, crews, weeks, op_id, topn),
            html.Div(nav_button("Rankings ▸", "rank"), style={"textAlign": "center", "marginTop": "10px"})]),
    ])
    return html.Div([top_row, bottom])

def quality_panel(step, bus, crews, weeks, op_id, topn=6):
    d = op_rollup(step, bus, crews, weeks, op_id)
    if d.empty:
        return html.Div("No data", style={"color": COLORS["muted"]})
    if "RANKABLE" in d.columns:
        d = d[d["RANKABLE"] == True]
    d = d.dropna(subset=["OPERATOR_NAME"]) if "OPERATOR_NAME" in d.columns else d
    sort_col = "QUALITY_SCORE" if "QUALITY_SCORE" in d.columns else "RANK"
    d = d.sort_values(sort_col).head(topn)
    items = []
    for _, r in d.iterrows():
        q = f"{r['QUALITY_SCORE']:.2f}%" if pd.notna(r.get("QUALITY_SCORE")) else "—"
        tr = f"{int(r['TIRES_BUILT']):,}" if pd.notna(r.get("TIRES_BUILT")) else "—"
        items.append(html.Div(style={"borderBottom": "1px solid #EEF1F6", "padding": "5px 2px"}, children=[
            op_chip_link(r["OP_ID"], r["OPERATOR_NAME"], COLORS["good"]),
            html.Div([html.B(q), html.Span("  Total Quality", style={"color": COLORS["muted"], "fontSize": "11px"})],
                     style={"fontSize": "13px"}),
            html.Div([html.B(tr), html.Span("  Total Tires", style={"color": COLORS["muted"], "fontSize": "11px"})],
                     style={"fontSize": "12px"}),
        ]))
    return html.Div(items, style={"maxHeight": "300px", "overflowY": "auto"})

def nc_scrap_panel(step, bus, crews, weeks, op_id, topn=6):
    d = op_rollup(step, bus, crews, weeks, op_id)
    if d.empty or "SCRAP_LBS" not in d.columns:
        return html.Div("No data", style={"color": COLORS["muted"]})
    d = d.dropna(subset=["OPERATOR_NAME"]).sort_values("SCRAP_LBS", ascending=False).head(topn)
    items = []
    for _, r in d.iterrows():
        lbs = f"{r['SCRAP_LBS']:,.1f}" if pd.notna(r.get("SCRAP_LBS")) else "—"
        per = f"{r['SCRAP_PCT']:.3f}" if pd.notna(r.get("SCRAP_PCT")) else "—"
        sh  = f"{int(r['SHIFTS_WORKED'])}" if pd.notna(r.get("SHIFTS_WORKED")) else "—"
        items.append(html.Div(style={"borderBottom": "1px solid #EEF1F6", "padding": "5px 2px"}, children=[
            op_chip_link(r["OP_ID"], r["OPERATOR_NAME"], COLORS["danger"]),
            html.Div([html.B(lbs), html.Span("  Scrap lbs", style={"color": COLORS["muted"], "fontSize": "11px"})],
                     style={"fontSize": "13px"}),
            html.Div([html.B(per), html.Span("  lbs / tire", style={"color": COLORS["muted"], "fontSize": "11px"}),
                      html.Span(f"   {sh} shifts", style={"color": COLORS["muted"], "fontSize": "11px"})],
                     style={"fontSize": "12px"}),
        ]))
    return html.Div(items, style={"maxHeight": "300px", "overflowY": "auto"})

def trend_fig(step, bus, crews, weeks, op_id):
    cfg = sds(step)
    keys = ["PROD_YEAR", "PROD_WEEK"]
    src = cfg.get("opwk")
    if src is not None and not src.empty:
        # Crew/Operator-aware trend straight from the operator x week table
        d = filt(src, bus, crews, weeks, op_id)
        if d.empty:
            return empty_fig("No trend data", height=330)
        g = d.groupby(keys, dropna=False).agg(
            TIRES=("TIRES_BUILT", "sum"), BC=("BC_COUNT", "sum"), AC=("AC_COUNT", "sum"),
            UT=("UNI_TESTED", "sum"), UR=("UNI_RFT", "sum")).reset_index()
        g["BC_PCT"]  = (g["BC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
        g["AC_PCT"]  = (g["AC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
        g["RFT_PCT"] = (g["UR"] / g["UT"].replace(0, float("nan")) * 100).round(2)
    else:
        # Fallback: pre-built weekly-trend + uniformity aggregates (no crew grain)
        TR = cfg["trend"]
        if TR.empty:
            return empty_fig("No trend data", height=330)
        d = TR.copy()
        d = d[d["BU"].isin(bus)] if bus else (d[d["BU"] == "ALL"] if (d["BU"] == "ALL").any() else d)
        if weeks and "PROD_WEEK" in d.columns:
            d = d[d["PROD_WEEK"].isin(weeks)]
        if d.empty:
            return empty_fig("No trend data", height=330)
        g = d.groupby(keys, dropna=False).agg(
            TIRES=("TIRES_BUILT", "sum"), BC=("BC_COUNT", "sum"), AC=("AC_COUNT", "sum")).reset_index()
        g["BC_PCT"] = (g["BC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
        g["AC_PCT"] = (g["AC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
        ug = filt(cfg["uni"], bus, None, weeks)
        if not ug.empty and {"RFT_COUNT", "TIRES_TESTED"}.issubset(ug.columns):
            uw = ug.groupby(keys, dropna=False).agg(R=("RFT_COUNT", "sum"), T=("TIRES_TESTED", "sum")).reset_index()
            uw["RFT_PCT"] = (uw["R"] / uw["T"].replace(0, float("nan")) * 100).round(2)
            g = g.merge(uw[keys + ["RFT_PCT"]], on=keys, how="left")
        else:
            g["RFT_PCT"] = float("nan")
    g["WK"] = ("W" + g["PROD_WEEK"].astype("Int64").astype(str).str.zfill(2))
    g = g.sort_values(keys)

    fig = go.Figure()
    fig.add_bar(x=g["WK"], y=g["BC_PCT"], name="BC CQ %", marker_color=COLORS["blue"], yaxis="y1")
    fig.add_bar(x=g["WK"], y=g["AC_PCT"], name="AC CQ %", marker_color=COLORS["navy"], yaxis="y1")
    fig.add_scatter(x=g["WK"], y=g["RFT_PCT"], name="RFT %", mode="lines+markers",
                    line=dict(color=COLORS["orange"], width=3), marker=dict(size=8), yaxis="y2")
    rft_min = float(pd.to_numeric(g["RFT_PCT"], errors="coerce").min()) if g["RFT_PCT"].notna().any() else 90
    fig.update_layout(
        barmode="group", height=330, margin=dict(l=10, r=10, t=6, b=6),
        yaxis=dict(title="BC % / AC %", showgrid=True, gridcolor="#F0F2F6"),
        yaxis2=dict(title="RFT %", overlaying="y", side="right",
                    range=[max(0, rft_min - 2), 100.5], showgrid=False),
        xaxis=dict(title="Week"), legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

# ============================================================
# 6. TAB: COUNTER VERIFIER
# ============================================================
def page_counter_verifier(bus, crews, weeks, op_id):
    cv = filt(CV, bus, crews, weeks, op_id)
    if cv.empty or "IS_LEAK" not in cv.columns:
        return html.Div(style=CARD, children=[html.H3("No Counter Verifier data", style={"color": COLORS["muted"]})])
    total = float(len(cv)); leaks = float(cv["IS_LEAK"].sum()); ok = total - leaks
    pct = (leaks / total * 100) if total else 0

    def tile(label, value, color):
        return html.Div(style=CARD, children=[
            html.Div(label, style={"color": COLORS["muted"], "fontSize": "12px", "textTransform": "uppercase"}),
            html.Div(value, style={"color": color, "fontSize": "26px", "fontWeight": "700"})])
    kpis = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "6px"}, children=[
        tile("Tires Verified", f"{total:,.0f}", COLORS["navy"]),
        tile("Leaks (Y)", f"{leaks:,.0f}", COLORS["danger"]),
        tile("OK (N)", f"{ok:,.0f}", COLORS["good"]),
        tile("Counter Verifier %", f"{pct:.2f}%", COLORS["danger"] if pct > 8 else COLORS["good"])])

    leaks_only = cv[cv["IS_LEAK"] == 1]
    if not leaks_only.empty and "COUNTER_VERIFIER_ID" in leaks_only.columns:
        gg = leaks_only.groupby("COUNTER_VERIFIER_ID").size().sort_values(ascending=False).head(10)
        cv_donut = donut([f"CV {int(i)}" for i in gg.index], gg.values, CAT,
                         center_text=f"{int(gg.sum()):,}", center_color=COLORS["danger"])
    else:
        cv_donut = empty_fig()

    if {"YEAR", "WEEK"}.issubset(cv.columns):
        w = (cv.groupby(["YEAR", "WEEK"], dropna=False)
               .agg(TIRES=("IS_LEAK", "size"), LEAKS=("IS_LEAK", "sum")).reset_index())
        w["CV_PCT"] = (w["LEAKS"] / w["TIRES"].replace(0, float("nan")) * 100).round(3)
        w["WK"] = "W" + w["WEEK"].astype("Int64").astype(str).str.zfill(2)
        w = w.sort_values(["YEAR", "WEEK"])
        tf = go.Figure()
        tf.add_bar(x=w["WK"], y=w["TIRES"], name="Verified", marker_color=COLORS["blue"], opacity=0.6, yaxis="y1")
        tf.add_scatter(x=w["WK"], y=w["CV_PCT"], name="Leak %", mode="lines+markers",
                       line=dict(color=COLORS["danger"], width=3), yaxis="y2")
        tf.update_layout(height=320, margin=dict(l=10, r=10, t=6, b=6),
                         barmode="group", yaxis=dict(title="Verified"),
                         yaxis2=dict(title="Leak %", overlaying="y", side="right"),
                         legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    else:
        tf = empty_fig(height=320)

    worst = html.Div("No operator data", style={"color": COLORS["muted"]})
    if {"OP_ID", "OPERATOR_NAME"}.issubset(cv.columns):
        gg = (cv.groupby(["OP_ID", "OPERATOR_NAME"], dropna=False)
                .agg(TESTED=("IS_LEAK", "size"), LEAKS=("IS_LEAK", "sum")).reset_index())
        gg = gg[gg["TESTED"] >= 30]
        gg["LEAK_PCT"] = gg["LEAKS"] / gg["TESTED"] * 100
        gg = gg.sort_values("LEAK_PCT", ascending=False).head(10)
        rows = []
        for _, r in gg.iterrows():
            name = r["OPERATOR_NAME"] if pd.notna(r.get("OPERATOR_NAME")) else str(r["OP_ID"])
            rows.append(html.Tr([
                html.Td(op_chip_link(r["OP_ID"], name, COLORS["btn"]), style={"padding": "6px"}),
                html.Td(f"{int(r['TESTED']):,}", style={"padding": "6px"}),
                html.Td(f"{int(r['LEAKS']):,}", style={"padding": "6px"}),
                html.Td(f"{r['LEAK_PCT']:.1f}%", style={"padding": "6px"}),
            ], style={"borderBottom": "1px solid #eee"}))
        worst = styled_table(["Operator", "Tested", "Leaks", "Leak%"], rows)

    return html.Div([
        kpis,
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px", "marginTop": "8px"}, children=[
            html.Div(style=CARD, children=[html.H4("Leaks by Counter Verifier Station", style={"margin": "0 0 6px 0"}),
                     dcc.Graph(figure=cv_donut, config=GRAPH_CFG)]),
            html.Div(style=CARD, children=[html.H4("Leak % — Weekly Trend", style={"margin": "0 0 6px 0"}),
                     dcc.Graph(figure=tf, config=GRAPH_CFG)])]),
        html.Div(style={**CARD, "marginTop": "6px"}, children=[
            html.H4("⚠️ Highest Leak-Rate Operators (≥30 verified)", style={"margin": "0 0 6px 0"}), worst]),
    ])

# ============================================================
# 7. TAB: RANKINGS
# ============================================================
def page_rankings(step, bus, crews, weeks, op_id, topn):
    d = op_rollup(step, bus, crews, weeks, op_id)
    if d.empty:
        return html.Div(style=CARD, children=[html.H3("No ranking data for this step", style={"color": COLORS["muted"]})])
    d = d.dropna(subset=["OPERATOR_NAME"]) if "OPERATOR_NAME" in d.columns else d
    if "QUALITY_SCORE" in d.columns:
        d = d.sort_values("QUALITY_SCORE")
    d = d.head(topn)
    header = ["#", "Operator", "BU", "Crew", "Tires", "BC%", "AC%", "RFT%", "Scrap/tire", "Score"]
    rows = []
    for _, r in d.iterrows():
        def n(c, fmt):
            return fmt.format(r[c]) if pd.notna(r.get(c)) else "—"
        rows.append(html.Tr([
            html.Td(int(r["RANK"]) if pd.notna(r.get("RANK")) else "", style={"padding": "6px"}),
            html.Td(op_chip_link(r["OP_ID"], r["OPERATOR_NAME"], COLORS["btn"]), style={"padding": "6px"}),
            html.Td(r.get("BU", ""), style={"padding": "6px"}),
            html.Td(int(r["CREW"]) if pd.notna(r.get("CREW")) else "", style={"padding": "6px"}),
            html.Td(n("TIRES_BUILT", "{:,.0f}"), style={"padding": "6px"}),
            html.Td(n("BC_PCT", "{:.2f}"), style={"padding": "6px"}),
            html.Td(n("AC_PCT", "{:.2f}"), style={"padding": "6px"}),
            html.Td(n("RFT_PCT", "{:.0f}"), style={"padding": "6px"}),
            html.Td(n("SCRAP_PCT", "{:.3f}"), style={"padding": "6px"}),
            html.Td(n("QUALITY_SCORE", "{:.1f}"), style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    table = styled_table(header, rows, max_h="360px")

    def bar(col, title, ascending):
        if col not in d.columns:
            return empty_fig(f"No {title}", height=300)
        sd = d.dropna(subset=[col]).sort_values(col, ascending=ascending).head(topn)
        fig = go.Figure(go.Bar(x=sd[col], y=sd["OPERATOR_NAME"], orientation="h", marker_color=COLORS["blue"]))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=6, b=6),
                          yaxis=dict(autorange="reversed"), xaxis_title=title,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    bars = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px", "marginTop": "6px"}, children=[
        html.Div(style=CARD, children=[html.H4("Top RFT%", style={"margin": "0 0 6px 0"}),
                 dcc.Graph(figure=bar("RFT_PCT", "RFT%", False), config=GRAPH_CFG)]),
        html.Div(style=CARD, children=[html.H4("Highest AC%", style={"margin": "0 0 6px 0"}),
                 dcc.Graph(figure=bar("AC_PCT", "AC%", False), config=GRAPH_CFG)]),
        html.Div(style=CARD, children=[html.H4("Highest BC%", style={"margin": "0 0 6px 0"}),
                 dcc.Graph(figure=bar("BC_PCT", "BC%", False), config=GRAPH_CFG)])])
    return html.Div([
        html.Div(style=CARD, children=[html.H3(f"Operator Rankings (Top {topn})",
                 style={"margin": "0 0 8px 0", "color": COLORS["navy"]}), table]), bars])

# ============================================================
# 8. LAYOUT
# ============================================================
FILT_LABEL = {"fontSize": "12px", "color": COLORS["muted"]}
app.layout = html.Div(style={"backgroundColor": COLORS["bg"], "padding": "12px",
                             "fontFamily": "Segoe UI, Arial, sans-serif", "minHeight": "100vh"}, children=[
    # Title bar
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 2fr 1fr", "alignItems": "center",
                    "marginBottom": "8px"}, children=[
        html.Div(f"Last Refresh: {REFRESH}", id="last-refresh",
                 style={"fontSize": "11px", "color": COLORS["muted"]}),
        html.H1("Operator Quality Score Card",
                style={"textAlign": "center", "margin": 0, "fontSize": "26px", "color": COLORS["ink"],
                       "fontWeight": "800"}),
        html.Div(style={"display": "flex", "alignItems": "center", "gap": "10px",
                        "justifyContent": "flex-end"}, children=[
            dcc.Loading(type="circle", children=html.Span(id="refresh-status",
                        style={"fontSize": "11px", "color": COLORS["good"], "fontWeight": "700"})),
            html.Button("🔄 Refresh data", id="btn-refresh", n_clicks=0,
                        style={"backgroundColor": COLORS["btn"], "color": "white", "border": "none",
                               "borderRadius": "6px", "padding": "7px 14px", "cursor": "pointer",
                               "fontSize": "12px", "fontWeight": "600"}),
            html.Div(id="f-op-display", style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        ]),
    ]),

    # Filters
    html.Div(style={**CARD, "display": "flex", "gap": "14px", "alignItems": "flex-end"}, children=[
        html.Div(style={"flex": 1}, children=[html.Label("Business Unit", style=FILT_LABEL),
            dcc.Dropdown(id="f-bu", options=[{"label": b, "value": b} for b in BU_OPTIONS], multi=True, placeholder="All BUs")]),
        html.Div(style={"flex": 1}, children=[html.Label("Crew", style=FILT_LABEL),
            dcc.Dropdown(id="f-crew", options=[{"label": f"Crew {c}", "value": c} for c in CREW_OPTIONS], multi=True, placeholder="All Crews")]),
        html.Div(style={"flex": 1}, children=[html.Label("Week", style=FILT_LABEL),
            dcc.Dropdown(id="f-week", options=[{"label": f"W{w:02d}", "value": w} for w in WEEK_OPTIONS], multi=True, placeholder="All Weeks")]),
        html.Div(style={"flex": 1}, children=[html.Label("Top N (performers & rankings)", style=FILT_LABEL),
            dcc.Dropdown(id="f-topn", options=[{"label": f"Top {n}", "value": n} for n in (10, 15, 20, 25)], value=10, clearable=False)]),
    ]),
    html.Div("Filters (BU · Crew · Week · Operator) apply across every visual — KPIs, donuts, trend, "
             "leaderboards and rankings. Rankings recompute for the selected period.",
             style={"fontSize": "11px", "color": COLORS["muted"], "margin": "4px 8px"}),

    # Step toggle (1st Step / 2nd Step)
    html.Div(style={"margin": "6px 8px"}, children=[
        dcc.RadioItems(id="step", value="1", inline=True,
                       options=[{"label": " 1st Step — Confection ", "value": "1"},
                                {"label": " 2nd Step — Finishing ", "value": "2"}],
                       labelStyle={"backgroundColor": COLORS["card"], "border": f"2px solid {COLORS['btn']}",
                                   "borderRadius": "6px", "padding": "8px 22px", "marginRight": "10px",
                                   "cursor": "pointer", "fontWeight": "700", "color": COLORS["btn"]},
                       inputStyle={"marginRight": "6px"}),
    ]),

    dcc.Tabs(id="tabs", value="score", children=[
        dcc.Tab(label="📋 ScoreCard", value="score"),
        dcc.Tab(label="💧 Counter Verifier", value="cv"),
        dcc.Tab(label="🏅 Rankings", value="rank"),
    ]),
    dcc.Store(id="f-op", data=None),
    dcc.Store(id="refresh-token", data=0),
    html.Div(id="content", style={"marginTop": "10px"}),
])

# ============================================================
# 9. CALLBACKS
# ============================================================
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

@app.callback(Output("tabs", "value"),
              Input({"type": "navbtn", "to": ALL}, "n_clicks"),
              prevent_initial_call=True)
def nav_tab(clicks):
    trig = ctx.triggered_id
    if isinstance(trig, dict) and any(c and c > 0 for c in (clicks or [])):
        return trig["to"]
    return no_update

@app.callback(
    Output("refresh-token", "data"),
    Output("last-refresh", "children"),
    Output("refresh-status", "children"),
    Input("btn-refresh", "n_clicks"),
    prevent_initial_call=True,
)
def do_refresh(n):
    load_all()   # re-read every dataset from Dataiku, rebuild lookups
    stamp = datetime.datetime.now().strftime("%I:%M:%S %p")
    return (n or 0), f"Last Refresh: {REFRESH}", f"✓ Data refreshed at {stamp}"

@app.callback(Output("f-op-display", "children"), Input("f-op", "data"))
def render_op_chip(op_id):
    if not op_id:
        return [html.Span("All operators", style={"color": COLORS["muted"], "fontSize": "13px"}),
                html.Button(id="clear-op", n_clicks=0, style={"display": "none"})]
    name = OP_NAME.get(op_id, op_id)
    return [html.Span(f"👤 {name}", style={"backgroundColor": COLORS["navy"], "color": "white",
                      "padding": "6px 10px", "borderRadius": "6px", "fontSize": "13px"}),
            html.Button("✕ Clear", id="clear-op", n_clicks=0,
                        style={"border": "none", "background": "transparent", "color": COLORS["danger"],
                               "cursor": "pointer", "fontSize": "12px"})]

@app.callback(
    Output("content", "children"),
    Input("step", "value"), Input("tabs", "value"),
    Input("f-bu", "value"), Input("f-crew", "value"),
    Input("f-week", "value"), Input("f-op", "data"), Input("f-topn", "value"),
    Input("refresh-token", "data"),
)
def render(step, tab, bus, crews, weeks, op_id, topn, _tok):
    if tab == "cv":
        return page_counter_verifier(bus, crews, weeks, op_id)
    if tab == "rank":
        return page_rankings(step, bus, crews, weeks, op_id, topn or 10)
    return page_scorecard(step, bus, crews, weeks, op_id, topn or 10)
