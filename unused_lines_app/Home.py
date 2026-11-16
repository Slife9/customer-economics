"""Unused Credit Line Management - standalone app.

    streamlit run unused_lines_app/Home.py --theme.baseFontSize 18

The unused-line module (engine/unused_lines): who carries costly unused card
lines, what each line-management lever is worth, and what each customer would
be offered, under the agreed working assumptions. It reads precomputed samples
only (samples/unused_lines/); the six-lever app (app/) is separate and
unchanged. Page layout follows rewards_app/Home.py on feature/l1-rewards-system
(495b0ec), copied, not merged.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unused_lines_app.lib import state as S, style  # noqa: E402

st.set_page_config(page_title="Unused Credit Line Management", page_icon="💳", layout="wide")
style.apply()

P = Path(__file__).parent / "pages"
groups = {
    "Results": [("05_Overview.py", "Overview", "🏠", "overview"),
                ("30_Dashboard.py", "Scenario dashboard", "📊", "dashboard"),
                ("20_Segments.py", "Segments", "🧩", "segments")],
    "Customers": [("60_Customers.py", "Customer drill-down", "🔎", "customers")],
    "Model": [("10_Regulatory.py", "Regulatory settings", "⚖️", "regulatory"),
              ("40_Levers.py", "Levers & assumptions", "🎚️", "levers")],
    "Reference": [("50_Lever_Guide.py", "Lever guide & regulation", "📖", "guide"),
                  ("70_Data.py", "Datasets & calibration", "🧪", "data")],
}
S.PAGES.update({u: st.Page(P / f, title=title, icon=icon, url_path=u, default=u == "overview")
                for pages in groups.values() for f, title, icon, u in pages})
nav = st.navigation({g: [S.PAGES[u] for *_, u in pages] for g, pages in groups.items()})
with st.sidebar:
    st.divider()
    names = {"stress": "Stress book (synthetic stress data)", "demo": "5k demo (standard bank)"}
    choice = st.radio("Dataset", list(names), index=list(names).index(S.dataset()), format_func=names.get)
    if choice != S.dataset():
        st.session_state["dataset"] = choice
        st.rerun()
    i = S.info()
    st.caption(f"{i['label']} · {i['card_accounts']:,} card accounts · trailing 12 months to {i['to']}")
    st.divider()
    st.caption(f"⚖️ {S.LABEL}")
nav.run()
