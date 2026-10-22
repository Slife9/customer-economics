"""ProfitInsight Customer Economics System — landing page (the Home entry
in the grouped navigation defined by app/Home.py, which is the entrypoint:
    streamlit run app/Home.py
"""

from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import pipeline_runner as PR, charts as C, presentation as P
from app.lib import results_bundle as RB
from engine.core.contract import DataContractViolation

# This deployment runs under one fixed leverage regime rather than letting
# each session pick one: Case A, the Supplementary Leverage Ratio (SLR),
# Category III - unused card lines ARE charged capital here, unlike under
# risk-based capital's 0% CCF or the basic Tier 1 leverage ratio (Case B),
# which doesn't charge them at all. See engine/config/
# leverage_capital_policy.case_a_slr_category_iii.json for the policy itself.
LEVERAGE_POLICY_NAME = "case_a_slr_category_iii"

st.set_page_config(page_title="ProfitInsight — Customer Economics System",
                  page_icon="💳", layout="wide")

st.title("💳 ProfitInsight Customer Economics System")
st.caption("What is each customer worth, after every cost — and which of six "
          "levers actually fixes it.")
st.markdown(P.legend(), unsafe_allow_html=True)

with st.sidebar:
    st.header("1 · Load a portfolio")
    demo_zip = st.file_uploader(
        "Portfolio to analyze (zip of the table CSVs)", type="zip", key="demo_zip")
    st.caption("e.g. `generator/out/demo` zipped up")

    run_clicked = st.button("Run analysis", type="primary", width="stretch",
                            disabled=demo_zip is None)

    st.divider()
    sample_dir = Path(__file__).resolve().parents[2] / "samples"
    sample_bundle_path = sample_dir / "demo_portfolio_50k_bundle.zip"
    sample_available = sample_bundle_path.exists()
    sample_clicked = st.button(
        "Try it with the bundled sample portfolio (50,000 customers)", width="stretch",
        disabled=not sample_available,
        help="Loads samples/demo_portfolio_50k_bundle.zip from this project - "
            "a pre-computed results bundle, not a live engine run - no file "
            "picker needed. (No negative-control gate demo on this path; see "
            "the Governance page's own note.)")

    st.divider()
    st.header("2 · Or load pre-computed results")
    st.caption("For a portfolio too large to upload or re-analyse on this "
              "instance — export one locally with "
              "`python -m engine.export_bundle`, then load the bundle here.")
    bundle_zip = st.file_uploader(
        "Load pre-computed results (.zip)", type="zip", key="bundle_zip")
    load_bundle_clicked = st.button(
        "Load bundle", width="stretch", disabled=bundle_zip is None)

if sample_clicked:
    with st.spinner("Loading the bundled sample portfolio…"):
        # This is a pre-computed results bundle (see ARCHITECTURE.md §8a),
        # not a live engine run - the same reasoning that motivated the
        # whole bundle feature (a 50,000-customer live run needs ~7GB of
        # memory) applies here too, so the "try it" demo uses a bundle at
        # this size rather than running the engine in-process. Drop any
        # previously-loaded result first so it doesn't stack in memory.
        st.session_state.pop("result", None)
        st.session_state.pop("control_result", None)
        PR._cached_pipeline.clear()
        result, bundle_meta, gate_report = RB.load_bundle_from_bytes(
            sample_bundle_path.read_bytes(), sample_bundle_path.name)
        st.session_state["result"] = result
        st.session_state["result_root"] = f"<bundle: {sample_bundle_path.name}>"
        st.session_state["demo_label"] = f"{bundle_meta.portfolio_label} (pre-computed)"
        st.session_state["bundle_metadata"] = bundle_meta
        st.session_state.pop("gate_report", None)  # no negative control for this sample

if run_clicked and demo_zip is not None:
    with st.spinner("Validating data contract, building the ledger, routing levers…"):
        try:
            result, root = PR.run_pipeline_for_upload(demo_zip, "demo", LEVERAGE_POLICY_NAME)
            st.session_state["result"] = result
            st.session_state["result_root"] = str(root)
            st.session_state["demo_label"] = demo_zip.name
        except DataContractViolation as e:
            st.error(f"**Data contract violation — refusing to run.**\n\n{e}")
            st.stop()
    # No negative-control upload for a user-supplied portfolio (the sidebar
    # control for that was removed) - clear any stale gate from a previous
    # sample-portfolio run so the Governance page doesn't show a gate that
    # belongs to a different portfolio.
    st.session_state.pop("control_result", None)
    st.session_state.pop("gate_report", None)
    st.session_state.pop("bundle_metadata", None)

if load_bundle_clicked and bundle_zip is not None:
    with st.spinner("Validating and loading the pre-computed results bundle…"):
        # Drop this session's own reference to whatever was loaded before
        # (a live run or an earlier bundle), and clear the engine's shared
        # result cache, BEFORE building the new one - a bundle load doesn't
        # need either, and on a memory-constrained host, leaving a previous
        # multi-hundred-MB result resident while loading a new one is
        # exactly what pushes total memory over the instance's limit.
        st.session_state.pop("result", None)
        st.session_state.pop("control_result", None)
        PR._cached_pipeline.clear()
        try:
            result, bundle_meta, gate_report = RB.load_bundle_from_bytes(
                bundle_zip.getvalue(), bundle_zip.name)
            st.session_state["result"] = result
            st.session_state["result_root"] = f"<bundle: {bundle_zip.name}>"
            st.session_state["demo_label"] = f"{bundle_meta.portfolio_label} (pre-computed)"
            st.session_state["bundle_metadata"] = bundle_meta
            if gate_report is not None:
                st.session_state["gate_report"] = gate_report
            else:
                st.session_state.pop("gate_report", None)
        except RB.BundleValidationError as e:
            st.error(f"**Could not load this bundle — refusing to load.**\n\n{e}")
            st.stop()

if "result" not in st.session_state:
    st.info("👈 Upload a zipped portfolio in the sidebar and click **Run analysis** "
           "to get started. Try `generator/out/demo` from this project, zipped.")
    st.markdown("""
### What happens when you run it

1. **Data contract** — every table and column is validated; anything shaped
   like a latent trait or a planted defect answer key is refused, not warned about.
2. **Economic ledger** — one row per account per month: interest, interchange,
   fees and deposit margin, less rewards (at *measured* cost), funding, expected
   credit loss, cost to serve, and cost of capital.
3. **Customer view** — rolled up across every product a customer holds, scored
   and banded.
4. **Suppression** — hardship, accommodation-plan, and SCRA customers are
   removed *before* anything else runs.
5. **Routing** — every below-cost customer is attributed to whichever cost
   dominates their account, then sent to the one lever that addresses it.
6. **Six levers** — each priced where the data honestly supports it, and left
   `None` — never a fabricated number — where it doesn't.
7. **Governance** — a four-fifths fairness test on both the score and the
   treatment, plus (when a run is paired with its own negative control -
   see `engine/export_bundle.py --compare-to`) the circularity gate against
   it.
    """)
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
# result["ledger"]["card"] is built BEFORE suppression and still includes
# hardship/accommodation/SCRA customers; cv does not. Restricting led to
# cv's own customers keeps the cost waterfall's "Net Economic Profit" total
# reconciled to the headline NEP metric below, exactly as
# charts.py:revenue_cost_waterfall's own docstring requires.
led = result["ledger"]["card"]
led = led.loc[led["Masked Customer Number"].isin(cv["Masked Customer Number"]), C.WATERFALL_COLUMNS]

st.success(f"Loaded **{st.session_state['demo_label']}** — "
          f"{cv['Masked Customer Number'].nunique():,} customers, "
          f"{led['Cycle Month'].nunique()} monthly cycles.")

st.header("Executive summary")

n_years = max(led["Cycle Month"].nunique() / 12.0, 1e-9)
total_customers = len(cv)
suppressed_n = len(result["suppressed"].suppressed)
below_cost = int(cv["is_below_cost"].sum())
below_cost_share = below_cost / max(total_customers, 1)
total_nep = cv["trailing_12m_net_economic_profit"].sum()
total_loss = -cv.loc[cv["is_below_cost"], "trailing_12m_net_economic_profit"].sum()
total_managed_limit = cv["current_limit"].sum()
total_card_balance = cv["latest_purchase_balance"].sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Customers scored", f"{total_customers:,}",
         help="How large the portfolio is, by relationship count.")
c2.metric("Suppressed (protected)", f"{suppressed_n:,}",
         help="Hardship, accommodation plan, or SCRA — removed before any lever runs.")
c3.metric("Trailing-12mo portfolio NEP", f"${total_nep:,.0f}",
         help="Net Economic Profit: everything the portfolio earned (interest, "
             "interchange, fees, deposit and loan margin) minus everything it cost "
             "(rewards, funding, credit losses, servicing, capital) over the last "
             "12 months. The single bottom-line number every other chart explains.")
c4.metric("Below-cost customers", f"{below_cost:,}", f"{below_cost_share:.1%} of book",
         help="Customers whose trailing-12mo NEP is negative — they currently cost "
             "the bank more than they earn.")
c5.metric("Total loss to route", f"${total_loss:,.0f}",
         help="The combined annual loss from every below-cost customer, before any "
             "lever is applied — the size of the problem the six levers exist to fix.")
st.markdown(
    f"{P.tag('measured')} Managed card credit lines: **\\${total_managed_limit:,.0f}** "
    f"carrying **\\${total_card_balance:,.0f}** in balances as of the latest cycle — "
    f"the portfolio's scale in dollars, not just headcount.",
    unsafe_allow_html=True)

left, right = st.columns([3, 2])
with left:
    st.plotly_chart(C.revenue_cost_waterfall(led), width="stretch")
    st.caption("This waterfall covers **card economics only**. The headline "
              "Trailing-12mo portfolio NEP above also adds each customer's "
              "deposit and loan relationship value, so the two totals differ "
              "on purpose — see **Portfolio Economics** for the full breakdown.")
with right:
    st.plotly_chart(C.cev_band_distribution(cv), width="stretch")

st.plotly_chart(C.relationship_view_chart(cv), width="stretch")
covers_n = int(cv["relationship_covers_card_loss"].sum())
if covers_n:
    st.caption(f"**{covers_n} customers** lose money on their card alone but are "
              f"profitable once deposits and loans are counted — none of them "
              f"should ever be recommended for exit.")

st.plotly_chart(C.routing_bar(result["routing_summary"]), width="stretch")

structural = result["routing_summary"]
if "STRUCTURAL" in structural.index:
    s_n = int(structural.loc["STRUCTURAL", "customers"])
    st.caption(f"**{s_n} customers ({s_n/max(below_cost,1):.1%} of loss-makers)** "
              f"have no single dominant fixable cost — a structural floor no "
              f"lever removes. Reporting this honestly is itself a finding: any "
              f"plan promising to recover the *entire* loss pool is wrong.")

st.divider()
st.subheader("📍 Where to look next")
routing_tbl = result["routing_summary"]
actionable = routing_tbl[routing_tbl.index.notna() & (routing_tbl.index != "STRUCTURAL")]
findings = []
if len(actionable):
    top_lever = actionable.index[0]
    top_loss = actionable.loc[top_lever, "total_loss"]
    top_n = int(actionable.loc[top_lever, "customers"])
    findings.append(f"**{top_lever}** carries this run's single largest below-cost loss "
                    f"pool — **${top_loss:,.0f}/yr** across **{top_n:,} customers**. "
                    f"Open **Strategy Overview** and that lever's own page for the business "
                    f"case and a customer-level drill-down.")
if "STRUCTURAL" in routing_tbl.index:
    s_n = int(routing_tbl.loc["STRUCTURAL", "customers"])
    findings.append(f"**{s_n} customers ({s_n/max(below_cost,1):.1%} of loss-makers)** "
                    f"have no single dominant fixable cost — a structural floor no "
                    f"lever removes. Any plan promising to recover the entire loss "
                    f"pool is wrong.")
if covers_n:
    findings.append(f"**{covers_n} customers** look unprofitable on their card alone "
                    f"but are profitable across the full relationship — never route "
                    f"these for exit.")
if suppressed_n:
    findings.append(f"**{suppressed_n} customers** were removed before any lever ran "
                    f"(hardship/accommodation/SCRA) — protected, not ignored.")
for f in findings:
    st.markdown(f"- {f}")

st.caption("Other pages: **Portfolio Economics** for the full cost breakdown; "
          "**Strategy Overview** for all six levers at a glance, with one page per "
          "lever (L2 also covers the regulatory carrying cost of unused credit lines "
          "and the ML credit-limit second opinion; L6 covers acquisition cost and "
          "payback); **Governance & Fairness** for the fairness and negative-control "
          "results.")
