"""L1 Rewards Profitability - standalone app.

    streamlit run rewards_app/Home.py --theme.baseFontSize 18 --server.maxUploadSize 4000

Only the L1 rewards lever: segment the unprofitable reward accounts and value
the Reward Profitability Scenario Model v2's levers on a portfolio's own data
(engine/rewards). The six-lever app (app/) is separate and unchanged.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rewards_app.lib import state as S, style  # noqa: E402

st.set_page_config(page_title="L1 Rewards Profitability", page_icon="🎁", layout="wide")
style.apply()

P = Path(__file__).parent / "pages"
groups = {
    "Results": [("05_Overview.py", "Overview", "🏠", "overview"),
                ("10_Dashboard.py", "Scenario dashboard", "📊", "dashboard"),
                ("20_Segments.py", "Segments", "🧩", "segments")],
    "Model": [("30_Assumptions.py", "Levers & assumptions", "🎚️", "assumptions"),
              ("40_Customers.py", "Customer drill-down", "🔎", "customers")],
    "Data": [("00_Load.py", "Upload your data", "📤", "upload"),
             ("60_Data.py", "Data & calibration", "🧪", "data"),
             ("70_Downloads.py", "Downloads", "⬇️", "downloads")],
    "Reference": [("50_Lever_Guide.py", "Lever guide & regulation", "📖", "guide")],
}
S.PAGES.update({u: st.Page(P / f, title=title, icon=icon, url_path=u, default=u == "overview")
                for pages in groups.values() for f, title, icon, u in pages})
nav = st.navigation({g: [S.PAGES[u] for *_, u in pages] for g, pages in groups.items()})
with st.sidebar:
    st.divider()
    if "label" in st.session_state:
        st.caption(f"Data in use: **{st.session_state['label']}**")
    S.page_link("upload", "Upload your own data", "📤")
nav.run()
