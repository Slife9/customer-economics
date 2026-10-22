"""L6 Channel Quality Review - repurposes the former Acquisition Cost page
(its CAC payback content is app/lib/sections/acquisition.py, kept intact)."""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_ui as UI  # noqa: E402
from app.lib.sections import acquisition  # noqa: E402

st.set_page_config(page_title="L6 Channel Quality", page_icon="🧭", layout="wide")
st.title("🧭 L6 Channel Quality Review")
result = UI.require_result()
size = result["sizes"]["L6"]

tab_value, tab_cac = st.tabs(["Overview & value", "Acquisition cost & payback"])
with tab_value:
    UI.value_summary(size)
with tab_cac:
    acquisition.render(result)
