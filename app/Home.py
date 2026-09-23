"""ProfitInsight Customer Economics System — landing page.

Run with:
    streamlit run app/Home.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.lib import pipeline_runner as PR, charts as C
from engine.core.contract import DataContractViolation

st.set_page_config(page_title="ProfitInsight — Customer Economics System",
                  page_icon="💳", layout="wide")

st.title("💳 ProfitInsight Customer Economics System")
st.caption("What is each customer worth, after every cost — and which of six "
          "levers actually fixes it.")

DATAGEN_APP_URL = "https://customer-economics-g36dfysbdmfgwf2f8ygmms.streamlit.app/"

with st.sidebar:
    st.caption(f"Need a portfolio to test with? [Generate one here]({DATAGEN_APP_URL}) — "
              f"pick a scenario, size, and data-quality issue rate, then come back "
              f"and upload it below.")
    st.divider()

    if st.button("🔄 Clear cache & reload", width="stretch",
                help="The analysis result is cached by portfolio path. If "
                    "you've just pulled or edited code under engine/, click "
                    "this before re-running - otherwise you may see a stale "
                    "result computed by the old code."):
        st.cache_resource.clear()
        for k in ("result", "result_root", "demo_label", "control_result",
                 "control_label", "gate_report"):
            st.session_state.pop(k, None)
        st.rerun()

    st.header("1 · Load a portfolio")
    demo_zip = st.file_uploader(
        "Portfolio to analyze (zip of the table CSVs)", type="zip", key="demo_zip")
    st.caption("e.g. `generator/out/demo` zipped up")

    st.header("2 · Optional: negative control")
    control_zip = st.file_uploader(
        "Negative control portfolio (zip)", type="zip", key="control_zip")
    st.caption("Enables the negative-control gate on the Governance page — "
              "proof the findings track their cause, not the generator.")

    run_clicked = st.button("Run analysis", type="primary", width="stretch",
                            disabled=demo_zip is None)

    st.divider()
    sample_dir = Path(__file__).resolve().parents[1] / "samples"
    sample_available = (sample_dir / "demo_portfolio.zip").exists()
    sample_clicked = st.button(
        "Try it with the bundled sample portfolio", width="stretch",
        disabled=not sample_available,
        help="Loads samples/demo_portfolio.zip and samples/negative_control_portfolio.zip "
            "from this project - no file picker needed.")

if sample_clicked:
    with st.spinner("Loading the bundled sample portfolio…"):
        result, root = PR.run_pipeline_for_sample(
            sample_dir / "demo_portfolio.zip", "demo")
        st.session_state["result"] = result
        st.session_state["result_root"] = str(root)
        st.session_state["demo_label"] = "samples/demo_portfolio.zip"
    ctrl_path = sample_dir / "negative_control_portfolio.zip"
    if ctrl_path.exists():
        with st.spinner("Loading the bundled negative control…"):
            control_result, control_root = PR.run_pipeline_for_sample(ctrl_path, "control")
            st.session_state["control_result"] = control_result
            st.session_state["control_label"] = "samples/negative_control_portfolio.zip"
            st.session_state["gate_report"] = PR.run_negative_control_gate(
                result, control_result)

if run_clicked and demo_zip is not None:
    with st.spinner("Validating data contract, building the ledger, routing levers…"):
        try:
            result, root = PR.run_pipeline_for_upload(demo_zip, "demo")
            st.session_state["result"] = result
            st.session_state["result_root"] = str(root)
            st.session_state["demo_label"] = demo_zip.name
        except DataContractViolation as e:
            st.error(f"**Data contract violation — refusing to run.**\n\n{e}")
            st.stop()

    if control_zip is not None:
        with st.spinner("Building the negative control for comparison…"):
            try:
                control_result, control_root = PR.run_pipeline_for_upload(control_zip, "control")
                st.session_state["control_result"] = control_result
                st.session_state["control_label"] = control_zip.name
                st.session_state["gate_report"] = PR.run_negative_control_gate(
                    result, control_result)
            except DataContractViolation as e:
                st.warning(f"Negative control failed the data contract, so the "
                          f"gate is unavailable this run: {e}")
    else:
        st.session_state.pop("control_result", None)
        st.session_state.pop("gate_report", None)

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
   treatment, and (if you load a negative control) the circularity gate.
    """)
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
led = result["ledger"]["card"]

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

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Customers scored", f"{total_customers:,}")
c2.metric("Suppressed (protected)", f"{suppressed_n:,}",
         help="Hardship, accommodation plan, or SCRA — removed before any lever runs.")
c3.metric("Trailing-12mo portfolio NEP", f"${total_nep:,.0f}")
c4.metric("Below-cost customers", f"{below_cost:,}", f"{below_cost_share:.1%} of book")
c5.metric("Total loss to route", f"${total_loss:,.0f}")

left, right = st.columns([3, 2])
with left:
    st.plotly_chart(C.revenue_cost_waterfall(led), width="stretch")
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
st.markdown("**Next:** open **Portfolio Economics** for the full cost breakdown, "
           "**Levers & Strategy** for the business case per lever and a "
           "customer-level drill-down, or **Governance** for the fairness and "
           "negative-control results.")
