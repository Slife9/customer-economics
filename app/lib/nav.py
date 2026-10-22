"""Grouped sidebar navigation (st.navigation) - the single registry of app
pages. app/Home.py is the entrypoint and only builds this navigation; every
page lives in app/pages/. Paths are relative to app/ (the entrypoint's
folder), which is also what st.page_link expects.

Removed controls are deliberately NOT re-added anywhere: generator link,
Clear cache button, negative-control upload, leverage-regime dropdown.
"""
from __future__ import annotations

import streamlit as st

HOME = "pages/00_Landing.py"
PORTFOLIO_ECONOMICS = "pages/10_Portfolio_Economics.py"
STRATEGY_OVERVIEW = "pages/20_Strategy_Overview.py"
PLAYBOOK = "pages/21_Lever_Playbook.py"
GOVERNANCE = "pages/30_Governance_and_Fairness.py"
DOWNLOADS = "pages/40_Downloads.py"

# code -> (path, sidebar title, icon, url path). A lever is listed only once
# its page exists, so the sidebar never shows a placeholder.
LEVER_PAGES = {
    "L1": ("pages/31_L1_Rewards.py", "L1 Rewards & Promo Economics", "🎁", "l1-rewards"),
    "L2": ("pages/32_L2_Credit_Lines.py", "L2 Credit Lines & Unused-Line Cost", "📈", "l2-credit-lines"),
    "L3": ("pages/33_L3_Pricing.py", "L3 Value-Based Pricing", "💲", "l3-pricing"),
    "L4": ("pages/34_L4_Cost_to_Serve.py", "L4 Cost-to-Serve Migration", "⚙️", "l4-cost-to-serve"),
    "L5": ("pages/35_L5_Retention.py", "L5 Retention Targeting", "🛟", "l5-retention"),
    "L6": ("pages/36_L6_Channel_Quality.py", "L6 Channel Quality Review", "🧭", "l6-channel-quality"),
}
BUILT_LEVER_PAGES = ("L1", "L2", "L3", "L4", "L6")


def lever_page(code: str) -> str | None:
    return LEVER_PAGES[code][0] if code in BUILT_LEVER_PAGES else None


def sections() -> dict:
    # Explicit url_path on every page: Streamlit would otherwise infer "Home"
    # for several pages; and the landing page is 00_Landing.py, not 00_Home.py,
    # because a page inferring "Home" collides with the Home.py entrypoint.
    return {
        "Overview": [
            st.Page(HOME, title="Home", icon="💳", default=True),
            st.Page(PORTFOLIO_ECONOMICS, title="Portfolio Economics", icon="📊",
                    url_path="portfolio-economics"),
        ],
        "Strategies": [st.Page(STRATEGY_OVERVIEW, title="Strategy Overview", icon="🎯",
                               url_path="strategy-overview")]
        + [st.Page(path, title=title, icon=icon, url_path=url)
           for code, (path, title, icon, url) in LEVER_PAGES.items() if code in BUILT_LEVER_PAGES],
        "Governance & Outputs": [
            st.Page(GOVERNANCE, title="Governance & Fairness", icon="🛡️",
                    url_path="governance-and-fairness"),
            st.Page(DOWNLOADS, title="Downloads", icon="⬇️", url_path="downloads"),
        ],
        "Reference": [st.Page(PLAYBOOK, title="Lever Playbook", icon="📖",
                              url_path="lever-playbook")],
    }
