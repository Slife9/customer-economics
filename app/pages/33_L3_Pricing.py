"""L3 Value-Based Pricing. Standard lever layout: app/lib/lever_page.py."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from engine.levers import assumptions as ASSUME  # noqa: E402
from engine.levers import l3_pricing as L3  # noqa: E402


def _extras(size, result):
    inp = size.inputs
    ex = {s: size.scenarios[s]["extras"] for s in ASSUME.SCENARIOS}
    c1, c2, c3 = st.columns(3)
    c1.metric("Flagged (priced below peers)", f"{inp['flagged']:,}")
    c2.metric("Targeted (revolvers only)", f"{inp['targeted']:,}",
              help="A pay-in-full customer has no interest to reprice, so is flagged but not targeted.")
    c3.metric("Revolving balance targeted", f"${inp['targeted_revolving_balance_usd']:,.0f}")
    st.markdown("**Year 1 vs steady state, and the leaver risk**")
    st.dataframe(pd.DataFrame([{
        "Scenario": s,
        "Year 1": size.scenarios[s]["total_usd"],
        "Steady state (all balances repriced)": ex[s]["steady_state"],
        "Expected leavers": ex[s]["leavers"],
        "Year 1 if leavers leave the bank": ex[s]["total_if_leavers_leave_bank"],
    } for s in ASSUME.SCENARIOS]).style.format({
        "Year 1": "${:,.0f}", "Steady state (all balances repriced)": "${:,.0f}",
        "Expected leavers": "{:,.1f}", "Year 1 if leavers leave the bank": "${:,.0f}"}),
        hide_index=True, width="stretch")
    st.caption("Year 1 is small because the CARD Act lets a new rate apply only to NEW "
               "transactions: existing balances keep their old rate, so only the share repriced "
               "within the year earns the gap. Steady state is the value once the whole revolving "
               "balance has turned over. If a leaver takes their whole relationship, the loss is "
               "their relationship NEP, not just card profit (right-hand column).")
    st.markdown("**CARD Act constraints built into the method:** no increase in the account's "
                "first year (excluded); new rate on new transactions only; 45 days' notice; "
                "rate increases re-evaluated at least every six months.")


def _change(row, size, a):
    c1, c2, c3 = st.columns(3)
    c1.metric("Current APR", f"{row['current_apr']:.2f}%")
    c2.metric("Target APR (peer median)", f"{row['target_apr']:.2f}%",
              f"{row['target_apr'] - row['current_apr']:+.2f} pts")
    c3.caption("Applies to new transactions only, after 45 days' notice; existing balances "
               "keep the current rate.")


SPEC = LP.LeverSpec(
    code="L3", module=L3,
    what_it_does=(
        "Reprices accounts whose risk has drifted since origination while their rate hasn't: "
        "charged meaningfully below customers with the same credit-score band. Only revolving "
        "balance earns the gap, only on new transactions, and some customers will leave or pay "
        "down - all assumptions a champion/challenger test must confirm."),
    scope_rules=[
        "**Flagged:** charged APR at least 2 points below the median of the same credit-score "
        "band, or routed to L3 (credit-cost loss priced below peers).",
        "**Excluded:** accounts in their first 12 months (CARD Act), including routed ones.",
        "**Targeted:** flagged accounts that revolve (revolving balance > $0).",
    ],
    regulation=[
        ("No rate increase in the first year", "Reg Z, 12 CFR 1026.55"),
        ("New rate applies to new transactions only", "Reg Z, 12 CFR 1026.55(b)"),
        ("45 days' advance notice", "Reg Z, 12 CFR 1026.9(c)(2)"),
        ("Re-evaluate rate increases at least every six months", "Reg Z, 12 CFR 1026.59"),
        ("Fair-lending review of the repricing worklist", "ECOA / Reg B (C-03)"),
    ],
    sliders=[
        LP.Slider("year1_balance_repriced", "Share of balance repriced in year 1", 0.0, 1.0, 0.05),
        LP.Slider("attrition", "Share of targeted customers who leave", 0.0, 0.4, 0.01),
        LP.Slider("balance_reduction_stayers", "Balance pay-down among stayers", 0.0, 0.5, 0.05),
        LP.Slider("notice_cost_usd", "Notice cost per account ($)", 0.0, 5.0, 0.25),
    ],
    key_metric=("latest_purchase_balance", "Purchase balance"),
    extras=_extras, change=_change,
    notices=["Rate increase: 45-day change-in-terms notice (Reg Z); new transactions only."],
)

st.set_page_config(page_title="L3 Pricing", page_icon="💲", layout="wide")
st.title("💲 L3 Value-Based Pricing")
result = UI.require_result()
tab_value, tab_dd = st.tabs(["Overview & value", "Customer drill-down"])
with tab_value:
    LP.render_overview(SPEC, result)
with tab_dd:
    LP.render_drilldown(SPEC, result)
