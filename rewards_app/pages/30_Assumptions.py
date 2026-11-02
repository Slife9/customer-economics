import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402
from engine.rewards.assumptions import LEVERS, LEVER_LABELS, SCENARIOS, SEGMENTS  # noqa: E402

st.title("🎚️ Levers & assumptions")
c = S.cfg()
st.caption(f"Defaults are the Reward Profitability Scenario Model v2's values (illustrative industry averages, "
           f"workbook sha256 {c['_source']['workbook_sha256'][:12]}…). Edits apply to this session only; "
           f"download them below to keep them.")
S.edited_badge()

c1, c2 = st.columns([1, 4])
if c1.button("Reset to workbook defaults"):
    S.reset_cfg()
    for k in [k for k in st.session_state if str(k).startswith("ed_")]:
        del st.session_state[k]
    st.rerun()
c2.download_button("Download these assumptions (JSON)", json.dumps(S.cfg(), indent=2),
                   "reward_model_assumptions_edited.json", "application/json")

labels = {s: S.seg_label(s) for s in SEGMENTS}


def seg_table(block: dict, row_labels: dict, key: str) -> None:
    """Edit a {row: {segment: value}} block in place."""
    df = pd.DataFrame({labels[s]: [block[r][s] for r in row_labels] for s in SEGMENTS},
                      index=list(row_labels.values()))
    ed = st.data_editor(df, key=key, width="stretch")
    for r, rl in row_labels.items():
        for s in SEGMENTS:
            block[r][s] = float(ed.loc[rl, labels[s]])


st.subheader("Lever intensity by segment")
scn = st.radio("Scenario to edit", SCENARIOS, index=SCENARIOS.index(S.scenario()),
               format_func=str.capitalize, horizontal=True)
seg_table(c["levers"][scn], {k: LEVER_LABELS[k] for k in LEVERS}, f"ed_levers_{scn}")
st.caption("Units: earn-rate cut in fraction of spend (0.0025 = 0.25 pp); fee in dollars; all others are "
           "shares (0.2 = 20%). 0 = lever not used. Unassigned accounts never get a lever.")

st.subheader("Customer response (the most uncertain inputs)")
seg_table(c["behaviour"], {
    "attrition_per_10pct_value_cut": "Attrition per 10% cut in perceived reward value",
    "attrition_per_100usd_fee_increase": "Attrition per $100 of annual fee increase",
    "spend_change_per_10pct_value_cut": "Spend change per 10% value cut (retained accounts)"}, "ed_behaviour")
st.caption("Calibrate with a champion / challenger test: apply each change to a random 10-20% of a segment, "
           "measure closures and spend against control for 6 months, then replace these.")

st.subheader("Portfolio-wide")
pf = c["portfolio"]
pdf = pd.DataFrame({"Value": pd.Series(pf, dtype=float)})
ped = st.data_editor(pdf, key="ed_portfolio", width="stretch")
for k in pf:
    pf[k] = float(ped.loc[k, "Value"])

st.subheader("Segment thresholds")
th = c["thresholds"]
tdf = pd.DataFrame({"Value": pd.Series(th, dtype=float)})
ted = st.data_editor(tdf, key="ed_thresholds", width="stretch")
for k in th:
    th[k] = float(ted.loc[k, "Value"])
st.caption("Changing a threshold re-segments every account on every page.")
