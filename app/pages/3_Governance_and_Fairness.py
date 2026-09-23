from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Governance & Fairness", page_icon="🛡️", layout="wide")
st.title("🛡️ Governance & Fairness")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
fairness = result["fairness"]

st.subheader("Negative control gate")
if "gate_report" in st.session_state:
    gate_report = st.session_state["gate_report"]
    st.plotly_chart(C.gate_chart(gate_report), width="stretch")

    defect_row = gate_report[gate_report["lever"] == "DEFECTS"].iloc[0]
    badge = "✅" if defect_row["status"] == "PASS" else "❌"
    st.markdown(f"{badge} **Planted defects in the control:** {defect_row['detail']}")

    st.dataframe(gate_report, width="stretch")

    st.markdown("""
**How to read this:** each lever's mechanism-varied test compares how much a
lever's driver (the portfolio quantity it claims to act on) fell in the
negative control against how much the lever's priced value fell. A lever
**passes** if value fell at least as fast as its driver — evidence the
finding tracks its cause rather than firing regardless. A lever the control
doesn't vary the mechanism for is reported **inconclusive**, not a pass.
    """)
    for _, r in gate_report.iterrows():
        icon = {"PASS": "✅", "FAIL": "❌", "INCONCLUSIVE": "⚪"}[r["status"]]
        st.markdown(f"{icon} **{r['lever']}** — {r['detail']}")
else:
    st.info("Upload a negative control portfolio on the **Home** page to enable "
           "this gate — the strongest available evidence that findings here "
           "track their cause rather than the generator that produced the demo data.")

st.divider()
st.subheader("Fairness — four-fifths test")
st.caption(fairness["proxy_method"])

tab1, tab2 = st.tabs(["Score fairness (who gets a high value band)",
                     "Treatment fairness (who gets a lever action)"])
with tab1:
    if fairness["score_any_failure"]:
        st.error("⚠️ At least one geography group fails the four-fifths test on "
                 "the SCORE. Reported here regardless of outcome — a fairness "
                 "result that only appears when it passes is not a fairness result.")
    else:
        st.success("No geography group failed the four-fifths test on the score.")
    st.plotly_chart(C.fairness_chart(fairness["score_fairness"], "Score selection rate by geography"),
                    width="stretch")
    st.dataframe(fairness["score_fairness"], width="stretch")

with tab2:
    if fairness["treatment_any_failure"]:
        st.error("⚠️ At least one geography group fails the four-fifths test on "
                 "the TREATMENT — who actually receives a lever action. A score "
                 "can pass while the treatment built on it fails, and the "
                 "treatment is what a customer experiences.")
    else:
        st.success("No geography group failed the four-fifths test on the treatment.")
    st.plotly_chart(C.fairness_chart(fairness["treatment_fairness"], "Treatment selection rate by geography"),
                    width="stretch")
    st.dataframe(fairness["treatment_fairness"], width="stretch")

if fairness["score_fairness_by_product_tier"] is not None and len(fairness["score_fairness_by_product_tier"]):
    st.divider()
    st.subheader("Score fairness by product tier")
    st.caption("Product tier is not a protected class, but it correlates with "
              "score and is worth examining on its own.")
    st.plotly_chart(C.fairness_chart(fairness["score_fairness_by_product_tier"],
                                     "Score selection rate by product tier"),
                    width="stretch")

st.divider()
st.subheader("Suppression")
supp = result["suppressed"].suppressed
if len(supp):
    reason_counts = supp["suppression_reason"].value_counts()
    st.bar_chart(reason_counts)
    st.caption(f"{len(supp):,} customers suppressed before any lever ran — "
              f"never flagged, never scored, never actioned.")
else:
    st.caption("No customers were suppressed in this portfolio.")
