import copy
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS, WORKBOOK_SEGMENTS, AssumptionsError  # noqa: E402

S.header("🎚️ Levers & assumptions")
st.warning("**Exploration only.** Changes apply to this browser session and are never saved to the configuration.")
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
S.cap("B8: the ML credit-limit model is not used in this module. B4: capital ratio and cost of equity below.")
new["screen"]["include_expected_drawdown_loss"] = st.toggle(
    "Screen including expected drawdown loss (sensitivity; default off)", value=cfg["screen"]["include_expected_drawdown_loss"])

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
