"""Unused Credit Line Management - standalone app.

    streamlit run unused_lines_app/Home.py --theme.baseFontSize 18

The unused-line module (engine/unused_lines): who carries costly unused card
lines, what each line-management action is worth, and what each customer
would be offered, under the agreed working assumptions. It reads precomputed
samples only (samples/unused_lines/); the six-lever app (app/) is separate and
unchanged. Page layout follows rewards_app/Home.py on feature/l1-rewards-system
(495b0ec), copied, not merged.

Two views (sidebar): Executive (default) - five decision pages in plain
language; Analyst - the same pages with every detail, plus Explore & reference.
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
    "Decisions": [("01_Summary.py", "Executive summary", "🏠", "summary"),
                  ("02_Cost.py", "Where the cost sits", "🧩", "cost"),
                  ("03_Actions.py", "Actions and value", "📊", "actions"),
                  ("04_Risks.py", "Risks and checks", "🛡️", "risks"),
                  ("05_Customers.py", "Customer evidence", "🔎", "customers")],
    "Explore & reference": [("40_What_If.py", "What-if (levers & assumptions)", "🎚️", "whatif"),
                            ("50_Lever_Guide.py", "Lever guide & regulation", "📖", "guide"),
                            ("70_Data.py", "Data & calibration", "🧪", "data"),
                            ("80_Technical.py", "Technical", "🛠️", "technical")],
}
S.PAGES.update({u: st.Page(P / f, title=title, icon=icon, url_path=u, default=u == "summary")
                for pages in groups.values() for f, title, icon, u in pages})
# The view and dataset switches write straight to session state (their keys),
# so a change needs no extra rerun and the page keeps its own selections.
st.session_state.setdefault("view", S.DEFAULT_VIEW)
st.session_state.setdefault("dataset", S.DEFAULT_DATASET)
names = {"stress": "Stress book (synthetic stress data)", "demo": "5k demo (standard bank)"}
with st.sidebar:
    st.radio("View", list(S.VIEWS), key="view", format_func=S.VIEWS.get, horizontal=True,
             help="Executive: plain language, the decision figures. Analyst: every detail, formulas and the "
                  "Explore & reference pages.")
    st.radio("Dataset", list(names), key="dataset", format_func=names.get)
shown = {g: p for g, p in groups.items() if S.analyst() or g != "Explore & reference"}
nav = st.navigation({g: [S.PAGES[u] for *_, u in pages] for g, pages in shown.items()})
with st.sidebar:
    st.divider()
    i = S.info()
    st.caption(f"{i['label']} · {i['card_accounts']:,} card accounts · trailing 12 months to {i['to']}")
    st.divider()
    st.caption(f"⚖️ {S.LABEL}")
nav.run()
