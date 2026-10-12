"""ML Credit Limit Recommendation - CES's first real machine-learning
diagnostic. See engine/ml/MODEL_CARD.md for the full model card: training
data, target definitions, anti-leakage measures, and what this explicitly
does not claim.

Forecasts (risk of 30+ DPD, 3-month spend, 3-month peak balance) come from
a model trained OFFLINE on this repo's own generator output and committed
to the repo (engine/ml/artifacts/) - never retrained here. A hand-written
rules engine (engine/ml/decisions.py) turns those forecasts into an action
and a recommended limit; the model never sets a dollar figure itself.

Kept separate from L2 (which already does credit-line INCREASE/DECREASE via
pure rules, no ML) and from NEP/CEV, same discipline as every other
diagnostic in this app. Suppressed customers (hardship/accommodation/SCRA)
are already excluded from result["customer_view"] by the time this page
reads it - engine/run.py merges the ml_* columns in BEFORE suppression
runs, so this page needs no suppression logic of its own, exactly like the
Liquidity and Leverage pages.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="ML Credit Limit", page_icon="🤖", layout="wide")
st.title("🤖 ML Credit Limit Recommendation")
st.caption("A genuinely separate recommendation engine from L2 - forecasts from a trained "
          "model, turned into an action by a hand-written rules engine. The model never sets "
          "a limit; it only supplies evidence. Never blended into NEP, CEV, or L2 itself.")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]

if not result.get("ml_available"):
    st.info("No trained model bundle found. Train one with "
           "`python -m engine.ml.train_credit_limit_model`, then rerun the analysis - "
           "nothing else needs to change.")
    st.stop()

if "ml_action" not in cv.columns or cv["ml_action"].isna().all():
    st.info("This portfolio has no card accounts the model could score. This page will "
           "populate automatically once that data is present.")
    st.stop()

evidence_path = Path(__file__).resolve().parents[2] / "engine" / "ml" / "artifacts" / "model_evidence.json"
evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}

ml_policy = result.get("ml_policy", {})
ml_warnings = result.get("ml_policy_warnings", [])

banner_bits = []
if evidence:
    banner_bits.append(f"trained {evidence.get('trained_at_utc', '?')[:10]}")
    banner_bits.append(f"bundle `{evidence.get('bundle_sha256', '?')[:12]}…`")
    deployed = {k: v.get("deployed", "?") for k, v in evidence.get("targets", {}).items()}
    banner_bits.append("deployed: " + ", ".join(f"{k}={v}" for k, v in deployed.items()))
st.info("**Trained on simulated data — not evidence of real-world accuracy.** "
       + (" · ".join(banner_bits) if banner_bits else ""))

if ml_warnings:
    with st.expander(f"⚠️ {len(ml_warnings)} policy warning(s)", expanded=False):
        for w in ml_warnings:
            st.caption(f"- {w}")

has_ml = cv["ml_action"].notna()
actionable = cv["ml_action"].isin(["INCREASE", "DECREASE_UNUSED_EXPOSURE", "FREEZE_NO_INCREASE"])

st.subheader("Portfolio summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Customers scored", f"{int(has_ml.sum()):,}")
m2.metric("Actionable recommendations", f"{int(actionable.sum()):,}",
         help="INCREASE, DECREASE_UNUSED_EXPOSURE, or FREEZE_NO_INCREASE — the three actions "
             "that actually change what a customer experiences.")
m3.metric("Sent to manual review", f"{int((cv['ml_action'] == 'MANUAL_REVIEW').sum()):,}")
m4.metric("Risk-adjusted value proxy (3mo)", f"${cv.loc[has_ml, 'ml_risk_adjusted_value_proxy'].sum():,.0f}",
         help="Interchange + released capacity − expected loss. See the caption below the money "
             "figures table — this total is NOT a profit forecast.")

st.divider()
st.plotly_chart(C.ml_action_distribution_chart(cv), width="stretch")

n_deferred = int(cv.loc[has_ml, "ml_pilot_cap_deferred"].sum()) if "ml_pilot_cap_deferred" in cv.columns else 0
if n_deferred:
    st.caption(f"**{n_deferred} customers** qualified for a reduction but were held back by the "
              f"portfolio pilot cap (safest {ml_policy.get('maximum_reduction_share_per_review', 0.05):.0%} "
              f"of the book per review cycle, prioritized by lowest need) — "
              f"reason code `REDUCTION_CANDIDATE_OUTSIDE_PILOT_CAP`.")

st.divider()
st.subheader("L2 vs. ML — do the two recommendation engines agree?")
st.caption("L2 (Levers & Strategy) decides credit-line changes from pure rules on observed "
          "trailing-12m behavior. This page decides from a trained model's forecasts. They are "
          "two independent engines over the same lever surface — agreement is a sanity check, "
          "not a requirement.")
l2_worklist = result["worklists"].get("L2")
if l2_worklist is not None and len(l2_worklist):
    l2_actions = l2_worklist[["Masked Customer Number", "action"]].rename(
        columns={"action": "L2 action"})
    compare = cv.loc[has_ml, ["Masked Customer Number", "ml_action"]].merge(
        l2_actions, on="Masked Customer Number", how="left")
    compare["L2 action"] = compare["L2 action"].fillna("No L2 action")
    cross = pd.crosstab(compare["ml_action"], compare["L2 action"])
    st.dataframe(cross, width="stretch")
else:
    st.caption("No L2 worklist available this run.")

st.divider()
st.subheader("Fairness (ML treatment)")
ml_fairness = result.get("ml_fairness")
if ml_fairness:
    st.caption(ml_fairness["proxy_method"])
    tf = ml_fairness["treatment_fairness"]
    if len(tf):
        st.dataframe(
            tf.rename(columns={"group": "Metro", "n": "N", "selection_rate": "Selection rate",
                               "ratio_to_population": "Ratio to population", "passes": "Passes 4/5ths"})
            .style.format({"Selection rate": "{:.1%}", "Ratio to population": "{:.2f}"}),
            width="stretch", height=240)
        if ml_fairness["treatment_any_failure"]:
            st.warning("At least one geography group fails the four-fifths threshold on who "
                      "receives an actionable ML recommendation. See the Governance page's "
                      "own fairness section for the methodology and its stated BISG limitation.")
    else:
        st.caption("No group had enough customers (≥30) to test.")
else:
    st.caption("Fairness check unavailable this run.")

st.divider()
st.subheader("Money figures (diagnostic — see the caveat before reading the total)")
mm1, mm2, mm3 = st.columns(3)
mm1.metric("Expected 3mo interchange", f"${cv.loc[has_ml, 'ml_expected_3m_interchange_proxy'].sum():,.0f}")
mm2.metric("Expected loss (unconditional)", f"${cv.loc[has_ml, 'ml_expected_loss_proxy'].sum():,.0f}")
mm3.metric("Released capacity value (3mo)", f"${cv.loc[has_ml, 'ml_released_capacity_value_proxy_3m'].sum():,.0f}")
st.caption("**Why the total is misleading, stated plainly (ported from the sibling system's own "
          "documentation):** revenue here is interchange-only on a 3-month horizon; expected "
          "loss is a full unconditional PD×EAD×LGD figure computed for every scored account, "
          "most of which exists whether or not any recommendation changes — not the *marginal* "
          "loss caused by this page's decisions. Comparing this total between two policy "
          "configurations is valid; reading the absolute number as a profit forecast is not.")

st.divider()
st.subheader("Customer-level detail")
f1, f2 = st.columns(2)
action_opts = f1.multiselect("Action", C.ML_ACTION_ORDER)
risk_opts = f2.multiselect("Risk category", ["Low", "Moderate", "High", "Unavailable"])

filtered = cv[has_ml].copy()
if action_opts:
    filtered = filtered[filtered["ml_action"].isin(action_opts)]
if risk_opts:
    filtered = filtered[filtered["ml_risk_category"].isin(risk_opts)]

st.caption(f"Showing {len(filtered):,} of {int(has_ml.sum()):,} scored customers")
show_cols = ["Masked Customer Number", "current_limit", "ml_action", "ml_primary_reason",
            "ml_recommended_limit", "predicted_risk_probability", "ml_risk_category",
            "ml_pressure_score", "ml_confidence"]
show_cols = [c for c in show_cols if c in filtered.columns]
st.dataframe(filtered[show_cols].sort_values("ml_pressure_score", ascending=False),
            width="stretch", height=420)

with st.expander("Model card and training evidence"):
    model_card_path = Path(__file__).resolve().parents[2] / "engine" / "ml" / "MODEL_CARD.md"
    if model_card_path.exists():
        st.markdown(model_card_path.read_text(encoding="utf-8"))
