"""L1 Rewards Profitability - standalone app.

    streamlit run rewards_app/Home.py --theme.baseFontSize 18

Only the L1 rewards lever: segment the unprofitable reward accounts and value
the Reward Profitability Scenario Model v2's levers on a portfolio's own data
(engine/rewards). The six-lever app (app/) is separate and unchanged.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rewards_app.lib import style  # noqa: E402

st.set_page_config(page_title="L1 Rewards Profitability", page_icon="🎁", layout="wide")
style.apply()

P = Path(__file__).parent / "pages"
nav = st.navigation({
    "Results": [
        st.Page(P / "05_Overview.py", title="Overview", icon="🏠", url_path="overview", default=True),
        st.Page(P / "10_Dashboard.py", title="Scenario dashboard", icon="📊", url_path="dashboard"),
        st.Page(P / "20_Segments.py", title="Segments", icon="🧩", url_path="segments"),
    ],
    "Model": [
        st.Page(P / "30_Assumptions.py", title="Levers & assumptions", icon="🎚️", url_path="assumptions"),
        st.Page(P / "40_Customers.py", title="Customer drill-down", icon="🔎", url_path="customers"),
    ],
    "Data": [
        st.Page(P / "00_Load.py", title="Load portfolio", icon="📂", url_path="load"),
        st.Page(P / "60_Data.py", title="Data & calibration", icon="🧪", url_path="data"),
        st.Page(P / "70_Downloads.py", title="Downloads", icon="⬇️", url_path="downloads"),
    ],
    "Reference": [
        st.Page(P / "50_Lever_Guide.py", title="Lever guide & regulation", icon="📖", url_path="guide"),
    ],
})
nav.run()
