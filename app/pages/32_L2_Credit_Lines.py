"""L2 Credit Lines & Unused-Line Cost.

Merges what used to be three places: L2's strategy card (Levers & Strategy),
the Liquidity page (app/lib/sections/liquidity.py) and the ML Credit Limit
page (app/lib/sections/ml_credit_limit.py). ML treatment fairness moved to
Governance & Fairness.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import lever_ui as UI  # noqa: E402
from app.lib.sections import liquidity, ml_credit_limit  # noqa: E402

st.set_page_config(page_title="L2 Credit Lines", page_icon="📈", layout="wide")
st.title("📈 L2 Credit Lines & Unused-Line Cost")
result = UI.require_result()
UI.regime_label(result)
size = result["sizes"]["L2"]

tab_value, tab_carry, tab_ml = st.tabs(
    ["Overview & value", "Unused-line carrying cost", "ML second opinion"])

with tab_value:
    UI.value_summary(size)

with tab_carry:
    st.subheader("Carrying cost of unused lines, by L2 group")
    if size.has_scenarios:
        table = pd.DataFrame(size.scenarios["base"]["extras"]["carrying_cost_by_group"])
        st.dataframe(table.rename(columns={
            "action": "L2 group", "customers": "Customers", "unused_lines_usd": "Unused lines",
            "required_hqla_usd": "Required HQLA", "liquidity_cost_usd": "Liquidity cost / yr",
            "slr_cost_usd": "SLR cost / yr", "card_net_usd": "Card net / yr",
            "card_net_after_carrying_cost_usd": "Card net after carrying cost / yr"}).style.format(
            {c: "${:,.0f}" for c in ("Unused lines", "Required HQLA", "Liquidity cost / yr",
                                     "SLR cost / yr", "Card net / yr",
                                     "Card net after carrying cost / yr")}),
            width="stretch", hide_index=True)
    else:
        UI.pre_rebuild_notice(size)
    st.divider()
    liquidity.render(result)

with tab_ml:
    ml_credit_limit.render(result)
