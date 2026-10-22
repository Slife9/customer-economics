"""L1 Rewards & Promo Economics. Standard lever layout: app/lib/lever_page.py."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from engine.levers import assumptions as ASSUME  # noqa: E402
from engine.levers import l1_rewards as L1  # noqa: E402

FEE_LEVELS = (49, 75, 95, 125, 150, 195)


def _assumptions(result):
    a = result["sizes"]["L1"].assumptions_used
    return a or ASSUME.load()[0]["L1"]


def _extras(size, result):
    a, inp = size.assumptions_used, size.inputs
    ex = {s: size.scenarios[s]["extras"] for s in ASSUME.SCENARIOS}
    g2 = inp["group2_customers"]
    offered = ex["base"]["offered_fee"]
    st.markdown("**Groups and the fee offer**")
    st.dataframe(pd.DataFrame([
        {"Group": "Group 1 - routed reward-driven losses", "Customers": inp["group1_customers"],
         "What happens": f"Programme-level reward cost cut ({ASSUME.pick(a['group1_reward_reduction'], 'base'):.0%} base)"},
        {"Group": "Group 2 - profitable, no fee, reward-heavy", "Customers": g2,
         "What happens": "Split by fee eligibility below"},
        {"Group": f"  2a - offered the ${a['annual_fee_usd']} fee", "Customers": offered,
         "What happens": f"Reward cost >= {a['min_reward_multiple_of_fee']} x fee "
                         f"(= ${ex['base']['fee_eligibility_threshold_usd']:,.0f})"},
        {"Group": "  2b - not offered", "Customers": ex["base"]["group2_not_offered"],
         "What happens": "Reward cost below the threshold - no change"},
    ]), hide_index=True, width="stretch")
    st.caption(f"Of those offered (base): {ASSUME.pick(a['accept_share'], 'base'):.0%} accept and pay, "
               f"{ASSUME.pick(a['downgrade_share'], 'base'):.0%} downgrade to a cheaper reward tier "
               f"(reward cost cut {ASSUME.pick(a['downgrade_reward_reduction'], 'base'):.0%}), "
               f"{ASSUME.pick(a['close_share'], 'base'):.0%} close the card.")
    st.markdown("**Closure risk**")
    st.dataframe(pd.DataFrame([{
        "Scenario": s,
        "Customers who close": ex[s]["closers"],
        "Total (closers leave the card only)": size.scenarios[s]["total_usd"],
        "Total (closers leave the bank entirely)": ex[s]["total_if_closers_leave_bank"],
    } for s in ASSUME.SCENARIOS]).style.format({
        "Customers who close": "{:,.0f}", "Total (closers leave the card only)": "${:,.0f}",
        "Total (closers leave the bank entirely)": "${:,.0f}"}), hide_index=True, width="stretch")
    st.caption("If a closer takes their whole relationship (deposits, loans) with them, the loss is "
               "their relationship NEP, not just their card profit - the right-hand column.")
    st.markdown("**Fee-level sensitivity** (base scenario, same response shares - eligibility moves "
                "with the fee)")
    rows = []
    for fee in FEE_LEVELS:
        sc = L1.value_scenarios(inp, ASSUME.with_overrides(a, {"annual_fee_usd": fee}))["base"]
        rows.append({"Annual fee": fee, "Customers offered": sc["extras"]["offered_fee"],
                     "Base total": sc["total_usd"],
                     "If closers leave the bank": sc["extras"]["total_if_closers_leave_bank"]})
    st.dataframe(pd.DataFrame(rows).style.format({
        "Annual fee": "${:,.0f}", "Customers offered": "{:,.0f}", "Base total": "${:,.0f}",
        "If closers leave the bank": "${:,.0f}"}), hide_index=True, width="stretch")
    st.caption("Computed with the engine's own L1 valuation for each fee - exploration only, the "
               "configured fee is unchanged.")


def _change(row, size, a):
    g = L1.subgroup(row, a)
    if g == "Group 1":
        st.markdown(f"**Change:** review this customer's reward programme cost (programme-level cut "
                    f"of {ASSUME.pick(a['group1_reward_reduction'], 'base'):.0%} in the base case). "
                    f"No fee is offered.")
    elif g == "Group 2a":
        st.markdown(f"**Change:** offer a ${a['annual_fee_usd']} annual fee (currently "
                    f"${row['annual_fee_total']:,.2f}). Reason: ${row['reward_expense']:,.0f}/yr of "
                    f"reward value against a {a['min_reward_multiple_of_fee']}x fee threshold. "
                    f"The customer may accept, downgrade or close.")
    else:
        st.markdown(f"**Change:** none - reward cost ${row['reward_expense']:,.0f} is below the "
                    f"fee-eligibility threshold, so no fee is offered.")


SPEC = LP.LeverSpec(
    code="L1", module=L1,
    what_it_does=(
        "Charges for reward value already being delivered rather than cutting rewards. Profitable "
        "customers who take a lot of reward value with no annual fee are offered a fee aligned to "
        "that value; reward-driven loss-makers get a programme-level reward cost review. How many "
        "accept, downgrade or close is an assumption that needs a pilot."),
    scope_rules=[
        "**Group 1:** below-cost relationships whose dominant cost is reward expense (routed to L1).",
        "**Group 2:** profitable relationships with no annual fee and at least $100 a year of reward cost.",
        "**Group 2a (offered the fee):** Group 2 with reward cost at least the configured multiple of the fee.",
        "**Group 2b (not offered):** the rest of Group 2.",
    ],
    regulation=[
        ("45 days' advance notice of a new or changed annual fee", "Reg Z, 12 CFR 1026.9(c)(2)"),
        ("Customer's right to reject the change", "Reg Z, 12 CFR 1026.9(h)"),
        ("First-year fee limit", "Reg Z, 12 CFR 1026.52(a)"),
        ("Consistent treatment across protected groups", "ECOA / Reg B (C-03)"),
    ],
    sliders=[
        LP.Slider("annual_fee_usd", "Annual fee ($)", 25, 250, 5, "int"),
        LP.Slider("min_reward_multiple_of_fee", "Eligibility: reward cost ≥ multiple × fee", 1.0, 4.0, 0.25),
        LP.Slider("accept_share", "Share who accept the fee", 0.0, 1.0, 0.05),
        LP.Slider("downgrade_share", "Share who downgrade", 0.0, 1.0, 0.05),
        LP.Slider("close_share", "Share who close the card", 0.0, 0.5, 0.01),
        LP.Slider("downgrade_reward_reduction", "Reward cost cut on downgrade", 0.0, 1.0, 0.05),
        LP.Slider("group1_reward_reduction", "Group 1 programme reward cut", 0.0, 0.6, 0.05),
    ],
    key_metric=("reward_expense", "Reward cost 12m"),
    extras=_extras, change=_change,
    rules=lambda row, result: L1.selection_rules(row, _assumptions(result)),
    notices=["Fee offer: 45-day advance notice and the right to reject (Reg Z)."],
)

st.set_page_config(page_title="L1 Rewards", page_icon="🎁", layout="wide")
st.title("🎁 L1 Rewards & Promo Economics")
result = UI.require_result()
tab_value, tab_dd = st.tabs(["Overview & value", "Customer drill-down"])
with tab_value:
    LP.render_overview(SPEC, result)
with tab_dd:
    LP.render_drilldown(SPEC, result)
