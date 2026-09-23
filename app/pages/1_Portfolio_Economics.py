from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Portfolio Economics", page_icon="📊", layout="wide")
st.title("📊 Portfolio Economics")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
led = result["ledger"]["card"]
measured = result["ledger"]["measured"]

tx = result["portfolio"]["Table5_Transaction.csv"]
effective_interchange = led["interchange_revenue"].sum() / max(tx["Transaction Amount"].sum(), 1)

st.subheader("Measured, not assumed")
m1, m2, m3 = st.columns(3)
m1.metric("Blended cost per reward point", f"${measured['cost_per_point_blended']:.4f}")
m2.metric("Breakage (matured vintages)", f"{measured['breakage_rate_matured_vintages']:.1%}")
m3.metric("Effective interchange rate", f"{effective_interchange:.2%}")
st.caption("These three figures were never a generator input — they are computed "
          "from the redemption, expiry and transaction tables you uploaded. If "
          "they could not be measured, the engine would have refused to run "
          "rather than assume a rate.")

st.divider()
st.subheader("Cost waterfall")
st.plotly_chart(C.revenue_cost_waterfall(led), width="stretch")

st.divider()
col1, col2 = st.columns(2)
with col1:
    st.subheader("Product mix")
    products = ["holds_card", "holds_deposit", "holds_loan"]
    counts = {p.replace("holds_", "").title(): int(cv[p].sum()) for p in products}
    fig = go.Figure(go.Bar(x=list(counts.keys()), y=list(counts.values()),
                          marker_color=["#2563eb", "#16a34a", "#d97706"],
                          text=list(counts.values()), textposition="outside"))
    fig.update_layout(height=360, yaxis_title="Customers", margin=dict(t=20, b=20))
    st.plotly_chart(fig, width="stretch")

with col2:
    st.subheader("Products held per customer")
    dist = cv["products_held"].value_counts().sort_index()
    fig = go.Figure(go.Bar(x=[f"{i} product{'s' if i != 1 else ''}" for i in dist.index],
                          y=dist.to_numpy(), marker_color="#7c3aed",
                          text=dist.to_numpy(), textposition="outside"))
    fig.update_layout(height=360, yaxis_title="Customers", margin=dict(t=20, b=20))
    st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Net economic profit by segment and score band")
seg_col, band_col = st.columns(2)
with seg_col:
    seg = cv.groupby("Segment")["trailing_12m_net_economic_profit"].agg(["sum", "mean", "count"])
    # Sorted by PER-CUSTOMER value, not total - a chart sorted by total puts
    # the biggest segment on top regardless of whether it's actually the
    # most valuable one, and total-by-segment on its own was shown to read
    # as "our most valuable segment" when it actually just meant "our
    # largest segment." Total (bars, left axis) and per-customer average
    # (line, right axis) are shown together so the two can't be conflated.
    seg = seg.sort_values("mean", ascending=False)
    x_labels = [f"{s}<br>(n={int(seg.loc[s, 'count']):,})" for s in seg.index]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_labels, y=seg["sum"], name="Total contribution (all customers combined)",
        marker_color="#93c5fd",
        text=[f"${v:,.0f}" for v in seg["sum"]], textposition="outside", yaxis="y1"))
    fig.add_trace(go.Scatter(
        x=x_labels, y=seg["mean"], name="Average per customer", mode="lines+markers",
        line=dict(color="#16a34a", width=3), marker=dict(size=9),
        text=[f"${v:,.0f}/customer" for v in seg["mean"]],
        textposition="top center", yaxis="y2"))
    fig.update_layout(
        title="Segment value: total contribution vs. per-customer average",
        height=440, margin=dict(t=60, b=20),
        legend=dict(orientation="h", y=-0.25),
        yaxis=dict(title="Total NEP, all customers (USD)"),
        yaxis2=dict(title="Average NEP per customer (USD)", overlaying="y", side="right"))
    st.plotly_chart(fig, width="stretch")
    st.caption("Sorted by average value per customer, not by total - the "
              "segment with the tallest bar is our LARGEST segment; the "
              "highest point on the green line is our MOST VALUABLE one "
              "per customer. They are not always the same segment.")
with band_col:
    band = cv.groupby("Credit Score Band", observed=True)[
        "trailing_12m_net_economic_profit"].agg(["sum", "mean", "count"])
    fig = go.Figure(go.Bar(x=band.index.astype(str), y=band["mean"],
                          marker_color=["#dc2626" if v < 0 else "#16a34a" for v in band["mean"]],
                          text=[f"${v:,.0f}" for v in band["mean"]], textposition="outside"))
    fig.update_layout(title="Mean NEP by credit score band", height=400, margin=dict(t=40, b=20))
    st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Customer economics table")

f1, f2, f3, f4, f5 = st.columns(5)
segment_opts = f1.multiselect("Segment", sorted(cv["Segment"].dropna().unique()))
band_opts = f2.multiselect("Credit Score Band",
                          sorted(cv["Credit Score Band"].dropna().unique()))
cev_opts = f3.multiselect("CEV Band",
                         [b for b in ["Detractor", "Underperforming", "Core",
                                     "Valued", "Premier"]
                         if b in cv["cev_band"].astype(str).unique()])
net_opts = f4.multiselect("Net Band", ["Profit", "Neutral", "Loss"])
lever_options = sorted(cv["routed_lever"].dropna().unique().tolist()) + ["Not routed"]
lever_opts = f5.multiselect("Routed Lever", lever_options)

filtered = cv.copy()
if segment_opts:
    filtered = filtered[filtered["Segment"].isin(segment_opts)]
if band_opts:
    filtered = filtered[filtered["Credit Score Band"].isin(band_opts)]
if cev_opts:
    filtered = filtered[filtered["cev_band"].astype(str).isin(cev_opts)]
if net_opts:
    filtered = filtered[filtered["net_band"].isin(net_opts)]
if lever_opts:
    wants_unrouted = "Not routed" in lever_opts
    named = [l for l in lever_opts if l != "Not routed"]
    mask = filtered["routed_lever"].isin(named)
    if wants_unrouted:
        mask = mask | filtered["routed_lever"].isna()
    filtered = filtered[mask]

st.caption(f"Showing {len(filtered):,} of {len(cv):,} customers")

show_cols = ["Masked Customer Number", "Segment", "Credit Score Band", "cev_score",
            "cev_band", "net_band", "trailing_12m_net_economic_profit", "card_net",
            "deposit_net_12m", "loan_net_12m", "products_held", "routed_lever"]
st.dataframe(filtered[show_cols].sort_values("trailing_12m_net_economic_profit"),
            width="stretch", height=420)
