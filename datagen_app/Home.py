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

SCENARIO_DETAILS = {
    "demo": {
        "what": "A realistic, mixed portfolio spanning every segment and credit tier, with no "
                "deliberate skew in any direction - the same shape as the bundled sample data.",
        "how": ["This **is** the baseline. It isn't derived from anything else - every other "
               "scenario below starts here and shifts specific underlying customer tendencies "
               "away from it, never a result like profit or default rate directly."],
    },
    "transactor_heavy": {
        "what": "Skews toward customers who spend heavily but pay their statement balance in "
                "full most months - valuable, low-credit-risk relationships that make money on "
                "interchange rather than interest.",
        "how": [
            "Raises the underlying tendency to pay reliably and on time, before any account "
            "activity is simulated - not a rule that forces on-time payment, a shift in the "
            "hidden trait that drives it",
            "Lowers the underlying appetite for carrying a revolving balance, so credit is used "
            "as a payment tool rather than a lending product",
            "Starts fewer accounts on a promotional low-rate offer than the baseline",
            "Credit limits, fee-waiver policy, and collections practice are all left at baseline - "
            "only the customer's underlying financial character is shifted",
        ],
    },
    "subprime_heavy": {
        "what": "Skews toward lower credit scores and higher underlying risk - useful for "
                "stress-testing the credit and pricing levers against a book that has real, "
                "elevated risk for them to find.",
        "how": [
            "Shifts the underlying credit score distribution downward before origination",
            "Lowers the underlying tendency toward reliable, on-time payment",
            "Grants less generous initial credit limits relative to income - tighter starting "
            "lines, consistent with a higher-risk book",
            "Starts more accounts on a promotional offer than baseline, matching how subprime "
            "acquisition often leans on promotional pricing to win volume",
        ],
    },
    "premium_heavy": {
        "what": "Skews toward higher-income, higher-credit-score, more affluent customers with "
                "larger limits - useful for testing how the levers behave on a book that looks "
                "financially healthy on the surface.",
        "how": [
            "Shifts the underlying credit score distribution upward before origination",
            "Raises the underlying affluence trait that drives income, spend level, and product "
            "appetite",
            "Grants more generous initial credit limits relative to income",
            "Shifts acquisition toward the channels premium customers are actually acquired "
            "through, instead of the balanced baseline mix",
        ],
    },
    "negative_control": {
        "what": "Not a realistic customer mix - a deliberately **well-run** portfolio built to "
                "prove the analysis system's findings are real, not an artifact of the generator "
                "that would show up no matter what data it was fed.",
        "how": [
            "Credit lines are reviewed using actual observed behavior, not left generous by default",
            "Fees are aligned to the value delivered, instead of charged flat regardless of usage",
            "Digital self-service deflects far more contact-center volume",
            "More fee waivers are granted, with tighter review discipline",
            "Repricing tracks drifting risk instead of a rate set once at origination and never "
            "revisited",
            "Zero data-quality issues are planted - nothing to find, by design",
        ],
    },
}
detail = SCENARIO_DETAILS[profile_name]
st.caption(detail["what"])
with st.expander("How this is built from the balanced baseline"):
    for line in detail["how"]:
        st.markdown(f"- {line}")
    if profile_name == "negative_control":
        st.caption("If the analysis app still reports meaningful fixable opportunity on this "
                  "portfolio, that's a red flag that a finding is coming from the generator, "
                  "not from anything real in the data.")

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
