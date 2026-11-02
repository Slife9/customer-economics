import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402
from engine.rewards.assumptions import SCENARIOS  # noqa: E402

st.title("⬇️ Downloads")
S.require()
S.edited_badge()
scn = st.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
               horizontal=True)
t, post, sm = S.run(scn)

acct = t[t["screened"]][["customer", "segment", "program", "spend", "revenue", "reward", "signup_bonus",
                          "fully_loaded_profit", "noncard_profit"]].join(
    post[["perceived_value_cut", "attrition", "spend_change", "fully_loaded_profit",
          "relationship_adjusted_profit"]].rename(columns=lambda c: f"{scn}_{c}"))
acct.index.name = "Masked Account Number"

st.download_button(f"Account-level results - {scn} (CSV)", acct.to_csv(), f"l1_rewards_accounts_{scn}.csv",
                   "text/csv")
st.caption("One row per screened account: segment, measured trailing-12m P&L, and the scenario's expected "
           "leave probability, spend change and post-change profit.")
st.download_button(f"Segment summary - {scn} (CSV)", sm.to_csv(), f"l1_rewards_segments_{scn}.csv", "text/csv")
st.download_button("Assumptions in use (JSON)", json.dumps(S.cfg(), indent=2), "reward_model_assumptions_in_use.json",
                   "application/json")
S.caveat()
