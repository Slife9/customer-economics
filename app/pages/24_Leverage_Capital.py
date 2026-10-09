"""Leverage capital cost - a diagnostic completely separate from the
Liquidity (LCR) page, even though both charge something against the same
undrawn card exposure. Two different rulebooks:

  - Liquidity (12 CFR 249): a stress-scenario cash-outflow assumption.
  - Leverage (this page): a capital-adequacy backstop, risk-weight-agnostic.

Whether unused credit lines cost anything under THIS rulebook depends on
which leverage regime applies to the bank - chosen on the Home page sidebar,
never inferred from the data. See engine/core/leverage_capital.py and
governance/REGULATORY_RULEBOOK.md for the full rule basis of every figure
on this page.
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Leverage Capital", page_icon="⚖️", layout="wide")
st.title("⚖️ Leverage Capital Cost")
st.caption("Banks hold capital under two separate rulebooks. This page is about the "
          "one that ignores risk and measures size - kept apart from CEV, net economic "
          "profit, AND the Liquidity page's own cost on purpose.")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
policy = result["leverage_policy"]
warnings = result["leverage_warnings"]
audit = result["leverage_audit"]
slr_mode = bool(policy["slr_mode"])

if "leverage_capital_cost" not in cv.columns or cv["leverage_capital_cost"].isna().all():
    st.info("This upload has no card-level undrawn-exposure data, so leverage capital "
           "cost can't be assessed. This page will populate automatically once that "
           "data is present — nothing else needs to change.")
    st.stop()

has_lev = cv["leverage_capital_cost"].notna()

st.info(
    f"**Regime: {'Supplementary Leverage Ratio (SLR)' if slr_mode else 'Tier 1 leverage'}** "
    f"— {policy['case_label']} · category `{policy['bank_category']}` · policy "
    f"v{policy['policy_version']} · as of {policy['as_of_date']}"
    + (" ⚠️ **inputs not yet verified against the primary source**" if not policy.get("inputs_verified") else ""))

with st.expander("What's the difference between the two leverage regimes?"):
    st.markdown(
        "The risk-based rulebook treats unused card limits as riskless because the "
        "bank can cancel them, so they need no capital (0% CCF, 12 CFR 217.33 — this "
        "is why the Levers & Strategy page's L2 caveat says risk-based relief is "
        "\"$0 by design\"). The leverage rulebook ignores risk and measures size. "
        "**Large banks subject to the Supplementary Leverage Ratio must count 10% of "
        "every unused card limit as exposure**, so they hold real capital against "
        "idle lines. **Smaller banks use the basic Tier 1 leverage ratio**, which "
        "counts only on-balance-sheet assets, so their unused limits cost nothing "
        "under this rulebook either. This cost is shown separately and never added "
        "into NEP, because a bank's binding capital requirement is the **higher** of "
        "the two rulebooks, not their sum.")

if warnings:
    with st.expander(f"⚠️ {len(warnings)} validation warning(s) on the active policy", expanded=False):
        for w in warnings:
            st.caption(f"- {w}")

st.subheader("Portfolio summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Avg undrawn exposure (12mo)", f"${cv.loc[has_lev, 'avg_undrawn_12m'].sum():,.0f}",
         help="Same base the Liquidity page uses - average unused credit line per "
             "customer over the trailing 12 months, summed across the portfolio.")
m2.metric("Leverage exposure", f"${cv.loc[has_lev, 'leverage_exposure'].sum():,.0f}",
         help="Undrawn exposure x the commitment type's CCF (10% for unconditionally "
             "cancellable card lines, R-06). $0 under the Tier 1 regime (R-01).")
m3.metric("Capital held", f"${cv.loc[has_lev, 'leverage_capital_held'].sum():,.0f}",
         help="Leverage exposure x target leverage ratio (SLR minimum + any eSLR "
             "buffer + management buffer, R-04/R-10).")
m4.metric("Annual leverage capital cost", f"${cv.loc[has_lev, 'leverage_capital_cost'].sum():,.0f}",
         help="Capital held x (cost of capital - capital benefit rate) - the "
             "opportunity cost of holding that capital. Policy inputs, not measured.")

nep_total = cv["trailing_12m_net_economic_profit"].sum()
if nep_total:
    cost_share = cv.loc[has_lev, "leverage_capital_cost"].sum() / abs(nep_total)
    st.caption(f"Leverage capital cost is **{cost_share:.2%}** of trailing-12mo portfolio "
              f"NEP — shown for scale only, never netted against it (M-01).")

if not slr_mode and policy.get("show_shadow_value_when_inactive"):
    shadow_total = cv.loc[has_lev, "shadow_leverage_capital_cost"].sum()
    st.caption(f"**If this bank were an SLR bank (illustrative only):** leverage capital "
              f"cost would be approximately **${shadow_total:,.0f}/yr** instead of $0. "
              f"This shadow figure is never used by any calculation on this site — "
              f"display only.")

st.divider()
st.plotly_chart(C.leverage_by_segment_chart(cv), width="stretch")

st.divider()
st.subheader("By segment")
by_segment = (cv[has_lev].groupby("Segment", observed=True).agg(
    customers=("Masked Customer Number", "nunique"),
    total_undrawn_12m=("avg_undrawn_12m", "sum"),
    total_leverage_exposure=("leverage_exposure", "sum"),
    total_capital_held=("leverage_capital_held", "sum"),
    total_leverage_capital_cost=("leverage_capital_cost", "sum"),
).reset_index().sort_values("total_leverage_capital_cost", ascending=False))
st.dataframe(
    by_segment.rename(columns={
        "Segment": "Segment", "customers": "Customers",
        "total_undrawn_12m": "Total undrawn (12mo avg)",
        "total_leverage_exposure": "Total leverage exposure",
        "total_capital_held": "Total capital held",
        "total_leverage_capital_cost": "Total annual cost"}).style.format({
        "Total undrawn (12mo avg)": "${:,.0f}", "Total leverage exposure": "${:,.0f}",
        "Total capital held": "${:,.0f}", "Total annual cost": "${:,.0f}",
    }, na_rep="n/a"),
    width="stretch", height=260)

st.divider()
st.subheader("Line management (L2) — leverage component")
l2_size = result["sizes"]["L2"]
st.caption(l2_size.caveat)
st.caption("Full L2 sizing, population, and worklist live on the **Levers & Strategy** page — "
          "this is only the leverage-specific slice of that same figure (M-02: decreases "
          "free leverage capital, increases consume it, symmetrically).")

st.divider()
with st.expander("Rules applied this run (audit trail)"):
    st.caption(f"Policy file: `{audit['policy_file']}` · SHA-256 `{audit['policy_sha256'][:16]}…` · "
              f"run at {audit['run_timestamp_utc']}")
    st.caption(f"Rule IDs applied: {', '.join(audit['rule_ids_applied'])} — "
              f"see `governance/REGULATORY_RULEBOOK.md` for each citation and "
              f"`governance/regulatory_verification_log.md` for verification status "
              f"(currently all OPEN, pending human review).")
    st.json(audit["totals"])

st.divider()
st.subheader("Customer-level detail")
segment_opts = st.multiselect("Segment", sorted(cv.loc[has_lev, "Segment"].dropna().unique()))
filtered = cv[has_lev].copy()
if segment_opts:
    filtered = filtered[filtered["Segment"].isin(segment_opts)]

st.caption(f"Showing {len(filtered):,} of {int(has_lev.sum()):,} customers with leverage data")
show_cols = ["Masked Customer Number", "Segment", "avg_undrawn_12m", "commitment_type",
            "leverage_exposure", "leverage_capital_held", "leverage_capital_cost",
            "leverage_status"]
st.dataframe(filtered[show_cols].sort_values("leverage_capital_cost", ascending=False),
            width="stretch", height=420)
