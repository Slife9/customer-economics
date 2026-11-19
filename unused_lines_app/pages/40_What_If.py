import copy
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS, WORKBOOK_SEGMENTS, AssumptionsError  # noqa: E402

S.header("🎚️ What-if: levers & assumptions")
S.analyst_only()
st.warning("**Exploration only.** Changes apply to this browser session and are never saved to the configuration. "
           "Every page shows a warning while settings differ from the agreed defaults.")
cfg = S.cfg()
new = copy.deepcopy(cfg)
if st.button("Reset to the agreed defaults", disabled=not S.cfg_edited()):
    S.reset_cfg()
    st.rerun()

# ---------------------------------------------------- open decisions
Y.band("Open decisions (config flags; defaults as agreed)")
c1, c2, c3 = st.columns(3)
new["capital"]["risk_weight_dormant_zero_balance"] = c1.select_slider(
    "B5 - dormant zero-balance risk weight", options=[0.45, 0.75], value=cfg["capital"]["risk_weight_dormant_zero_balance"],
    format_func=lambda v: f"{v:.0%}")
new["levers"]["dormant_rightsizing_enabled"] = c2.toggle("B6 - dormant right-sizing in the headline",
                                                         value=cfg["levers"]["dormant_rightsizing_enabled"])
new["levers"]["dormant_closure_enabled"] = c2.toggle("B6 - dormant closure and non-reissue in the headline",
                                                     value=cfg["levers"]["dormant_closure_enabled"])
new["levers"]["scope_mode"] = c3.radio("B7 - scope", cfg["levers"]["scope_mode_options"],
                                       index=cfg["levers"]["scope_mode_options"].index(cfg["levers"]["scope_mode"]),
                                       format_func={"workbook_unprofitable_low_use": "Workbook scope (default)",
                                                    "full_line_management": "Full line management"}.get)
S.cap("B8 decided: the ML credit-limit model is not used in this module. B4: capital ratio and cost of equity below.")
new["screen"]["include_expected_drawdown_loss"] = st.toggle(
    "Screen including expected drawdown loss (sensitivity; default off)", value=cfg["screen"]["include_expected_drawdown_loss"])

# ---------------------------------------------------- calculation settings (revision B)
Y.band("Calculation settings")
d1, d2, d3 = st.columns(3)
dr, co = cfg["drawdown_risk"], cfg["costs"]
new["drawdown_risk"]["leq_source"] = d1.radio(
    "LEQ source (B2)", dr["leq_source_options"], index=dr["leq_source_options"].index(dr["leq_source"]),
    format_func={"measured_account": "Account Behavioral CCF", "workbook_segment": "Workbook segment LEQ (default)"}.get)
new["costs"]["fixed_cost_basis"] = d2.radio(
    "Fixed cost per account (B5)", co["fixed_cost_basis_options"],
    index=co["fixed_cost_basis_options"].index(co["fixed_cost_basis"]),
    format_func={"engine_allocated": "Engine allocation (default)", "workbook_segment": "Workbook, by segment"}.get)
new["treatment"]["fairness"]["min_selected_per_group"] = d3.number_input(
    "Fairness: minimum selected accounts per metro", 1, 500, cfg["treatment"]["fairness"]["min_selected_per_group"])

Y.band("Balance basis and pay-in-full policy (revision E; defaults as agreed)")
bb = cfg["balance_basis"]
e1, e2, e3, e4 = st.columns(4)
new["balance_basis"]["screen"] = e1.radio(
    "30% use test", bb["screen_options"], index=bb["screen_options"].index(bb["screen"]),
    format_func={"statement_date": "Statement date (default)", "after_payment": "After payment (before E)"}.get)
new["balance_basis"]["cost"] = e2.radio(
    "Balance for costs", bb["cost_options"], index=bb["cost_options"].index(bb["cost"]),
    format_func={"midpoint": "Midpoint (default)", "after_payment": "After payment (before E)"}.get)
new["balance_basis"]["lever_values"] = e3.radio(
    "Lever values on", bb["lever_values_options"], index=bb["lever_values_options"].index(bb["lever_values"]),
    format_func={"current": "Today's unused line (default)", "average_12m": "12-month average (before E)"}.get)
sm = cfg["levers"]["system_mode"]
new["levers"]["system_mode"]["transactor_rightsizing_in_approved_value"] = e4.toggle(
    "Count pay-in-full cuts in the approved value (before E)", value=sm["transactor_rightsizing_in_approved_value"])

Y.band("The 90-day warning (Strategy 3) - assumptions, to be tested in the pilot")
wn = cfg["warning"]
w1, w2, w3, w4 = st.columns(4)
new["warning"]["enabled"] = w1.toggle("Warning step on (default)", value=wn["enabled"])
sh = wn["response_shares"]
new["warning"]["response_shares"]["resume_use"] = w2.number_input("Resume use", 0.0, 1.0, sh["resume_use"], 0.05)
new["warning"]["response_shares"]["accept_lower_limit"] = w3.number_input("Accept a lower limit", 0.0, 1.0,
                                                                         sh["accept_lower_limit"], 0.05)
new["warning"]["response_shares"]["close_voluntarily"] = w4.number_input("Close voluntarily", 0.0, 1.0,
                                                                        sh["close_voluntarily"], 0.05)
v1, v2, v3, v4 = st.columns(4)
new["warning"]["min_use_to_reset"] = v1.radio(
    "Use that resets the clock", wn["min_use_to_reset_options"],
    index=wn["min_use_to_reset_options"].index(wn["min_use_to_reset"]),
    format_func={"one_transaction": "One transaction", "min_spend": "Minimum spend (default)"}.get)
new["warning"]["min_spend_to_reset_usd"] = v2.number_input("Minimum spend (USD)", 0, 5000, wn["min_spend_to_reset_usd"], 25)
new["warning"]["letter_cost_usd"] = v3.number_input("Letter cost per customer (USD)", 0.0, 20.0, wn["letter_cost_usd"], 0.5)
new["warning"]["notice_days"] = v4.number_input("Notice (days)", 30, 180, wn["notice_days"], 15)
S.cap("The warning never carries a fee (inactivity fees are prohibited). The minimum-spend rule decides who counts as "
      "resumed; the resume share is the assumption for that rule.")

Y.band("Bank profile")
bp = cfg["bank_profile"]
b1, b2 = st.columns(2)
new["bank_profile"]["apply_to"] = b1.radio(
    "Apply the conservative LCR assumption to", bp["apply_to_options"],
    index=bp["apply_to_options"].index(bp["apply_to"]),
    format_func={"category_I_III": "Category I-III banks (default)", "all_banks": "All banks"}.get)
new["bank_profile"]["bank_category"] = b2.radio(
    "This bank is", bp["bank_category_options"], index=bp["bank_category_options"].index(bp["bank_category"]),
    format_func={"category_I_III": "Category I-III (default)", "category_IV_or_other": "Category IV or other"}.get)

# ---------------------------------------------------- parameters
Y.band("Regulatory and business parameters")
p1, p2, p3, p4, p5 = st.columns(5)
new["capital"]["capital_ratio"] = p1.number_input("Capital ratio", 0.01, 0.30, cfg["capital"]["capital_ratio"], 0.005, format="%.3f")
new["capital"]["cost_of_equity"] = p2.number_input("Cost of equity", 0.01, 0.40, cfg["capital"]["cost_of_equity"], 0.01, format="%.2f")
new["capital"]["ccf_unused_card_lines"] = p3.number_input("CCF on unused lines (> 0)", 0.01, 1.0,
                                                          cfg["capital"]["ccf_unused_card_lines"], 0.05, format="%.2f")
new["liquidity"]["lcr_outflow_unused_card_lines"] = p4.number_input(
    "LCR outflow", 0.0, 1.0, cfg["liquidity"]["lcr_outflow_unused_card_lines"], 0.01, format="%.2f")
new["liquidity"]["negative_carry"] = p5.number_input("Negative carry", 0.0, 0.05, cfg["liquidity"]["negative_carry"],
                                                     0.0025, format="%.4f")
q1, q2, q3, q4 = st.columns(4)
new["levers"]["max_reduction_per_review"] = q1.number_input("Max cut per review", 0.05, 1.0,
                                                            cfg["levers"]["max_reduction_per_review"], 0.05)
new["levers"]["system_mode"]["reviews_in_year_one"] = q2.number_input(
    "Reviews in year 1", 1, 4, cfg["levers"]["system_mode"]["reviews_in_year_one"])
new["levers"]["system_mode"]["closure_min_inactive_months"] = q3.number_input(
    "Closure: months inactive", 12, 36, cfg["levers"]["system_mode"]["closure_min_inactive_months"])
new["treatment"]["pilot"]["holdout_share"] = q4.number_input("Pilot holdout share", 0.0, 0.5,
                                                             cfg["treatment"]["pilot"]["holdout_share"], 0.05)

# ---------------------------------------------------- workbook levers
Y.band("Lever settings by scenario and segment (from the reference workbook)")
scn = st.radio("Scenario to edit", SCENARIOS, index=1, format_func=str.capitalize, horizontal=True)
lv = pd.DataFrame(cfg["workbook"]["levers"][scn]).T[WORKBOOK_SEGMENTS]
lv.columns = [S.seg_label(c) for c in lv.columns]
ed = st.data_editor(lv, width="stretch", key=f"lv_{scn}")
ed.columns = WORKBOOK_SEGMENTS
new["workbook"]["levers"][scn] = {k: {s: float(ed.loc[k, s]) for s in WORKBOOK_SEGMENTS} for k in ed.index}

Y.band("Customer response by segment (from the reference workbook)")
keys = ["response_rate", "attrition_after_decrease", "spend_loss_after_decrease", "pd_increase_after_decrease", "leq"]
rs = pd.DataFrame({s: {k: cfg["workbook"]["segments"][s][k] for k in keys} for s in WORKBOOK_SEGMENTS})
rs.columns = [S.seg_label(c) for c in rs.columns]
ed2 = st.data_editor(rs, width="stretch", key="responses")
ed2.columns = WORKBOOK_SEGMENTS
for s in WORKBOOK_SEGMENTS:
    for k in keys:
        new["workbook"]["segments"][s][k] = float(ed2.loc[k, s])
    new["drawdown_risk"]["leq_by_segment"][s] = float(ed2.loc["leq", s])

if new != cfg:
    try:
        S.set_cfg(new)
        st.rerun()
    except AssumptionsError as e:
        st.error(f"Not applied: {e}")
S.caveat()
