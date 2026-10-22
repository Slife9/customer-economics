"""L6 Channel Quality Review - repurposes the former Acquisition Cost page
(its CAC payback content is app/lib/sections/acquisition.py, kept intact).
Standard lever layout: app/lib/lever_page.py. L6 is valued at channel level:
there is no per-customer figure."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from app.lib.sections import acquisition  # noqa: E402
from engine.levers import l6_crosssell as L6  # noqa: E402


def _extras(size, result):
    ex = size.scenarios["base"]["extras"]
    st.markdown("**Channel table** - customers acquired within the observation window")
    t = pd.DataFrame(ex["channel_table"]).rename(columns={
        "channel": "Channel", "customers_in_window": "Acquired in window",
        "new_customers_per_year": "New customers / yr", "mean_cac_usd": "Mean CAC",
        "mean_trailing_12m_nep_usd": "Mean NEP (12m)", "nep_per_cac_dollar": "NEP per CAC $",
        "annual_acquisition_spend_usd": "Acquisition spend / yr",
        "payback_years_simple": "Simple payback (yrs)"})
    st.dataframe(t.style.format({"New customers / yr": "{:,.0f}", "Mean CAC": "${:,.0f}",
                                 "Mean NEP (12m)": "${:,.0f}", "NEP per CAC $": "{:.2f}",
                                 "Acquisition spend / yr": "${:,.0f}",
                                 "Simple payback (yrs)": "{:.1f}"}, na_rep="n/a"),
                 hide_index=True, width="stretch")
    sc = {s: size.scenarios[s]["extras"] for s in ("low", "base", "high")}
    c1, c2, c3 = st.columns(3)
    c1.metric("Budget moved per year", f"${ex['budget_shifted_usd']:,.0f}",
              help=f"From {ex['worst']} (worst NEP per CAC $) to {ex['best']} (best). Budget-neutral.")
    c2.metric("Customers lost / gained (base)",
              f"{ex['customers_lost']:,.0f} / {ex['customers_gained']:,.0f}")
    c3.metric("Break-even quality (base)", f"{ex['breakeven_quality']:.0%}",
              help="The best channel's new customers must be at least this good, relative to "
                   "its current customers, for the shift to break even.")
    st.markdown(f"**{ex['build_years']}-year build** (the same shift repeated, with "
                f"{1 - size.assumptions_used['annual_attrition']:.0%} of each year's cohort "
                f"retained): low **${sc['low']['after_n_years']:,.0f}** · base "
                f"**${sc['base']['after_n_years']:,.0f}** · high **${sc['high']['after_n_years']:,.0f}** "
                f"per year by year {ex['build_years']}.")
    st.caption(f"Sanity check: the base value (${size.scenarios['base']['total_usd']:,.0f}) is below "
               f"total annual acquisition spend (${ex['annual_acquisition_spend_usd']:,.0f}). In this "
               f"synthetic demo the channel quality gap is planted by the generator - finding it shows "
               f"the detection works, it is not a business finding.")


def _ranking(result):
    memo = LP._memo(result)
    if "l6_ranking" not in memo:
        memo["l6_ranking"] = L6.population_channel_ranking(result["customer_view"])
    return memo["l6_ranking"]


def _change(row, size, a):
    st.caption("A sourcing decision, not a customer action: nothing changes for this customer. "
               "Future acquisition budget moves between channels.")


SPEC = LP.LeverSpec(
    code="L6", module=L6, per_customer=False,
    what_it_does=(
        "Ranks acquisition channels by the customer value they actually produced per acquisition "
        "dollar, then values moving part of the worst channel's budget to the best channel. Only "
        "future acquisitions change - existing customers are not touched - and the new channel "
        "is assumed to cost more at the margin and bring somewhat weaker customers."),
    scope_rules=[
        "**Population:** customers acquired through the bottom third of channels, ranked by mean "
        "trailing-12m NEP minus mean acquisition cost.",
        "**Valuation inputs:** customers acquired within the observation window (CAC payback "
        "status Recovered or Not yet recovered), by channel.",
        "**Worst / best channel:** lowest / highest mean NEP per acquisition-cost dollar.",
    ],
    regulation=[
        ("Fair-lending and redlining review of where acquisition marketing goes", "ECOA / Reg B (C-03)"),
        ("Prescreened credit offers", "FCRA, 15 U.S.C. 1681b(c), 1681m(d)"),
        ("Unfair, deceptive or abusive marketing practices", "UDAAP, 12 U.S.C. 5531, 5536"),
    ],
    sliders=[
        LP.Slider("budget_shift_share", "Share of the worst channel's budget moved", 0.0, 1.0, 0.05),
        LP.Slider("marginal_cac_multiplier", "Marginal CAC multiplier in the best channel", 1.0, 4.0, 0.1),
        LP.Slider("incremental_quality", "Quality of incremental customers vs current", 0.3, 1.2, 0.05),
        LP.Slider("annual_attrition", "Annual attrition of acquired customers", 0.0, 0.3, 0.01),
        LP.Slider("build_years", "Build years", 1, 5, 1, "int"),
    ],
    key_metric=("trailing_12m_net_economic_profit", "Trailing-12m NEP"),
    extras=_extras, change=_change,
    rules=lambda row, result: L6.selection_rules(row, _ranking(result)),
    notices=["No customer notice: a budget decision, no customer contact."],
)

st.set_page_config(page_title="L6 Channel Quality", page_icon="🧭", layout="wide")
st.title("🧭 L6 Channel Quality Review")
result = UI.require_result()

tab_value, tab_cac, tab_dd = st.tabs(
    ["Overview & value", "Acquisition cost & payback", "Customer drill-down"])
with tab_value:
    LP.render_overview(SPEC, result)
with tab_cac:
    acquisition.render(result)
with tab_dd:
    LP.render_drilldown(SPEC, result)
