"""Liquidity cost (LCR) - a deliberately separate page.

The US Liquidity Coverage Ratio Final Rule (12 CFR 249) requires a bank to
hold High-Quality Liquid Assets against a modeled 30-day stress outflow on
every UNUSED card commitment - a real, currently-in-force rule, completely
distinct from capital (CCF/risk-weighted assets) and from the core P&L.
Holding HQLA instead of lending that capacity out has an opportunity cost:
the gap between what HQLA yields and what the bank could otherwise earn
lending it. That cost is informative, not measured the way revenue and
credit losses are - it depends on policy inputs (outflow rate, yield gap)
a finance team owns. See engine/config/liquidity_policy.json and
engine/core/customer_view.py's _compute_liquidity_cost for the full basis.
Kept out of net_economic_profit and total_cost on purpose, same reasoning
as CAC payback on the Acquisition Cost page.
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Liquidity", page_icon="💧", layout="wide")
st.title("💧 Liquidity Cost (LCR)")
st.caption("What does it cost to hold the liquid assets regulators require against each "
          "customer's unused credit line? A diagnostic view, kept separate from CEV and "
          "net economic profit on purpose.")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]

if "annual_liquidity_cost" not in cv.columns or cv["annual_liquidity_cost"].isna().all():
    st.info("This upload doesn't have enough card-level data to estimate undrawn exposure, "
           "so liquidity cost can't be assessed. This page will populate automatically once "
           "that data is present — nothing else needs to change.")
    st.stop()

has_liq = cv["annual_liquidity_cost"].notna()
needs_review = cv["lcr_outflow_rate"].isna() & has_liq

st.subheader("Portfolio summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total undrawn exposure (avg, trailing 12mo)",
         f"${cv.loc[has_liq, 'avg_undrawn_12m'].sum():,.0f}",
         help="Average unused credit line per customer over the trailing 12 months, summed "
             "across the portfolio. This is the base the LCR outflow rate applies to.")
m2.metric("Required HQLA", f"${cv.loc[has_liq, 'required_hqla'].sum():,.0f}",
         help="Undrawn exposure x LCR outflow rate — the liquid assets the bank must hold "
             "against the modeled 30-day drawdown risk on these lines.")
m3.metric("Annual liquidity cost", f"${cv.loc[has_liq, 'annual_liquidity_cost'].sum():,.0f}",
         help="Required HQLA x (lending yield − HQLA yield) — the opportunity cost of holding "
             "those assets instead of lending the capacity out. Policy inputs, not measured.")
m4.metric("Needs individual assessment", f"{int(needs_review.sum()):,}",
         help="Exceeds the concentration threshold on card limit alone and so fails the "
             "regulatory-retail test — needs a full-relationship-exposure check, not a "
             "blanket retail rate.")

st.divider()
st.plotly_chart(C.liquidity_by_segment_chart(cv), width="stretch")
st.caption("Small Business lines get the higher non-retail outflow rate by default. Private "
          "Banking is individually assessed against a concentration threshold on card limit "
          "alone — a necessary check, not a sufficient one (see caption below).")

st.divider()
st.subheader("By segment")
by_segment = (cv[has_liq].groupby("Segment", observed=True).agg(
    customers=("Masked Customer Number", "nunique"),
    avg_outflow_rate=("lcr_outflow_rate", "mean"),
    total_undrawn_12m=("avg_undrawn_12m", "sum"),
    total_required_hqla=("required_hqla", "sum"),
    total_annual_liquidity_cost=("annual_liquidity_cost", "sum"),
).reset_index().sort_values("total_annual_liquidity_cost", ascending=False))
st.dataframe(
    by_segment.rename(columns={
        "Segment": "Segment", "customers": "Customers",
        "avg_outflow_rate": "Avg outflow rate",
        "total_undrawn_12m": "Total undrawn (12mo avg)",
        "total_required_hqla": "Total required HQLA",
        "total_annual_liquidity_cost": "Total annual liquidity cost"}).style.format({
        "Avg outflow rate": "{:.1%}",
        "Total undrawn (12mo avg)": "${:,.0f}",
        "Total required HQLA": "${:,.0f}",
        "Total annual liquidity cost": "${:,.0f}",
    }, na_rep="n/a"),
    width="stretch", height=260)

st.divider()
st.subheader("Customer-level detail")
f1, f2 = st.columns(2)
segment_opts = f1.multiselect("Segment", sorted(cv.loc[has_liq, "Segment"].dropna().unique()))
review_only = f2.checkbox("Needs individual assessment only")

filtered = cv[has_liq].copy()
if segment_opts:
    filtered = filtered[filtered["Segment"].isin(segment_opts)]
if review_only:
    filtered = filtered[filtered["lcr_outflow_rate"].isna()]

st.caption(f"Showing {len(filtered):,} of {int(has_liq.sum()):,} customers with liquidity cost data")
show_cols = ["Masked Customer Number", "Segment", "avg_undrawn_12m", "lcr_outflow_rate",
            "required_hqla", "annual_liquidity_cost", "lcr_classification"]
st.dataframe(filtered[show_cols].sort_values("annual_liquidity_cost", ascending=False),
            width="stretch", height=420)
