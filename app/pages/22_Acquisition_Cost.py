"""Customer Acquisition Cost (CAC) & payback - a deliberately separate page.

This is a LIFETIME view, not a trailing-window one. CEV and
trailing_12m_net_economic_profit (Portfolio Economics, Levers & Strategy)
answer "how is this customer doing lately." This page answers a different
question: "has this relationship paid back what it cost to acquire it, and
how long did that take." Blending the two would mean assuming an
amortization schedule for CAC - see engine/core/customer_view.py and
ARCHITECTURE.md section 4 for why that line is deliberately not crossed.
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Acquisition Cost", page_icon="💰", layout="wide")
st.title("💰 Acquisition Cost & Payback")
st.caption("Has what we spent to acquire each customer actually been earned back — and how "
          "long did it take? A lifetime view, kept separate from CEV on purpose.")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]

if "acquisition_cost_usd" not in cv.columns or cv["acquisition_cost_usd"].isna().all():
    st.info("This upload has no `Table23_Acquisition.csv` with an `Acquisition Cost USD` "
           "column, so payback can't be assessed. This page will populate automatically "
           "once that data is present — nothing else needs to change.")
    st.stop()

has_cac = cv["acquisition_cost_usd"].notna()
measurable = cv[cv["cac_payback_status"].isin(["Recovered", "Not yet recovered"])]
recovered = cv[cv["cac_payback_status"] == "Recovered"]

st.subheader("Portfolio summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total acquisition cost on file", f"${cv.loc[has_cac, 'acquisition_cost_usd'].sum():,.0f}",
         help="Sum of Acquisition Cost USD across every customer with a record in "
             "Table23_Acquisition.csv.")
m2.metric("Customers with a measurable payback window", f"{len(measurable):,}",
         help="Has both a known acquisition cost AND a genuine (non-floored) account-open "
             "cycle within the data window. Everyone else is reported as Unknown, not guessed.")
m3.metric("Recovered, of those measurable",
         f"{len(recovered) / max(len(measurable), 1):.0%}" if len(measurable) else "n/a")
m4.metric("Average months to recover", f"{recovered['cac_payback_months'].mean():.1f}"
         if len(recovered) else "n/a")

st.divider()
col1, col2 = st.columns([1, 1])
with col1:
    st.plotly_chart(C.cac_payback_status_chart(cv), width="stretch")
    st.caption("Most of a demo-scale portfolio predates the data window (see "
              "`generator/README.md`), so **Unknown — predates observation window** is "
              "expected to be the largest bar here, not a gap to chase.")
with col2:
    if len(recovered):
        st.plotly_chart(C.cac_payback_months_histogram(cv), width="stretch")
    else:
        st.info("No customer in this portfolio has both a measurable payback window and "
               "a recovered acquisition cost yet.")

st.divider()
st.subheader("By acquisition channel")
st.caption("Complements the Channel Quality Review lever (L6): L6 ranks channels by net "
          "customer value after CAC; this shows what share of each channel's own cohort "
          "has actually earned its acquisition cost back, and how long that took.")
by_channel = C.cac_by_channel_table(cv)
if len(by_channel):
    display = by_channel.rename(columns={
        "acquisition_channel": "Channel", "customers": "Customers",
        "avg_acquisition_cost": "Avg CAC ($)",
        "measurable_customers": "Measurable",
        "recovered_share_of_measurable": "Recovered (of measurable)",
        "avg_months_to_recover": "Avg months to recover"})
    st.dataframe(
        display.style.format({
            "Avg CAC ($)": "${:,.0f}",
            "Recovered (of measurable)": "{:.0%}",
            "Avg months to recover": "{:.1f}",
        }, na_rep="n/a"),
        width="stretch", height=260)
else:
    st.caption("No channel data available.")

st.divider()
st.subheader("Customer-level detail")
f1, f2 = st.columns(2)
channel_opts = f1.multiselect("Acquisition Channel",
                              sorted(cv["acquisition_channel"].dropna().unique()))
status_opts = f2.multiselect("Payback Status", C.CAC_STATUS_ORDER)

filtered = cv[has_cac].copy()
if channel_opts:
    filtered = filtered[filtered["acquisition_channel"].isin(channel_opts)]
if status_opts:
    filtered = filtered[filtered["cac_payback_status"].isin(status_opts)]

st.caption(f"Showing {len(filtered):,} of {int(has_cac.sum()):,} customers with acquisition cost data")
show_cols = ["Masked Customer Number", "acquisition_channel", "acquisition_cost_usd",
            "cumulative_net_value_since_acquisition", "cac_payback_months",
            "cac_payback_status"]
st.dataframe(filtered[show_cols].sort_values("cac_payback_status"),
            width="stretch", height=420)
