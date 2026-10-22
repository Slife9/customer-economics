"""L4 Cost-to-Serve Migration. Standard lever layout: app/lib/lever_page.py."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from engine.levers import assumptions as ASSUME  # noqa: E402
from engine.levers import l4_cost_to_serve as L4  # noqa: E402


def _extras(size, result):
    ex = size.scenarios["base"]["extras"]
    inp = size.inputs
    c1, c2, c3 = st.columns(3)
    c1.metric("Annual avoidable calls", f"{ex['annual_avoidable_calls']:,.0f}",
              help="Billing, rewards and rate queries, trailing 12 cycles, this population.")
    c2.metric("Annual paper statements", f"{ex['annual_paper_statements']:,.0f}")
    c3.metric("Calls avoided per month (base)", f"{ex['avoided_calls_per_month']:,.0f}")
    st.markdown("**Year 1 vs year 2**")
    st.dataframe(pd.DataFrame([{
        "Scenario": s,
        "Year 1 (after outreach cost)": size.scenarios[s]["total_usd"],
        "From year 2 (no outreach)": size.scenarios[s]["extras"]["from_year2"],
    } for s in ASSUME.SCENARIOS]).style.format({
        "Year 1 (after outreach cost)": "${:,.0f}", "From year 2 (no outreach)": "${:,.0f}"}),
        hide_index=True, width="stretch")
    bridge = L4.correction_bridge(inp, size.assumptions_used, "base")
    if bridge:
        st.markdown("**Correction bridge** - from the pre-rebuild system figure to the corrected "
                    "year-1 value, one correction at a time (base scenario)")
        st.dataframe(pd.DataFrame(bridge).rename(columns={
            "step": "Step", "what": "What changes", "value": "Running figure"}).style.format(
            {"Running figure": "${:,.0f}"}), hide_index=True, width="stretch")
    st_ = ex["staffing_step"]
    st.markdown(
        f"**Staffing step (information only, never in the total).** Portfolio call volume "
        f"{st_['monthly_calls_before']:,.0f}/month before → {st_['monthly_calls_after']:,.0f}/month "
        f"after (base). Fixed capacity cost {UI_money(st_['fixed_cost_monthly_before_usd'])} → "
        f"{UI_money(st_['fixed_cost_monthly_after_usd'])} a month: annual step saving "
        f"**{UI_money(st_['annual_step_saving_usd'])}**. {st_['note']}")
    st.caption("Unit costs: " + ", ".join(f"{k} ${v:.2f} ({inp['unit_cost_sources'][k]})"
                                          for k, v in inp["unit_costs"].items()) + ".")


def UI_money(v):
    return f"${v:,.0f}"


def _recent(row, col, label):
    v = row.get(col)
    return f" ({v:.0f} {label} in the last 12 cycles)" if v is not None and pd.notna(v) else ""


def _change(row, size, a):
    if row["action"] == "ENABLE_SELF_SERVICE":
        st.markdown("**Change:** steer billing, rewards and rate queries to digital self-service"
                    + _recent(row, "annual_avoidable_calls_t12", "avoidable calls") + ".")
    elif row["action"] == "MIGRATE_TO_DIGITAL_STATEMENTS":
        st.markdown("**Change:** offer e-statements with E-SIGN consent"
                    + _recent(row, "annual_paper_statements_t12", "paper statements") + ".")
    else:
        st.markdown("**Change:** review this routed servicing-cost loss; no automatic migration.")


SPEC = LP.LeverSpec(
    code="L4", module=L4,
    what_it_does=(
        "Moves avoidable servicing demand to cheaper channels: billing, rewards and rate queries "
        "to digital self-service, and paper statements to e-statements. No customer-facing "
        "price or limit change; the saving is real only to the extent customers actually move, "
        "which is an assumption a pilot should test."),
    scope_rules=[
        "**Self-service:** at least 3 avoidable calls (billing, rewards, rate) in the data window.",
        "**Digital statements:** at least 6 paper statements in the data window.",
        "**Review:** below-cost relationships routed to L4 because servicing cost they caused dominates.",
        "Valuation uses only the **trailing 12 cycles** of each customer's activity.",
    ],
    regulation=[
        ("Customer consent before replacing paper with electronic disclosures", "E-SIGN Act, 15 U.S.C. 7001(c)"),
        ("Electronic delivery of card disclosures", "Reg Z, 12 CFR 1026.5(a)(1)(iii)"),
        ("Keep paper / phone service for customers who need it (excluded share)", "UDAAP; accessibility"),
    ],
    sliders=[
        LP.Slider("call_deflection", "Share of avoidable calls deflected", 0.0, 1.0, 0.05),
        LP.Slider("paper_migration", "Share of paper statements migrated", 0.0, 1.0, 0.05),
        LP.Slider("excluded_share", "Share excluded (must keep paper/phone)", 0.0, 0.5, 0.05),
        LP.Slider("outreach_cost_usd", "Outreach cost per customer, year 1 ($)", 0.0, 5.0, 0.25),
        LP.Slider("sessions_per_deflected_call", "Digital sessions per deflected call", 0, 6, 1, "int"),
    ],
    key_metric=("annual_avoidable_calls_t12", "Avoidable calls, last 12 cycles"),
    extras=_extras, change=_change,
    notices=["No customer notice for self-service steering; e-statements need E-SIGN consent."],
)

st.set_page_config(page_title="L4 Cost to Serve", page_icon="⚙️", layout="wide")
st.title("⚙️ L4 Cost-to-Serve Migration")
result = UI.require_result()
tab_value, tab_dd = st.tabs(["Overview & value", "Customer drill-down"])
with tab_value:
    LP.render_overview(SPEC, result)
with tab_dd:
    LP.render_drilldown(SPEC, result)
