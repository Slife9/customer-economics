"""ProfitInsight synthetic portfolio generator - standalone app.

Lets a non-technical user create a new synthetic test portfolio (a zip of
the same table CSVs the Customer Economics System analyzes) without
touching config files or the command line, then hands them straight to
that analysis app.
"""
from __future__ import annotations
import io
import random
import sys
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from generator.run import build, PROFILES, DEMO_DEFECT_PREVALENCE  # noqa: E402

ANALYSIS_APP_URL = "https://customer-economics-exut3amfwi9uesfmpqvm4j.streamlit.app/"

SCENARIOS = {
    "Balanced portfolio (recommended starting point)": "demo",
    "Heavy transactors (customers who pay in full)": "transactor_heavy",
    "Higher credit risk (subprime-heavy)": "subprime_heavy",
    "Premium / affluent customers": "premium_heavy",
    "Validation baseline (negative control - for testing the system itself)": "negative_control",
}

st.set_page_config(page_title="ProfitInsight Portfolio Generator", page_icon="🧪", layout="wide")

if "gen_seed" not in st.session_state:
    st.session_state["gen_seed"] = random.randint(1, 999_999_999)

st.title("🧪 ProfitInsight Synthetic Portfolio Generator")
st.caption("Create a brand-new test portfolio, then analyze it in the Customer Economics System - "
           "no config files, no command line.")

st.info(f"After you generate and download a portfolio here, open the "
        f"[analysis app]({ANALYSIS_APP_URL}) and upload the zip on its home page.")

st.header("1 · Choose a scenario")
scenario_label = st.selectbox("What kind of portfolio do you want to test against?",
                              list(SCENARIOS.keys()))
profile_name = SCENARIOS[scenario_label]

SCENARIO_BLURBS = {
    "demo": "A realistic, mixed portfolio across all segments - the same shape as the bundled sample data.",
    "transactor_heavy": "Skews toward customers who spend heavily but pay their balance in full every month.",
    "subprime_heavy": "Skews toward lower credit scores and higher risk - useful for stress-testing the credit and pricing levers.",
    "premium_heavy": "Skews toward higher income, higher credit limits, and more affluent customers.",
    "negative_control": "Every lever's mechanism is deliberately turned OFF or held flat - the system should find little to no fixable opportunity here. Used to prove a finding is real, not a generator artifact.",
}
st.caption(SCENARIO_BLURBS[profile_name])

st.header("2 · Set the size and shape")
col1, col2 = st.columns(2)
with col1:
    n_customers = st.slider("Number of customers", min_value=500, max_value=10_000,
                            value=3_000, step=500)
with col2:
    n_months = st.slider("Time horizon (months)", min_value=12, max_value=36,
                         value=36, step=6,
                         help="At least 12 months are needed for the analysis app's "
                              "trailing-12-month figures to be meaningful.")

st.header("3 · Set the data-quality issue rate")
defect_multiplier = st.slider(
    "Planted data-quality issues, relative to a normal baseline",
    min_value=0.0, max_value=2.0, value=1.0, step=0.25,
    format="%.2fx",
    help="0x = a clean portfolio with no planted issues. 1x = a normal baseline rate "
         "(unposted fees, expired promos, mispriced interchange, and similar). "
         "2x = double the baseline rate, for stress-testing the detection logic.")
if profile_name == "negative_control":
    st.caption("Disabled for this scenario - the negative control always carries zero planted issues by design.")

with st.expander("Advanced: random seed"):
    st.write(f"Current seed: **{st.session_state['gen_seed']}** "
            f"(the same seed always reproduces the exact same portfolio)")
    if st.button("🎲 Use a new random seed"):
        st.session_state["gen_seed"] = random.randint(1, 999_999_999)
        st.rerun()

st.divider()

if st.button("Generate portfolio", type="primary"):
    overrides = {}
    if profile_name != "negative_control" and defect_multiplier != 1.0:
        overrides["defect_prevalence"] = {
            k: min(v * defect_multiplier, 0.90) for k, v in DEMO_DEFECT_PREVALENCE.items()
        }

    with st.spinner("Generating your portfolio - this can take a minute or two for larger sizes..."):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "portfolio"
            meta = build(profile_name, out_dir, st.session_state["gen_seed"],
                        n_months, n_customers, overrides or None)

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(out_dir.iterdir()):
                    if f.is_file():
                        zf.write(f, arcname=f.name)
            buf.seek(0)
            st.session_state["last_zip"] = buf.getvalue()
            st.session_state["last_meta"] = meta

if "last_meta" in st.session_state:
    meta = st.session_state["last_meta"]
    st.success(f"Generated {meta['customers']:,} customers over {meta['cycles']} months "
              f"({meta['from']} to {meta['to']}).")

    m1, m2, m3 = st.columns(3)
    m1.metric("Transactions", f"{meta['transactions']:,}")
    m2.metric("Account-months", f"{meta['account_cycles']:,}")
    m3.metric("Planted data-quality issues", f"{meta['planted_defects']:,}")

    st.download_button(
        "⬇️ Download portfolio (zip)",
        data=st.session_state["last_zip"],
        file_name=f"portfolio_{profile_name}_{st.session_state['gen_seed']}.zip",
        mime="application/zip",
        type="primary",
    )
    st.caption(f"Then open the [analysis app]({ANALYSIS_APP_URL}) and upload this zip on its home page "
              f"to see the full customer economics, lever recommendations, and governance checks.")

    with st.expander("What's inside this portfolio?"):
        st.write(
            "A complete set of the same table CSVs a bank's own systems would hold: "
            "customers, card accounts, monthly account cycles, transactions, risk "
            "parameters, capital, cost drivers, rewards, fees, and more. Every figure "
            "is generated from underlying customer behavior - never planted to match "
            "a result the analysis app is expected to find.")
