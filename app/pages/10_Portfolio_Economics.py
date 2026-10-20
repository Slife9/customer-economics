from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C, presentation as P
from app.lib.results_bundle import BundleTableUnavailable

st.set_page_config(page_title="Portfolio Economics", page_icon="📊", layout="wide")
st.title("📊 Portfolio Economics")
st.caption("Where the bank earns, where it spends, and who it earns from — "
          "down to a single customer.")
st.markdown(P.legend(), unsafe_allow_html=True)

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
# result["ledger"]["card"] is built BEFORE suppression and still includes
# hardship/accommodation/SCRA customers; cv does not. Restricting led to
# cv's own customers keeps the cost waterfall (and the per-customer
# drill-down below) reconciled to every cv-derived chart on this page,
# exactly as charts.py:revenue_cost_waterfall's own docstring requires.
led = result["ledger"]["card"]
led = led[led["Masked Customer Number"].isin(cv["Masked Customer Number"])]
measured = result["ledger"]["measured"]

# A pre-computed results bundle never carries the raw transaction table (see
# ARCHITECTURE.md's "Results bundle" section) - it carries this one
# already-summed scalar instead, measured at export time from the same
# table. A live engine run never has this key, so it always falls through
# to the raw-table sum below, unchanged from before this feature existed.
try:
    tx = result["portfolio"]["Table5_Transaction.csv"]
    total_tx_amount = float(tx["Transaction Amount"].sum())
except BundleTableUnavailable:
    total_tx_amount = measured.get("total_transaction_amount_usd")
effective_interchange = (led["interchange_revenue"].sum() / max(total_tx_amount, 1)
                        if total_tx_amount is not None else None)

st.subheader("Measured, not assumed")
st.markdown(P.tag("measured"), unsafe_allow_html=True)
m1, m2, m3 = st.columns(3)
m1.metric("Blended cost per reward point", f"${measured['cost_per_point_blended']:.4f}")
m2.metric("Breakage (matured vintages)", f"{measured['breakage_rate_matured_vintages']:.1%}")
m3.metric("Effective interchange rate",
         f"{effective_interchange:.2%}" if effective_interchange is not None else "N/A")
st.caption("These three figures were never a generator input — they are computed "
          "from the redemption, expiry and transaction tables you uploaded. If "
          "they could not be measured, the engine would have refused to run "
          "rather than assume a rate.")

st.divider()
st.subheader("Cost waterfall")
st.plotly_chart(C.revenue_cost_waterfall(led), width="stretch")
st.caption("Card economics only — deposit and loan relationship value isn't part "
          "of this chart. A customer's full trailing-12mo net profit (shown in the "
          "table and drill-down below) adds those in.")

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
st.subheader("Product ownership vs. profitability")
own = cv.groupby("products_held")["trailing_12m_net_economic_profit"].agg(
    ["sum", "mean", "count"])
own_labels = [f"{i} product{'s' if i != 1 else ''}<br>(n={int(own.loc[i, 'count']):,})"
             for i in own.index]
fig = go.Figure()
fig.add_trace(go.Bar(
    x=own_labels, y=own["sum"], name="Total contribution (all customers combined)",
    marker_color="#93c5fd",
    text=[f"${v:,.0f}" for v in own["sum"]], textposition="outside", yaxis="y1"))
fig.add_trace(go.Scatter(
    x=own_labels, y=own["mean"], name="Average per customer", mode="lines+markers",
    line=dict(color="#16a34a", width=3), marker=dict(size=9),
    text=[f"${v:,.0f}/customer" for v in own["mean"]],
    textposition="top center", yaxis="y2"))
fig.update_layout(
    title="Does holding more products mean a more profitable customer?",
    height=440, margin=dict(t=60, b=20),
    legend=dict(orientation="h", y=-0.25),
    xaxis_title="Products held",
    yaxis=dict(title="Total NEP, all customers (USD)"),
    yaxis2=dict(title="Average NEP per customer (USD)", overlaying="y", side="right"))
st.plotly_chart(fig, width="stretch")
st.markdown(
    f"{P.tag('measured')} Customers grouped by how many products (card, deposit, "
    f"loan) they actually hold this run — not an assumed cross-sell value.",
    unsafe_allow_html=True)

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
st.subheader("Why is this customer profitable or unprofitable?")
st.markdown(P.tag("measured"), unsafe_allow_html=True)
pick_order = cv.sort_values("trailing_12m_net_economic_profit")["Masked Customer Number"]
selected_id = st.selectbox(
    "Pick a customer to drill into", pick_order.tolist(),
    help="Sorted from the biggest loss to the biggest profit — type to search.")

row = cv.loc[cv["Masked Customer Number"] == selected_id].iloc[0]
dcol1, dcol2 = st.columns([2, 3])
with dcol1:
    st.markdown(
        f"**Segment:** {row['Segment']}  \n"
        f"**Credit Score Band:** {row['Credit Score Band']}  \n"
        f"**Value tier:** {row['cev_band']}  \n"
        f"**Products held:** {int(row['products_held'])}  \n"
        f"**12-month net profit:** ${row['trailing_12m_net_economic_profit']:,.0f}")
    if pd.notna(row.get("routed_lever")):
        st.markdown(
            f"**Lever recommendation:** {row['routed_lever']}  \n"
            f"*{row.get('routing_reason', '')}*")

    cost_drivers = {
        "rewards": -row["reward_expense"], "funding cost": -row["funding_cost"],
        "credit loss": -row["credit_cost"], "cost to serve": -row["cost_to_serve"],
        "capital cost": -row["capital_cost"],
    }
    dominant_cost = min(cost_drivers, key=cost_drivers.get)
    pieces = [f"generated **\\${row['card_revenue']:,.0f}** in card revenue"]
    other_products_net = row["deposit_net_12m"] + row["loan_net_12m"]
    if other_products_net:
        pieces.append(f"**\\${other_products_net:,.0f}** net from deposits/loans")
    pieces.append(f"while **{dominant_cost}** was the single largest cost "
                  f"(\\${-cost_drivers[dominant_cost]:,.0f})")
    verdict = "profitable" if row["trailing_12m_net_economic_profit"] >= 0 else "below cost"
    st.markdown(
        f"**In plain terms:** this customer {', '.join(pieces)} — leaving them "
        f"**{verdict}** by **\\${abs(row['trailing_12m_net_economic_profit']):,.0f}** "
        f"over the trailing 12 months.")
with dcol2:
    # Restrict to the SAME trailing-12mo window every other chart on this
    # page uses (not this customer's own last 12 reporting months) - an
    # account that closed before the portfolio's current window would
    # otherwise show stale pre-closure activity as if it were current,
    # disagreeing with their own card_net (already correctly zero above).
    trailing_window = sorted(led["Cycle Month"].unique())[-12:]
    cust_led = led[(led["Masked Customer Number"] == selected_id)
                  & (led["Cycle Month"].isin(trailing_window))]
    if len(cust_led):
        st.plotly_chart(C.revenue_cost_waterfall(cust_led), width="stretch")
    else:
        st.info("No card ledger activity for this customer in the current "
               "trailing-12-month window — their economics come entirely from "
               "deposits/loans, or their card account closed before this window.")

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
DISPLAY_NAMES = {
    "Masked Customer Number": "Customer ID", "cev_score": "Value Score",
    "cev_band": "Value Tier", "net_band": "Profit/Loss",
    "trailing_12m_net_economic_profit": "Net Profit, 12mo ($)",
    "card_net": "Card Net ($)", "deposit_net_12m": "Deposit Net, 12mo ($)",
    "loan_net_12m": "Loan Net, 12mo ($)", "products_held": "Products Held",
    "routed_lever": "Lever Recommendation",
}
st.dataframe(
    filtered[show_cols].sort_values("trailing_12m_net_economic_profit")
        .rename(columns=DISPLAY_NAMES),
    width="stretch", height=420)
