"""L2 Credit Lines & Unused-Line Cost.

Merges what used to be three places: L2's strategy card (Levers & Strategy),
the Liquidity page (app/lib/sections/liquidity.py) and the ML Credit Limit
page (app/lib/sections/ml_credit_limit.py). ML treatment fairness moved to
Governance & Fairness. Standard lever layout: app/lib/lever_page.py.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.lib import lever_page as LP  # noqa: E402
from app.lib import lever_ui as UI  # noqa: E402
from app.lib import nav  # noqa: E402
from app.lib.sections import liquidity, ml_credit_limit  # noqa: E402
from engine.levers import l2_lines as L2  # noqa: E402

ML_FOR_L2 = {"INCREASE_LIMIT": "INCREASE", "DECREASE_LIMIT": "DECREASE_UNUSED_EXPOSURE"}


def _extras(size, result):
    ex = size.scenarios["base"]["extras"]
    st.markdown("**Carrying cost of unused lines, by L2 group** (the core of the L2 story - "
                "an idle line is not free to keep open)")
    _carrying_table(ex["carrying_cost_by_group"])
    st.caption(
        f"Dormant-line right-sizing (base): **${ex['dormant_rightsizing']:,.0f}/yr**, "
        f"{'INCLUDED in' if ex['dormant_rightsizing_enabled'] else 'not included in'} the "
        f"total (feature flag `dormant_rightsizing_enabled`, default off pending a business "
        f"decision). Funding rate used for increases: {ex['funding_rate']:.3%} "
        f"(card funding cost ÷ drawn balances).")


def _carrying_table(rows):
    t = pd.DataFrame(rows).rename(columns={
        "action": "L2 group", "customers": "Customers", "unused_lines_usd": "Unused lines",
        "required_hqla_usd": "Required HQLA", "liquidity_cost_usd": "Liquidity cost / yr",
        "slr_cost_usd": "SLR cost / yr", "card_net_usd": "Card net / yr",
        "card_net_after_carrying_cost_usd": "Card net after carrying cost / yr"})
    money = ["Unused lines", "Required HQLA", "Liquidity cost / yr", "SLR cost / yr",
             "Card net / yr", "Card net after carrying cost / yr"]
    st.dataframe(t.style.format({c: "${:,.0f}" for c in money}), hide_index=True, width="stretch")


def _change(row, size, a):
    ch = L2.proposed_change(row, a)
    c1, c2, c3 = st.columns(3)
    c1.metric("Current limit", f"${ch['current_limit']:,.0f}")
    c2.metric("Proposed limit", f"${ch['proposed_limit']:,.0f}",
              f"{ch['proposed_limit'] - ch['current_limit']:+,.0f}")
    c3.caption(f"Rule: {ch['rule']}")


def _ml_compare(row, result):
    st.markdown("**Second opinion: the ML credit-limit model, same customer**")
    if not result.get("ml_available") or pd.isna(row.get("ml_action")):
        st.caption("No ML recommendation for this customer (model unavailable or account not scored).")
        return
    ml = str(row["ml_action"])
    expected = ML_FOR_L2.get(str(row["action"]))
    agree = expected is not None and ml == expected
    no_change = str(row["action"]) in ("REACTIVATION_CAMPAIGN", "DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE")
    msg = (f"L2: `{row['action']}` · ML: `{ml}` (recommended limit "
           f"${row.get('ml_recommended_limit', float('nan')):,.0f}; reason: {row.get('ml_primary_reason', 'n/a')})")
    if agree or (no_change and ml in ("MAINTAIN", "FREEZE_NO_INCREASE")):
        st.success("✅ **Agree.** " + msg)
    else:
        st.warning("⚠️ **Disagree - worth a second look.** " + msg)


SPEC = LP.LeverSpec(
    code="L2", module=L2,
    what_it_does=(
        "Moves credit limits in both directions, based on 12 months of observed behaviour, "
        "never a single-month snapshot. Idle lines are trimmed, dormant ones get a "
        "reactivation campaign first, and genuinely stretched good-standing accounts get "
        "more room. Every unused line carries a real cost: regulatory liquidity (LCR) "
        "and, under the SLR, leverage capital."),
    scope_rules=[
        "**Seasoned and in good standing:** account at least 12 months old and 0 days past due "
        "(all groups except routed losses).",
        "**Dormant → reactivation campaign:** average utilisation ≤ 10%, peak ≤ 20%, spend ≤ 15% of "
        "the limit and inactive at least half the year, on a limit above $1,000.",
        "**Idle, light use → decrease:** average ≤ 10%, peak ≤ 20%, spend ≤ 50% of the limit, "
        "limit above $1,000, and not already dormant.",
        "**Active pay-in-full transactor → deepen, no limit change:** low ending balances but spend "
        "above 50% of the limit, paid in full at least half the months.",
        "**Stretched → increase:** peak utilisation ≥ 75%, good standing, credit score ≥ 660.",
        "**Routed credit-cost losses → decrease:** below-cost relationships whose dominant cost is "
        "credit loss, priced in line with peers (routing).",
    ],
    regulation=[
        ("Adverse-action notice on any limit decrease", "ECOA / Reg B, 12 CFR 1002.9 (C-01)"),
        ("Credit-limit reduction notice rules", "Reg Z, 12 CFR 1026.9(g)(4) (C-02)"),
        ("Fair-lending review of who is cut and who is raised", "ECOA, 15 U.S.C. 1691; Reg B (C-03)"),
        ("Reasons for each decision documented", "C-04"),
        ("Liquidity on undrawn retail commitments", "LCR, 12 CFR Part 249"),
        ("Leverage exposure includes off-balance-sheet lines; 10% CCF in the SLR",
         "12 CFR 217.10 (R-05, R-06)"),
        ("Tier 1 leverage ratio charges no unused lines", "12 CFR 217.10 (R-01)"),
        ("Risk-based capital: 0% CCF on unconditionally cancellable lines", "12 CFR 217.33 (R-09)"),
    ],
    sliders=[
        LP.Slider("decrease_implemented", "Share of decreases implemented", 0.0, 1.0, 0.05),
        LP.Slider("card_life_years", "Card life (years) to annualise lifetime PD", 1, 5, 1, "int"),
        LP.Slider("increase_pct", "Limit increase size", 0.05, 0.50, 0.05),
        LP.Slider("headroom_used", "Share of new headroom customers use", 0.0, 1.0, 0.05),
        LP.Slider("reactivation_rate", "Reactivation success rate", 0.0, 0.30, 0.01),
        LP.Slider("campaign_cost_usd", "Campaign cost per dormant customer ($)", 0.0, 10.0, 0.5),
        LP.Slider("dormant_rightsizing_enabled", "Include dormant-line right-sizing", kind="bool"),
    ],
    key_metric=("peak_utilization_12m", "Peak utilisation 12m"),
    extras=_extras, change=_change, customer_extra=_ml_compare,
    notices=["Decrease: Reg B adverse-action notice and Reg Z limit-reduction rules apply "
             "before the change takes effect.",
             "Increase: no adverse-action notice; document the reason (C-04)."],
)


st.set_page_config(page_title="L2 Credit Lines", page_icon="📈", layout="wide")
st.title("📈 L2 Credit Lines & Unused-Line Cost")
result = UI.require_result()
UI.regime_label(result)
size = result["sizes"]["L2"]

tab_value, tab_carry, tab_ml, tab_dd = st.tabs(
    ["Overview & value", "Unused-line carrying cost", "ML second opinion", "Customer drill-down"])

with tab_value:
    LP.render_overview(SPEC, result)

with tab_carry:
    st.subheader("Why an unused line costs money")
    policy_name = UI.active_leverage_policy(result)
    liq = json.loads((ROOT / "engine" / "config" / "liquidity_policy.json").read_text(encoding="utf-8"))
    lev_path = ROOT / "engine" / "config" / f"leverage_capital_policy.{policy_name}.json"
    lev = json.loads(lev_path.read_text(encoding="utf-8")) if lev_path.exists() else {}
    gap = liq["lending_yield_annual"] - liq["hqla_yield_annual"]
    st.markdown(
        f"**Liquidity (LCR, 12 CFR Part 249).** Regulators assume part of every unused retail "
        f"line is drawn in a 30-day stress, so the bank holds High-Quality Liquid Assets (HQLA) "
        f"against it: `required HQLA = average undrawn line × outflow rate` "
        f"(retail {liq['default_outflow_rate']:.0%}; small business "
        f"{liq['lcr_outflow_rate_by_segment'].get('Small Business', liq['default_outflow_rate']):.0%}). "
        f"Holding HQLA instead of lending costs the yield gap: `annual liquidity cost = HQLA × "
        f"({liq['lending_yield_annual']:.1%} lending yield − {liq['hqla_yield_annual']:.1%} HQLA "
        f"yield)` = **{gap:.1%} of required HQLA**.")
    if lev.get("slr_mode"):
        target = lev["slr_minimum"] + lev.get("eslr_buffer", 0) + lev.get("management_buffer", 0)
        ccf = lev["slr_ccf_by_commitment_type"]["UNCONDITIONALLY_CANCELLABLE"]
        cost_gap = lev["cost_of_capital_annual"] - lev.get("capital_benefit_rate_annual", 0)
        st.markdown(
            f"**Leverage capital (SLR, 12 CFR 217.10).** Under `{policy_name}` the Supplementary "
            f"Leverage Ratio counts unused lines at a **{ccf:.0%} CCF** (R-06), unlike risk-based "
            f"capital's 0% (R-09): `SLR cost = undrawn × {ccf:.0%} × {target:.1%} target ratio × "
            f"{cost_gap:.0%} cost of capital` = **{ccf * target * cost_gap:.4%} of the undrawn line "
            f"per year**.")
    else:
        st.markdown(f"**Leverage capital.** Under `{policy_name}` the bank is assessed on the Tier 1 "
                    f"leverage ratio, which counts on-balance-sheet assets only (R-01) - unused "
                    f"lines carry **no** leverage capital, so the SLR components are $0.")
    st.caption("Both are diagnostics, kept out of NEP and CEV on purpose; L2 uses each customer's "
               "own already-computed rate (cost per undrawn dollar) when it values a decrease or "
               "an increase. Citations to be confirmed by compliance.")
    st.subheader("Carrying cost by L2 group")
    if size.has_scenarios:
        _carrying_table(size.scenarios["base"]["extras"]["carrying_cost_by_group"])
    else:
        UI.pre_rebuild_notice(size)
    st.divider()
    liquidity.render(result)

with tab_ml:
    ml_credit_limit.render(result)

with tab_dd:
    LP.render_drilldown(SPEC, result)
