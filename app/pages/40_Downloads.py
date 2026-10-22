from __future__ import annotations
import io
import json
import sys
import zipfile
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
st.caption("Each file is built when you click its button, not when the page opens.")

sf = PR.score_file(result)
wl = PR.worklist_export(result)
lr = PR.leakage_register(result)
ledger = result["ledger"]["card"]

fairness = result["fairness"]
gate_report = st.session_state.get("gate_report", pd.DataFrame())
pack = OUT.governance_pack(fairness, gate_report, result["routing_summary"],
                          result["ledger"]["measured"])

LEDGER_CHUNK_ROWS = 200_000


def _ledger_zip() -> bytes:
    # Written in row chunks straight into the zip: as one CSV string the 100k
    # ledger is ~880 MB on top of the ledger itself, more than a 2 GB
    # instance can spare. Zipped it is ~195 MB.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf, \
            zf.open("ledger_account_cycle.csv", "w", force_zip64=True) as f:
        for i in range(0, len(ledger), LEDGER_CHUNK_ROWS):
            chunk = ledger.iloc[i:i + LEDGER_CHUNK_ROWS]
            f.write(chunk.to_csv(index=False, header=(i == 0)).encode("utf-8"))
    return buf.getvalue()


c1, c2 = st.columns(2)
with c1:
    st.subheader("Score file")
    st.caption("customer × month — for the bank's decision systems")
    st.dataframe(sf.head(20), width="stretch")
    st.download_button("Download score_file.csv", lambda: sf.to_csv(index=False),
                       "score_file.csv", "text/csv", width="stretch")

    st.subheader("Worklist")
    st.caption("customer × action — for operations")
    st.dataframe(wl.head(20), width="stretch")
    st.download_button("Download worklist.csv", lambda: wl.to_csv(index=False),
                       "worklist.csv", "text/csv", width="stretch")

with c2:
    st.subheader("Leakage register")
    st.caption("finding, with owner and amount — for finance to confirm and action")
    st.dataframe(lr, width="stretch")
    st.download_button("Download leakage_register.csv", lambda: lr.to_csv(index=False),
                       "leakage_register.csv", "text/csv", width="stretch")

    st.subheader("Governance pack")
    st.caption("model card, fairness, negative control — for model risk")
    st.json(pack, expanded=False)
    st.download_button("Download governance_pack.json",
                       lambda: json.dumps(pack, indent=2, default=str),
                       "governance_pack.json", "application/json", width="stretch")

st.divider()
st.subheader("Ledger")
st.caption("account × cycle — for finance to reconcile against the general ledger. "
           f"{len(ledger):,} rows, delivered as a zipped CSV; on a large portfolio the "
           "file takes a minute or so to build after you click.")
st.dataframe(ledger.head(20), width="stretch")
st.download_button("Download ledger_account_cycle.csv (zipped)", _ledger_zip,
                   "ledger_account_cycle.zip", "application/zip", width="stretch")
