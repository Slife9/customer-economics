import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402

st.title("🧪 Data & calibration")
S.require()
t = S.frame()
meta = st.session_state["meta"]
root = Path(st.session_state["root"])
c = S.cfg()

st.subheader("Where every figure comes from")
st.dataframe(pd.DataFrame([
    ("Card P&L lines", "Engine card ledger (engine.core.ledger), trailing 12 cycles", "Measured"),
    ("Sign-up bonus", "Table26_Signup_Bonus - bonus earned in the trailing 12 cycles", "Measured from data; NOT in the engine's profit"),
    ("Spend, earn rate, bonus-category share, quasi-cash share", "Table5 purchases (cash advances excluded), Table16, Table25", "Measured"),
    ("Paid in full, revolving balance, APR, line", "Table4 account cycles", "Measured"),
    ("Non-card relationship profit, deposits", "Engine deposit and loan ledgers; Table6b", "Measured"),
    ("Credit inquiries (confirming indicator)", "Table27_Bureau_Inquiries", "Synthetic, generated"),
    ("Levers, customer response, portfolio rates", "Reward Profitability Scenario Model v2", "Assumption - illustrative"),
], columns=["What", "Source", "Basis"]), hide_index=True, width="stretch")

st.subheader("Reconciliation")
diff = (t["fully_loaded_profit"] + t["signup_bonus"] - t["engine_nep"]).abs().max()
st.markdown(f"Fully loaded card profit + sign-up bonus = the engine's net economic profit, for every account: "
            f"largest difference **${diff:,.2f}** across {len(t):,} accounts.")
if S.prebuilt(root):
    st.markdown(f"This sample is a **prebuilt account frame** (`{root.name}`): the per-account figures above, "
                f"built from a generator run of the `{meta.get('profile')}` profile with "
                f"{meta.get('customers', 0):,} customers (seed {meta.get('seed')}) in `{meta.get('data_dir')}`. "
                f"The raw tables of a 100,000-customer book run to several GB, so they are not shipped; rebuild "
                f"with `python -m rewards_app.build_sample`.")
else:
    present = {n: (root / n).exists() for n in ["Table25_MCC_Reference.csv", "Table26_Signup_Bonus.csv",
                                                 "Table27_Bureau_Inquiries.csv", "build_manifest.json"]}
    st.markdown("Tables present: " + ", ".join(f"{'✅' if v else '❌'} {k}" for k, v in present.items()))
    if st.session_state.get("added_tables"):
        st.caption("Computed at load: " + ", ".join(st.session_state["added_tables"]))

st.subheader("Model check against the workbook")
st.markdown("Fed the workbook's own five segments, this system's model reproduces the workbook's Calc sheets "
            "exactly (90 values, 3 scenarios x 5 segments, largest difference $0.00 - "
            "`audit/audit_l1_rewards_system.py`). Differences on this page come from the data, not the formulas.")

st.subheader("Known limitations")
st.markdown(
    "- **Assumptions are illustrative.** No customer response has been measured on this portfolio.\n"
    "- **The ledger has no separate network / processing line** (the workbook charges 0.1% of spend), so that "
    "line is $0 here.\n"
    "- **Segment-level levers.** Every account in a segment gets the same lever settings, as in the workbook; "
    "results are expected values.\n"
    "- **Single-year steady state**: no 45-day notice lag, ramp-up or multi-year customer value.\n"
    "- **Unassigned** is large on this data, mainly flat-rate cash-back transactors the workbook's rules do "
    "not cover.\n"
    "- The bundled *reward stress* book is a deliberately skewed synthetic portfolio built to populate every "
    "segment - not a realistic US book.")
st.caption(f"Portfolio: {st.session_state['label']} ({meta['first']} to {meta['last']}). Assumptions: workbook "
           f"{c['_source']['workbook']} (sha256 {c['_source']['workbook_sha256'][:16]}…)"
           + (" - edited in this session." if S.cfg_edited() else "."))
