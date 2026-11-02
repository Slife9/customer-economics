import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402
from rewards_app.lib.guide import GUARDRAILS, LEVER_GUIDE, SEGMENT_ACTIONS  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

st.title("📖 Lever guide & regulation")
st.caption("Summarised from the Reward Profitability Scenario Model v2's Lever Guide and Segment Definitions. "
           "Terms are illustrative designs - adapt to your products, test against a holdout, and clear with "
           "Compliance before launch.")

st.subheader("The nine levers")
st.dataframe(pd.DataFrame(LEVER_GUIDE, columns=["Lever", "What it is", "Example (Base scenario)", "Compliance"]),
             hide_index=True, width="stretch")

st.subheader("What to do, by segment")
for seg in ORDER + ["unassigned"]:
    g = SEGMENT_ACTIONS[seg]
    with st.expander(S.seg_label(seg)):
        st.markdown(f"**Who:** {g['why']}")
        st.markdown("\n".join(f"- {a}" for a in g["actions"]))
        st.markdown(f"**Watch-out:** {g['watch']}")

st.subheader("How the model works")
st.markdown(
    "- **Perceived reward value cut** = 1 - (new earn / old earn) x (1 - excluded spend) x (1 - cap effect) "
    "x (1 - steering x pass-through). Merchant-funded offers don't reduce perceived value.\n"
    "- **Leave probability** = min(cap, multiplier x [cut / 10% x attrition sensitivity + fee increase / $100 "
    "x fee sensitivity]).\n"
    "- Retained accounts' **spend** changes by cut / 10% x spend sensitivity. Migrated accounts earn "
    "non-rewards interchange on reduced spend and have their own product-change attrition.\n"
    "- **Fixed cost is held constant**: closing an account removes only its variable cost.\n"
    "- Non-card relationship profit is lost when an account leaves.")

st.subheader("Regulatory guardrails (US)")
st.markdown("\n".join(f"- {g}" for g in GUARDRAILS))
