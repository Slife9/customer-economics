from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import pipeline_runner as PR
from engine.core import outputs as OUT

st.set_page_config(page_title="Downloads", page_icon="⬇️", layout="wide")
st.title("⬇️ Outputs")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
st.caption("The score file is the product (concept spec 5.6) — the rest supports it.")

sf = PR.score_file(result)
wl = PR.worklist_export(result)
lr = PR.leakage_register(result)
ledger = result["ledger"]["card"]

fairness = result["fairness"]
gate_report = st.session_state.get("gate_report", pd.DataFrame())
pack = OUT.governance_pack(fairness, gate_report, result["routing_summary"],
                          result["ledger"]["measured"])

c1, c2 = st.columns(2)
with c1:
    st.subheader("Score file")
    st.caption("customer × month — for the bank's decision systems")
    st.dataframe(sf.head(20), width="stretch")
    st.download_button("Download score_file.csv", sf.to_csv(index=False),
                       "score_file.csv", "text/csv", width="stretch")

    st.subheader("Worklist")
    st.caption("customer × action — for operations")
    st.dataframe(wl.head(20), width="stretch")
    st.download_button("Download worklist.csv", wl.to_csv(index=False),
                       "worklist.csv", "text/csv", width="stretch")

with c2:
    st.subheader("Leakage register")
    st.caption("finding, with owner and amount — for finance to confirm and action")
    st.dataframe(lr, width="stretch")
    st.download_button("Download leakage_register.csv", lr.to_csv(index=False),
                       "leakage_register.csv", "text/csv", width="stretch")

    st.subheader("Governance pack")
    st.caption("model card, fairness, negative control — for model risk")
    st.json(pack, expanded=False)
    st.download_button("Download governance_pack.json",
                       json.dumps(pack, indent=2, default=str),
                       "governance_pack.json", "application/json", width="stretch")

st.divider()
st.subheader("Ledger")
st.caption("account × cycle — for finance to reconcile against the general ledger")
st.dataframe(ledger.head(20), width="stretch")
st.download_button("Download ledger_account_cycle.csv", ledger.to_csv(index=False),
                   "ledger_account_cycle.csv", "text/csv", width="stretch")
