"""L5 Retention Targeting - unpriced. Standard lever layout: app/lib/lever_page.py."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from engine.levers import assumptions as ASSUME  # noqa: E402
from engine.levers import l5_retention as L5  # noqa: E402

SIGNAL_LABELS = {"closure_request_contact": "Closure-request contact (last 12 cycles)",
                 "spend_declining": "Spend declining (last 3 vs prior 3 months)",
                 "priced_above_peer": "Priced ≥ 2 pts above peers"}


def _pct(v):
    return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"


def _extras(size, result):
    st.warning("**Unpriced.** L5 is never part of a portfolio total. The figures below are value at "
             "risk (a fact about today) and a conditional estimate under assumed leave and keep "
             "rates - not a forecast, and not recoverable value until a pilot proves it.")
    ex = size.scenarios["base"]["extras"]
    bysig = pd.DataFrame([{"Signal": SIGNAL_LABELS.get(k, k), "Customers": v["customers"],
                           "Value at risk": v["value_at_risk_usd"]} for k, v in ex["by_signal"].items()])
    st.markdown("**Value at risk by signal** (a customer can show more than one)")
    st.dataframe(bysig.style.format({"Value at risk": "${:,.0f}"}), hide_index=True, width="stretch")

    h = ex["historical_leave_rates"]
    st.markdown("**Historical leave rates vs the configured assumption** (shown for comparison - "
                "they never overwrite the configuration)")
    if h.get("available"):
        st.dataframe(pd.DataFrame([
            {"Measure": "Configured leave rate (base)", "Rate": _pct(ex["configured_leave_rate"]), "Based on": "lever_assumptions.json"},
            {"Measure": "Valued/Premier: voluntary closures, trailing 12 cycles",
             "Rate": _pct(h["valued_premier_annual_rate"]), "Based on": f"{h['valued_premier_customers']:,} customers"},
            {"Measure": "Within 12 cycles after a closure-request contact (all customers)",
             "Rate": _pct(h["after_closure_request_rate"]), "Based on": f"{h['after_closure_request_customers']:,} customers"},
            {"Measure": "Same, Valued/Premier only",
             "Rate": _pct(h["after_closure_request_valued_premier_rate"]),
             "Based on": f"{h['after_closure_request_valued_premier_customers']:,} customers"},
        ]), hide_index=True, width="stretch")
        st.caption(h["definition"])
    else:
        st.caption(f"Not available: {h.get('reason', 'no data')}")

    st.markdown("**Conditional range**")
    st.dataframe(pd.DataFrame([{
        "Scenario": s,
        "Leave rate": size.scenarios[s]["extras"]["configured_leave_rate"],
        "Keep rate": size.scenarios[s]["extras"]["configured_keep_rate"],
        "Value kept": size.scenarios[s]["components"]["value_kept"]["value_usd"],
        "Outreach + offer cost": size.scenarios[s]["components"]["outreach_cost"]["value_usd"]
                                 + size.scenarios[s]["components"]["offer_cost"]["value_usd"],
        "Conditional net": size.scenarios[s]["total_usd"],
        "Break-even keep rate": size.scenarios[s]["extras"]["breakeven_keep_rate"],
    } for s in ASSUME.SCENARIOS]).style.format({
        "Leave rate": "{:.0%}", "Keep rate": "{:.0%}", "Value kept": "${:,.0f}",
        "Outreach + offer cost": "${:,.0f}", "Conditional net": "${:,.0f}",
        "Break-even keep rate": "{:.0%}"}), hide_index=True, width="stretch")

    st.markdown("**Break-even table** - the share of would-be leavers outreach must keep to pay "
                "for itself, at different leave rates (base costs)")
    be = pd.DataFrame(L5.breakeven_table(size.inputs, size.assumptions_used))
    st.dataframe(be.rename(columns={"leave_rate": "Leave rate", "cost_per_contact_usd": "Cost per contact",
                                    "breakeven_keep_rate": "Break-even keep rate"}).style.format(
        {"Leave rate": "{:.0%}", "Cost per contact": "${:,.2f}", "Break-even keep rate": "{:.0%}"}),
        hide_index=True, width="stretch")


def _change(row, size, a):
    st.markdown("**Change:** a retention outreach contact, with an offer for those who take it up. "
                "Nothing changes in the account's terms unless an offer does - and then Reg Z "
                "change-in-terms rules apply.")


SPEC = LP.LeverSpec(
    code="L5", module=L5, unpriced=True,
    what_it_does=(
        "Spends the retention budget according to what customers are worth: only high-value "
        "customers showing an observable warning sign are contacted. The value at risk is a fact; "
        "how many would leave and how many outreach would keep are assumptions, so L5 is "
        "reported as a conditional estimate with a break-even test, never priced."),
    scope_rules=[
        "**High value:** CEV band Valued or Premier.",
        "**And at least one signal:** a closure-request contact in the trailing 12 cycles; "
        "spend in the last 3 months at most 70% of the prior 3; or a charged APR at least 2 points "
        "above the credit-score-band median.",
    ],
    regulation=[
        ("No unfair, deceptive or abusive retention practices", "UDAAP, 12 U.S.C. 5531, 5536"),
        ("Consistent treatment in who receives retention offers", "ECOA / Reg B (C-03)"),
        ("Change-in-terms notice if an offer changes account terms", "Reg Z, 12 CFR 1026.9(c)"),
    ],
    sliders=[
        LP.Slider("leave_rate", "Share of contacted customers who would leave", 0.0, 0.4, 0.01),
        LP.Slider("keep_rate", "Share of would-be leavers outreach keeps", 0.0, 1.0, 0.05),
        LP.Slider("outreach_cost_usd", "Outreach cost per contact ($)", 0.0, 30.0, 1.0),
        LP.Slider("offer_takeup", "Offer take-up", 0.0, 1.0, 0.05),
        LP.Slider("offer_cost_usd", "Offer cost ($)", 0.0, 150.0, 5.0),
    ],
    key_metric=("value_at_risk_usd", "Value at risk"),
    signal_col="reason", extras=_extras, change=_change,
    notices=["Outreach itself needs no notice; an offer that changes terms needs a Reg Z notice."],
)

st.set_page_config(page_title="L5 Retention", page_icon="🛟", layout="wide")
st.title("🛟 L5 Retention Targeting")
result = UI.require_result()
tab_value, tab_dd = st.tabs(["Overview & value", "Customer drill-down"])
with tab_value:
    LP.render_overview(SPEC, result)
with tab_dd:
    LP.render_drilldown(SPEC, result)
