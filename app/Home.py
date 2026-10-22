"""ProfitInsight Customer Economics System - app entrypoint.

    streamlit run app/Home.py

Builds the grouped sidebar navigation (app/lib/nav.py) and runs the selected
page. The landing page itself is app/pages/00_Landing.py. The file name is kept
as the entrypoint because render.yaml's startCommand and the docs launch it.
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.lib import nav  # noqa: E402

st.set_page_config(page_title="ProfitInsight — Customer Economics System",
                   page_icon="💳", layout="wide")
st.navigation(nav.sections()).run()
