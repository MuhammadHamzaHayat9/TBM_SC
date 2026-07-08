# -*- coding: utf-8 -*-
"""
Tire Building Scorecard — Dash Webapp (v4 — reads the pre-computed aggregates)

Reads the small aggregate datasets produced by the Dataiku flow (a few hundred
to a few thousand rows each) instead of the raw multi-million-row fact tables,
so the webapp backend stays well within memory. Three tabs:

  1. ScoreCard        — KPI cards, BC / AC / Scrap / Uniformity donuts,
                        weekly trend, Top-10 performers
  2. Counter Verifier — end-of-line leak %, leaks by station, weekly CV trend,
                        worst operators (from fact_counter_verifier)
  3. Rankings         — full operator ranking table + Top-N bar charts

Datasets read (all from the current Dataiku project):
  agg_top_performers   agg_uniformity      agg_donut_bc
  agg_donut_ac         agg_donut_scrap     agg_weekly_trend
  fact_counter_verifier

Filters: BU, Crew, Week, Operator (click a name on any leaderboard/ranking to
drill the app to that operator).

Paste into the Python tab of a Dataiku Code Webapp (Dash). `app` is provided
by the Dataiku backend.
"""

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
    """Vectorised OP_ID normaliser -> 6-char zero-padded string."""
    txt = s.astype("string").str.strip()
    txt = txt.str.replace(r"\.0+$", "", regex=True)   # '232694.0' -> '232694'
    txt = txt.str.zfill(6)
    return txt.where(s.notna(), None)

TOP   = load("agg_top_performers")     # operator-grain KPIs + ranks
UNI   = load("agg_uniformity")         # BU/CREW/WEEK uniformity RFT
DBC   = load("agg_donut_bc")           # before-cure CQ donut
DAC   = load("agg_donut_ac")           # after-cure  CQ donut
DSC   = load("agg_donut_scrap")        # scrap by TBM donut
TREND = load("agg_weekly_trend")       # weekly tires + BC/AC/scrap %
CV    = load("fact_counter_verifier")  # end-of-line leak events

if not TOP.empty and "OP_ID" in TOP.columns:
    TOP["OP_ID"] = norm_op_series(TOP["OP_ID"])
if not CV.empty and "OP_ID" in CV.columns:
    CV["OP_ID"] = norm_op_series(CV["OP_ID"])

# Operator display names
OP_NAME = {}
if not TOP.empty and {"OP_ID", "OPERATOR_NAME"}.issubset(TOP.columns):
    OP_NAME = (TOP.dropna(subset=["OPERATOR_NAME"])
                  .drop_duplicates("OP_ID")
                  .set_index("OP_ID")["OPERATOR_NAME"].to_dict())

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

BU_OPTIONS   = _uniq(TOP, "BU")
CREW_OPTIONS = _uniq(TOP, "CREW", int)
WEEK_OPTIONS = sorted(set(_uniq(TREND, "PROD_WEEK", int)) | set(_uniq(CV, "WEEK", int)))

# ============================================================
# 2. STYLES
# ============================================================
COLORS = {
    "bg": "#F5F7FA", "card": "#FFFFFF", "primary": "#0033A0", "accent": "#FFCC00",
    "danger": "#E63946", "good": "#2A9D8F", "muted": "#6C757D",
}
CARD = {"backgroundColor": COLORS["card"], "padding": "16px", "borderRadius": "10px",
        "boxShadow": "0 2px 6px rgba(0,0,0,0.08)", "margin": "8px"}

# ============================================================
# 3. FILTER HELPERS
# ============================================================
def filt(df, bus, crews, weeks=None, op_id=None, drop_bu_na=False):
    """Apply whatever of BU / CREW / WEEK / OP_ID the dataframe supports."""
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

# ============================================================
# 4. VISUAL HELPERS
# ============================================================
def kpi_tile(label, value, suffix="", color=None):
    color = color or COLORS["primary"]
    return html.Div(style=CARD, children=[
        html.Div(label, style={"color": COLORS["muted"], "fontSize": "12px",
                               "textTransform": "uppercase", "letterSpacing": "1px"}),
        html.Div(f"{value}{suffix}", style={"color": color, "fontSize": "28px",
                                            "fontWeight": "700", "marginTop": "6px"}),
    ])

def empty_fig(msg="No data", height=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16, color=COLORS["muted"]))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig

def donut(labels, values, height=300):
    if len(values) == 0 or float(sum(values)) == 0:
        return empty_fig(height=height)
    fig = go.Figure(data=[go.Pie(labels=[str(l) for l in labels], values=list(values),
                                 hole=0.55, textinfo="percent",
                                 hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>")])
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=height, showlegend=True,
                      legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)),
                      annotations=[dict(text=f"{int(sum(values)):,}", x=0.5, y=0.5,
                                        font_size=16, showarrow=False)])
    return fig

def donut_from_agg(df, bus, crews, label_col, value_col, code_col=None, height=300):
    """Build a donut from an agg_donut_* dataset (drop pre-computed BU=NaN totals)."""
    d = filt(df, bus, crews, drop_bu_na=True)
    if d.empty or value_col not in d.columns:
        return empty_fig(height=height)
    lab = label_col if (label_col in d.columns) else code_col
    d = d.copy()
    if code_col and label_col in d.columns:
        d[label_col] = d[label_col].fillna(d[code_col].astype(str))
    grp = d.groupby(lab)[value_col].sum().sort_values(ascending=False).head(10)
    return donut(grp.index, grp.values, height=height)

def op_link(op_id, name):
    return html.A(name, id={"type": "op-link", "index": str(op_id)}, n_clicks=0,
                  style={"color": COLORS["primary"], "cursor": "pointer",
                         "textDecoration": "underline"})

def styled_table(header, rows, max_h=None):
    thead = html.Tr([html.Th(h, style={"padding": "6px", "textAlign": "left"}) for h in header],
                    style={"backgroundColor": COLORS["primary"], "color": "white"})
    tbl = html.Table([thead] + rows,
                     style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})
    if max_h:
        return html.Div(tbl, style={"maxHeight": max_h, "overflowY": "auto"})
    return tbl

# ============================================================
# 5. TAB: SCORECARD
# ============================================================
def page_scorecard(bus, crews, weeks, op_id):
    t = filt(TOP, bus, crews, op_id=op_id)          # operator-grain KPI source
    u = filt(UNI, bus, crews, weeks)                 # BU/CREW/WEEK uniformity

    def s(col):
        return float(t[col].sum()) if (not t.empty and col in t.columns) else 0.0
    tires = s("TIRES_BUILT")
    bc    = s("BC_COUNT"); ac = s("AC_COUNT"); scrap = s("SCRAP_LBS")
    uni_tested = float(u["TIRES_TESTED"].sum()) if (not u.empty and "TIRES_TESTED" in u.columns) else s("UNI_TESTED")
    uni_rft    = float(u["RFT_COUNT"].sum())    if (not u.empty and "RFT_COUNT" in u.columns)    else s("UNI_RFT")

    cvf   = filt(CV, bus, crews, weeks, op_id)
    cv_pct = float(cvf["IS_LEAK"].mean() * 100) if (not cvf.empty and "IS_LEAK" in cvf.columns) else 0.0

    bc_pct  = (bc / tires * 100) if tires else 0
    ac_pct  = (ac / tires * 100) if tires else 0
    scrap_t = (scrap / tires)    if tires else 0
    rft_pct = (uni_rft / uni_tested * 100) if uni_tested else 0

    kpis = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(6, 1fr)", "gap": "8px"}, children=[
        kpi_tile("Tires Built",     f"{tires:,.0f}", color=COLORS["primary"]),
        kpi_tile("Before Cure %",   f"{bc_pct:.2f}", "%", color=COLORS["danger"] if bc_pct > 1 else COLORS["good"]),
        kpi_tile("After Cure %",    f"{ac_pct:.2f}", "%", color=COLORS["danger"] if ac_pct > 20 else COLORS["good"]),
        kpi_tile("Scrap lbs/tire",  f"{scrap_t:.3f}", color=COLORS["accent"]),
        kpi_tile("Uniformity RFT",  f"{rft_pct:.1f}", "%", color=COLORS["good"] if rft_pct >= 90 else COLORS["danger"]),
        kpi_tile("Counter Verifier %", f"{cv_pct:.2f}", "%", color=COLORS["danger"] if cv_pct > 8 else COLORS["good"]),
    ])

    donut_row = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)",
                                "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[html.H4("Before Cure — CQ Breakdown", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_from_agg(DBC, bus, crews, "CQ_DESCRIPTION", "CQ_COUNT", "CQ_CODE_STR"),
                           config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("After Cure — CQ Breakdown", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_from_agg(DAC, bus, crews, "CQ_DESCRIPTION", "CQ_COUNT", "CQ_CODE_STR"),
                           config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("NC Scrap — TBM Breakdown", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=donut_from_agg(DSC, bus, crews, "TBM", "SCRAP_LBS"),
                           config={"displayModeBar": False})]),
    ])

    bottom = html.Div(style={"display": "grid", "gridTemplateColumns": "2fr 1fr",
                             "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[html.H4("Weekly Trend", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=trend_fig(bus, weeks), config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("🏆 Top 10 Performers", style={"margin": "0 0 8px 0"}),
                 leaderboard(bus, crews, op_id)]),
    ])
    return html.Div([kpis, donut_row, bottom])

def trend_fig(bus, weeks):
    if TREND.empty:
        return empty_fig("No trend data", height=340)
    d = TREND.copy()
    # agg_weekly_trend holds per-BU rows plus BU='ALL' overall rows
    if bus:
        d = d[d["BU"].isin(bus)]
    else:
        d = d[d["BU"] == "ALL"] if (d["BU"] == "ALL").any() else d
    if weeks and "PROD_WEEK" in d.columns:
        d = d[d["PROD_WEEK"].isin(weeks)]
    if d.empty:
        return empty_fig("No trend data", height=340)
    keys = ["PROD_YEAR", "PROD_WEEK"]
    g = d.groupby(keys, dropna=False).agg(
        TIRES=("TIRES_BUILT", "sum"), BC=("BC_COUNT", "sum"),
        AC=("AC_COUNT", "sum"), SCRAP=("SCRAP_LBS", "sum")).reset_index()
    g["BC_PCT"] = (g["BC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
    g["AC_PCT"] = (g["AC"] / g["TIRES"].replace(0, float("nan")) * 100).round(3)
    g["WEEK_LABEL"] = (g["PROD_YEAR"].astype("Int64").astype(str)
                       + "-W" + g["PROD_WEEK"].astype("Int64").astype(str).str.zfill(2))
    g = g.sort_values(keys)
    fig = go.Figure()
    fig.add_bar(x=g["WEEK_LABEL"], y=g["TIRES"], name="Tires Built",
                marker_color=COLORS["primary"], opacity=0.55, yaxis="y1")
    fig.add_scatter(x=g["WEEK_LABEL"], y=g["BC_PCT"], name="BC%", mode="lines+markers",
                    line=dict(color=COLORS["danger"], width=3), yaxis="y2")
    fig.add_scatter(x=g["WEEK_LABEL"], y=g["AC_PCT"], name="AC%", mode="lines+markers",
                    line=dict(color=COLORS["accent"], width=3), yaxis="y2")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=340,
                      yaxis=dict(title="Tires Built"),
                      yaxis2=dict(title="Quality %", overlaying="y", side="right"),
                      xaxis=dict(title="Week"), legend=dict(orientation="h", y=-0.25))
    return fig

def leaderboard(bus, crews, op_id):
    d = filt(TOP, bus, crews, op_id=op_id)
    if d.empty:
        return html.Div("No data", style={"color": COLORS["muted"]})
    if "RANKABLE" in d.columns:
        d = d[d["RANKABLE"] == True]
    d = d.dropna(subset=["OPERATOR_NAME"]) if "OPERATOR_NAME" in d.columns else d
    sort_col = "QUALITY_SCORE" if "QUALITY_SCORE" in d.columns else "RANK"
    d = d.sort_values(sort_col).head(10)
    rows = []
    for _, r in d.iterrows():
        rft = f"{r['RFT_PCT']:.0f}%" if pd.notna(r.get("RFT_PCT")) else "—"
        rows.append(html.Tr([
            html.Td(int(r["RANK"]) if pd.notna(r.get("RANK")) else "", style={"padding": "6px"}),
            html.Td(op_link(r["OP_ID"], r["OPERATOR_NAME"]), style={"padding": "6px"}),
            html.Td(r.get("BU", ""), style={"padding": "6px"}),
            html.Td(int(r["CREW"]) if pd.notna(r.get("CREW")) else "", style={"padding": "6px"}),
            html.Td(f"{int(r['TIRES_BUILT']):,}" if pd.notna(r.get("TIRES_BUILT")) else "—", style={"padding": "6px"}),
            html.Td(rft, style={"padding": "6px"}),
            html.Td(f"{r['QUALITY_SCORE']:.1f}" if pd.notna(r.get("QUALITY_SCORE")) else "—", style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    return styled_table(["#", "Operator", "BU", "Crew", "Tires", "RFT%", "Score"], rows)

# ============================================================
# 6. TAB: COUNTER VERIFIER
# ============================================================
def page_counter_verifier(bus, crews, weeks, op_id):
    cv = filt(CV, bus, crews, weeks, op_id)
    if cv.empty or "IS_LEAK" not in cv.columns:
        return html.Div(style=CARD, children=[html.H3("No Counter Verifier data",
                        style={"color": COLORS["muted"]})])
    total = float(len(cv)); leaks = float(cv["IS_LEAK"].sum()); ok = total - leaks
    pct = (leaks / total * 100) if total else 0

    kpis = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "8px"}, children=[
        kpi_tile("Tires Verified", f"{total:,.0f}", color=COLORS["primary"]),
        kpi_tile("Leaks (Y)",      f"{leaks:,.0f}", color=COLORS["danger"]),
        kpi_tile("OK (N)",         f"{ok:,.0f}",    color=COLORS["good"]),
        kpi_tile("Counter Verifier %", f"{pct:.2f}", "%",
                 color=COLORS["danger"] if pct > 8 else COLORS["good"]),
    ])

    # Donut: leaks by station
    leaks_only = cv[cv["IS_LEAK"] == 1]
    if not leaks_only.empty and "COUNTER_VERIFIER_ID" in leaks_only.columns:
        g = leaks_only.groupby("COUNTER_VERIFIER_ID").size().sort_values(ascending=False).head(10)
        cv_donut = donut([f"CV {int(i)}" for i in g.index], g.values)
    else:
        cv_donut = empty_fig()

    # Weekly CV trend
    if {"YEAR", "WEEK"}.issubset(cv.columns):
        w = (cv.groupby(["YEAR", "WEEK"], dropna=False)
               .agg(TIRES=("IS_LEAK", "size"), LEAKS=("IS_LEAK", "sum")).reset_index())
        w["CV_PCT"] = (w["LEAKS"] / w["TIRES"].replace(0, float("nan")) * 100).round(3)
        w["WEEK_LABEL"] = (w["YEAR"].astype("Int64").astype(str)
                           + "-W" + w["WEEK"].astype("Int64").astype(str).str.zfill(2))
        w = w.sort_values(["YEAR", "WEEK"])
        tf = go.Figure()
        tf.add_bar(x=w["WEEK_LABEL"], y=w["TIRES"], name="Verified",
                   marker_color=COLORS["primary"], opacity=0.5, yaxis="y1")
        tf.add_scatter(x=w["WEEK_LABEL"], y=w["CV_PCT"], name="Leak %", mode="lines+markers",
                       line=dict(color=COLORS["danger"], width=3), yaxis="y2")
        tf.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320,
                         yaxis=dict(title="Verified"),
                         yaxis2=dict(title="Leak %", overlaying="y", side="right"),
                         legend=dict(orientation="h", y=-0.25))
    else:
        tf = empty_fig(height=320)

    # Worst operators by leak %
    worst_tbl = html.Div("No operator data", style={"color": COLORS["muted"]})
    if {"OP_ID", "OPERATOR_NAME"}.issubset(cv.columns):
        g = (cv.groupby(["OP_ID", "OPERATOR_NAME"], dropna=False)
               .agg(TESTED=("IS_LEAK", "size"), LEAKS=("IS_LEAK", "sum")).reset_index())
        g = g[g["TESTED"] >= 30]
        g["LEAK_PCT"] = (g["LEAKS"] / g["TESTED"] * 100)
        g = g.sort_values("LEAK_PCT", ascending=False).head(10)
        rows = []
        for _, r in g.iterrows():
            name = r["OPERATOR_NAME"] if pd.notna(r.get("OPERATOR_NAME")) else str(r["OP_ID"])
            rows.append(html.Tr([
                html.Td(op_link(r["OP_ID"], name), style={"padding": "6px"}),
                html.Td(f"{int(r['TESTED']):,}", style={"padding": "6px"}),
                html.Td(f"{int(r['LEAKS']):,}", style={"padding": "6px"}),
                html.Td(f"{r['LEAK_PCT']:.1f}%", style={"padding": "6px"}),
            ], style={"borderBottom": "1px solid #eee"}))
        worst_tbl = styled_table(["Operator", "Tested", "Leaks", "Leak%"], rows)

    return html.Div([
        kpis,
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px", "marginTop": "12px"}, children=[
            html.Div(style=CARD, children=[html.H4("Leaks by Counter Verifier Station", style={"margin": "0 0 8px 0"}),
                     dcc.Graph(figure=cv_donut, config={"displayModeBar": False})]),
            html.Div(style=CARD, children=[html.H4("Leak % — Weekly Trend", style={"margin": "0 0 8px 0"}),
                     dcc.Graph(figure=tf, config={"displayModeBar": False})]),
        ]),
        html.Div(style={**CARD, "marginTop": "8px"}, children=[
            html.H4("⚠️ Highest Leak-Rate Operators (≥30 verified)", style={"margin": "0 0 8px 0"}),
            worst_tbl]),
    ])

# ============================================================
# 7. TAB: RANKINGS
# ============================================================
def page_rankings(bus, crews, op_id, topn):
    d = filt(TOP, bus, crews, op_id=op_id)
    if d.empty:
        return html.Div(style=CARD, children=[html.H3("No ranking data", style={"color": COLORS["muted"]})])
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
            html.Td(op_link(r["OP_ID"], r["OPERATOR_NAME"]), style={"padding": "6px"}),
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
        s = d.dropna(subset=[col]).sort_values(col, ascending=ascending).head(topn)
        fig = go.Figure(go.Bar(x=s[col], y=s["OPERATOR_NAME"], orientation="h",
                               marker_color=COLORS["primary"]))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(autorange="reversed"), xaxis_title=title)
        return fig

    bars = html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)",
                           "gap": "8px", "marginTop": "8px"}, children=[
        html.Div(style=CARD, children=[html.H4("Top RFT%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=bar("RFT_PCT", "RFT%", False), config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("Highest AC%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=bar("AC_PCT", "AC%", False), config={"displayModeBar": False})]),
        html.Div(style=CARD, children=[html.H4("Highest BC%", style={"margin": "0 0 8px 0"}),
                 dcc.Graph(figure=bar("BC_PCT", "BC%", False), config={"displayModeBar": False})]),
    ])
    return html.Div([
        html.Div(style=CARD, children=[html.H3(f"Operator Rankings (Top {topn})",
                 style={"margin": "0 0 8px 0", "color": COLORS["primary"]}), table]),
        bars,
    ])

# ============================================================
# 8. LAYOUT
# ============================================================
app.layout = html.Div(style={"backgroundColor": COLORS["bg"], "padding": "16px",
                             "fontFamily": "Segoe UI, Arial, sans-serif", "minHeight": "100vh"}, children=[
    html.Div(style={"display": "flex", "alignItems": "center", "justifyContent": "space-between",
                    "marginBottom": "12px"}, children=[
        html.H2("🏭 Tire Building Scorecard", style={"color": COLORS["primary"], "margin": 0}),
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
            dcc.Dropdown(id="f-topn", options=[{"label": f"Top {n}", "value": n} for n in (10, 15, 20, 25)],
                         value=10, clearable=False)]),
    ]),
    html.Div("Week filter applies to the weekly trends, Uniformity and Counter Verifier; "
             "operator KPI cards and donuts are period totals.",
             style={"fontSize": "11px", "color": COLORS["muted"], "margin": "4px 8px"}),

    dcc.Tabs(id="tabs", value="score", children=[
        dcc.Tab(label="📋 ScoreCard", value="score"),
        dcc.Tab(label="💧 Counter Verifier", value="cv"),
        dcc.Tab(label="🏅 Rankings", value="rank"),
    ]),
    dcc.Store(id="f-op", data=None),
    html.Div(id="content", style={"marginTop": "12px"}),
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

@app.callback(Output("f-op-display", "children"), Input("f-op", "data"))
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
    Output("content", "children"),
    Input("tabs", "value"),
    Input("f-bu", "value"), Input("f-crew", "value"),
    Input("f-week", "value"), Input("f-op", "data"), Input("f-topn", "value"),
)
def render(tab, bus, crews, weeks, op_id, topn):
    if tab == "cv":
        return page_counter_verifier(bus, crews, weeks, op_id)
    if tab == "rank":
        return page_rankings(bus, crews, op_id, topn or 10)
    return page_scorecard(bus, crews, weeks, op_id)
