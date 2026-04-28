# -*- coding: utf-8 -*-
"""
Tire Building Scorecard — Dash Webapp (v2 — with Uniformity)
Filters: BU, Crew, Week, Operator (click on leaderboard name to drill in)

Paste into the Python tab of a Dataiku Code Webapp (Dash).
"""

import dataiku
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, ALL, ctx, no_update

# ============================================================
# 1. LOAD FACT TABLES
# ============================================================
def load(name):
    df = dataiku.Dataset(name).get_dataframe()
    df.columns = [c.upper() for c in df.columns]
    return df

PROD  = load("fact_first_step")
BC    = load("fact_conf_bc")
AC    = load("fact_conf_ac")
SCRAP = load("fact_nc_scrap")
UNI   = load("fact_uniformity")
TOP   = load("agg_top_performers")

def norm_op(x):
    if pd.isna(x): return None
    try:    return str(int(float(x))).zfill(6)
    except: return str(x).strip().zfill(6)

for df in (PROD, BC, AC, SCRAP, UNI, TOP):
    df["OP_ID"] = df["OP_ID"].apply(norm_op)

# Dedupe uniformity to one row per barcode (avoid double counting re-tests)
UNI = UNI.sort_values(["BARCODE", "TEST_DATE"]).drop_duplicates("BARCODE", keep="first")

OP_NAME = (PROD.dropna(subset=["OPERATOR_NAME"])
                .drop_duplicates("OP_ID")
                .set_index("OP_ID")["OPERATOR_NAME"].to_dict())

BU_OPTIONS   = sorted([b for b in PROD["BU"].dropna().unique()])
CREW_OPTIONS = sorted([int(c) for c in PROD["CREW"].dropna().unique()])
WEEK_OPTIONS = sorted(PROD["PROD_WEEK"].dropna().unique().astype(int).tolist())

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
}
CARD = {"backgroundColor": COLORS["card"], "padding": "16px",
        "borderRadius": "10px", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)",
        "margin": "8px"}

# ============================================================
# 3. HELPERS
# ============================================================
def filter_facts(bus, crews, weeks, op_id):
    def f(df):
        d = df
        if bus:   d = d[d["BU"].isin(bus)]
        if crews: d = d[d["CREW"].isin(crews)]
        if weeks and "PROD_WEEK" in d.columns:
            d = d[d["PROD_WEEK"].isin(weeks)]
        if op_id: d = d[d["OP_ID"] == str(op_id)]
        return d
    return f(PROD), f(BC), f(AC), f(SCRAP), f(UNI)

def kpi_tile(label, value, suffix="", color=None):
    color = color or COLORS["primary"]
    return html.Div(style=CARD, children=[
        html.Div(label, style={"color": COLORS["muted"], "fontSize": "13px",
                               "textTransform": "uppercase", "letterSpacing": "1px"}),
        html.Div(f"{value}{suffix}", style={"color": color, "fontSize": "32px",
                                            "fontWeight": "700", "marginTop": "6px"}),
    ])

# ============================================================
# 4. LAYOUT
# ============================================================
app.layout = html.Div(style={"backgroundColor": COLORS["bg"], "padding": "16px",
                             "fontFamily": "Segoe UI, Arial, sans-serif",
                             "minHeight": "100vh"}, children=[

    html.Div(style={"display": "flex", "alignItems": "center",
                    "justifyContent": "space-between", "marginBottom": "12px"}, children=[
        html.H2("🏭 Tire Building Scorecard",
                style={"color": COLORS["primary"], "margin": 0}),
        html.Div("Live from Dataiku Flow", style={"color": COLORS["muted"]}),
    ]),

    # ---- Filters ----
    html.Div(style={**CARD, "display": "flex", "gap": "16px", "alignItems": "flex-end"}, children=[
        html.Div(style={"flex": 1}, children=[
            html.Label("Business Unit", style={"fontSize": "12px", "color": COLORS["muted"]}),
            dcc.Dropdown(id="f-bu",
                         options=[{"label": b, "value": b} for b in BU_OPTIONS],
                         multi=True, placeholder="All BUs"),
        ]),
        html.Div(style={"flex": 1}, children=[
            html.Label("Crew", style={"fontSize": "12px", "color": COLORS["muted"]}),
            dcc.Dropdown(id="f-crew",
                         options=[{"label": f"Crew {c}", "value": c} for c in CREW_OPTIONS],
                         multi=True, placeholder="All Crews"),
        ]),
        html.Div(style={"flex": 1}, children=[
            html.Label("Week", style={"fontSize": "12px", "color": COLORS["muted"]}),
            dcc.Dropdown(id="f-week",
                         options=[{"label": f"W{w:02d}", "value": w} for w in WEEK_OPTIONS],
                         multi=True, placeholder="All Weeks"),
        ]),
        html.Div(style={"flex": 1.2}, children=[
            html.Label("Operator", style={"fontSize": "12px", "color": COLORS["muted"]}),
            html.Div(id="f-op-display",
                     style={"display": "flex", "alignItems": "center", "gap": "8px",
                            "marginTop": "4px", "minHeight": "36px"}),
        ]),
        dcc.Store(id="f-op", data=None),
    ]),

    # ---- KPI Cards (5 tiles now) ----
    html.Div(id="kpi-row",
             style={"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)",
                    "gap": "8px", "marginTop": "12px"}),

    # ---- Donut row ----
    html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)",
                    "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[
            html.H4("Before Cure — CQ Breakdown", style={"margin": "0 0 8px 0"}),
            dcc.Graph(id="donut-bc", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD, children=[
            html.H4("After Cure — CQ Breakdown", style={"margin": "0 0 8px 0"}),
            dcc.Graph(id="donut-ac", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD, children=[
            html.H4("Uniformity Defects (UNI_GRADE)", style={"margin": "0 0 8px 0"}),
            dcc.Graph(id="donut-uni", config={"displayModeBar": False}),
        ]),
    ]),

    # ---- Trend + leaderboard row ----
    html.Div(style={"display": "grid", "gridTemplateColumns": "2fr 1fr",
                    "gap": "8px", "marginTop": "12px"}, children=[
        html.Div(style=CARD, children=[
            html.H4("Weekly Trend", style={"margin": "0 0 8px 0"}),
            dcc.Graph(id="trend-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD, children=[
            html.H4("🏆 Top 10 Performers", style={"margin": "0 0 8px 0"}),
            html.Div(id="top-table"),
        ]),
    ]),
])

# ============================================================
# 5. CALLBACKS
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

@app.callback(
    Output("f-op-display", "children"),
    Input("f-op", "data"),
)
def render_op_chip(op_id):
    if not op_id:
        return [
            html.Span("All operators",
                      style={"color": COLORS["muted"], "fontSize": "13px"}),
            html.Button(id="clear-op", n_clicks=0, style={"display": "none"}),
        ]
    name = OP_NAME.get(op_id, op_id)
    return [
        html.Span(f"👤 {name}",
                  style={"backgroundColor": COLORS["primary"], "color": "white",
                         "padding": "6px 10px", "borderRadius": "6px", "fontSize": "13px"}),
        html.Button("✕ Clear", id="clear-op", n_clicks=0,
                    style={"border": "none", "background": "transparent",
                           "color": COLORS["danger"], "cursor": "pointer", "fontSize": "12px"}),
    ]

@app.callback(
    Output("kpi-row",     "children"),
    Output("donut-bc",    "figure"),
    Output("donut-ac",    "figure"),
    Output("donut-uni",   "figure"),
    Output("trend-chart", "figure"),
    Output("top-table",   "children"),
    Input("f-bu",   "value"),
    Input("f-crew", "value"),
    Input("f-week", "value"),
    Input("f-op",   "data"),
)
def update_all(bus, crews, weeks, op_id):
    prod, bc, ac, scrap, uni = filter_facts(bus, crews, weeks, op_id)

    # ---------- KPIs ----------
    tires     = float(prod["TIRES_BUILT"].sum())
    bc_cnt    = float(bc.dropna(subset=["CQ_CODE_STR"]).shape[0])
    ac_cnt    = float(ac.dropna(subset=["CQ_CODE_STR"]).shape[0])
    scrap_lb  = float(scrap["OP_SCRAP_LBS_BY_TIRES"].sum())
    uni_total = float(uni["BARCODE"].nunique())
    uni_rft   = float(uni["IS_RFT"].sum())

    bc_pct   = (bc_cnt / tires * 100) if tires else 0
    ac_pct   = (ac_cnt / tires * 100) if tires else 0
    scrap_pt = (scrap_lb / tires)     if tires else 0
    rft_pct  = (uni_rft / uni_total * 100) if uni_total else 0

    kpis = [
        kpi_tile("Tires Built",    f"{tires:,.0f}",       color=COLORS["primary"]),
        kpi_tile("Before Cure %",  f"{bc_pct:.2f}", "%",
                 color=COLORS["danger"] if bc_pct > 5 else COLORS["good"]),
        kpi_tile("After Cure %",   f"{ac_pct:.2f}", "%",
                 color=COLORS["danger"] if ac_pct > 5 else COLORS["good"]),
        kpi_tile("Scrap lbs/tire", f"{scrap_pt:.3f}",     color=COLORS["accent"]),
        kpi_tile("Uniformity RFT", f"{rft_pct:.1f}", "%",
                 color=COLORS["good"] if rft_pct >= 90 else COLORS["danger"]),
    ]

    # ---------- Donuts ----------
    def make_donut(df, label_col, value_col=None, dropna_col=None):
        d = df.copy()
        if dropna_col:
            d = d.dropna(subset=[dropna_col])
        if value_col:
            grp = d.groupby(label_col)[value_col].sum().sort_values(ascending=False).head(10)
        else:
            grp = d.groupby(label_col).size().sort_values(ascending=False).head(10)
        if grp.empty:
            fig = go.Figure()
            fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                               font=dict(size=16, color=COLORS["muted"]))
            fig.update_layout(height=320, margin=dict(l=10,r=10,t=10,b=10))
            return fig
        fig = go.Figure(data=[go.Pie(
            labels=grp.index.astype(str), values=grp.values,
            hole=0.55, textinfo="percent",
            hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>")])
        fig.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=320,
                          showlegend=True,
                          legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)),
                          annotations=[dict(text=f"{int(grp.sum()):,}", x=0.5, y=0.5,
                                            font_size=18, showarrow=False)])
        return fig

    donut_bc  = make_donut(bc,  "CQ_DESCRIPTION", dropna_col="CQ_CODE_STR")
    donut_ac  = make_donut(ac,  "CQ_DESCRIPTION", dropna_col="CQ_CODE_STR")
    donut_uni = make_donut(uni, "UNI_GRADE",      dropna_col="UNI_GRADE")

    # ---------- Weekly trend ----------
    keys = ["PROD_YEAR","PROD_WEEK"]
    p_w  = prod.groupby(keys, dropna=False)["TIRES_BUILT"].sum().reset_index()
    bc_w = (bc.dropna(subset=["CQ_CODE_STR"])
              .groupby(keys, dropna=False).size().reset_index(name="BC_COUNT"))
    ac_w = (ac.dropna(subset=["CQ_CODE_STR"])
              .groupby(keys, dropna=False).size().reset_index(name="AC_COUNT"))
    uni_w = (uni.groupby(keys, dropna=False)
                .agg(UNI_TESTED=("BARCODE","nunique"),
                     UNI_RFT=("IS_RFT","sum"))
                .reset_index())

    t = p_w.merge(bc_w,  on=keys, how="left") \
           .merge(ac_w,  on=keys, how="left") \
           .merge(uni_w, on=keys, how="left")
    for c in ["BC_COUNT","AC_COUNT","UNI_TESTED","UNI_RFT"]:
        t[c] = t[c].fillna(0)
    t["BC_PCT"]  = (t["BC_COUNT"]  / t["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
    t["AC_PCT"]  = (t["AC_COUNT"]  / t["TIRES_BUILT"].replace(0, pd.NA) * 100).round(3)
    t["RFT_PCT"] = (t["UNI_RFT"]   / t["UNI_TESTED"].replace(0, pd.NA) * 100).round(3)
    t["WEEK_LABEL"] = (t["PROD_YEAR"].astype(int).astype(str)
                       + "-W" + t["PROD_WEEK"].astype(int).astype(str).str.zfill(2))
    t = t.sort_values(keys)

    trend_fig = go.Figure()
    trend_fig.add_bar(x=t["WEEK_LABEL"], y=t["TIRES_BUILT"],
                      name="Tires Built", marker_color=COLORS["primary"], opacity=0.55, yaxis="y1")
    trend_fig.add_scatter(x=t["WEEK_LABEL"], y=t["BC_PCT"], name="BC%",
                          mode="lines+markers",
                          line=dict(color=COLORS["danger"], width=3), yaxis="y2")
    trend_fig.add_scatter(x=t["WEEK_LABEL"], y=t["AC_PCT"], name="AC%",
                          mode="lines+markers",
                          line=dict(color=COLORS["accent"], width=3), yaxis="y2")
    trend_fig.add_scatter(x=t["WEEK_LABEL"], y=t["RFT_PCT"], name="RFT%",
                          mode="lines+markers",
                          line=dict(color=COLORS["good"], width=3), yaxis="y2")
    trend_fig.update_layout(
        margin=dict(l=10,r=10,t=10,b=10), height=340,
        yaxis=dict(title="Tires Built"),
        yaxis2=dict(title="Quality %", overlaying="y", side="right"),
        xaxis=dict(title="Week"),
        legend=dict(orientation="h", y=-0.2),
    )

    # ---------- Top performers ----------
    top_filt = TOP[(TOP["RANKABLE"] == True) & TOP["OPERATOR_NAME"].notna()].copy()
    if bus:   top_filt = top_filt[top_filt["BU"].isin(bus)]
    if crews: top_filt = top_filt[top_filt["CREW"].isin(crews)]
    if op_id: top_filt = top_filt[top_filt["OP_ID"] == str(op_id)]
    top_filt = top_filt.sort_values("QUALITY_SCORE").head(10)

    table_rows = [html.Tr(
        [html.Th(c, style={"padding": "6px", "textAlign": "left"})
         for c in ["#", "Operator", "BU", "Crew", "Tires", "RFT%", "Score"]],
        style={"backgroundColor": COLORS["primary"], "color": "white"})]
    for _, r in top_filt.iterrows():
        op = r["OP_ID"]
        rft_disp = f"{r['RFT_PCT']:.0f}%" if pd.notna(r.get("RFT_PCT")) else "—"
        table_rows.append(html.Tr([
            html.Td(int(r["RANK"]) if pd.notna(r["RANK"]) else "",
                    style={"padding": "6px"}),
            html.Td(html.A(r["OPERATOR_NAME"],
                           id={"type": "op-link", "index": str(op)},
                           n_clicks=0,
                           style={"color": COLORS["primary"], "cursor": "pointer",
                                  "textDecoration": "underline"}),
                    style={"padding": "6px"}),
            html.Td(r["BU"], style={"padding": "6px"}),
            html.Td(int(r["CREW"]) if pd.notna(r["CREW"]) else "",
                    style={"padding": "6px"}),
            html.Td(f"{int(r['TIRES_BUILT']):,}", style={"padding": "6px"}),
            html.Td(rft_disp, style={"padding": "6px"}),
            html.Td(f"{r['QUALITY_SCORE']:.1f}", style={"padding": "6px"}),
        ], style={"borderBottom": "1px solid #eee"}))
    top_table = html.Table(table_rows,
                           style={"width": "100%", "borderCollapse": "collapse",
                                  "fontSize": "13px"})

    return kpis, donut_bc, donut_ac, donut_uni, trend_fig, top_table
