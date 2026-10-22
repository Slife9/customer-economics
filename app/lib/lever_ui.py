"""Shared building blocks for the per-lever pages (L1-L6) and Strategy
Overview. Every figure shown comes from the engine's SizeResult (live run or
results bundle) - nothing here re-derives a lever value."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.levers import assumptions as ASSUME

VALUE_TYPE_LABELS = {
    "revenue": "Revenue", "cost_saving": "Cost saving", "avoided_loss": "Avoided loss",
    "lost_profit": "Lost profit", "cost": "Cost", "protected_value": "Protected value",
}
PILOT_TAG = "assumption-based, pilot required"


def page_link(path: str, label: str, icon: str | None = None) -> None:
    """st.page_link, falling back to plain text if no navigation registry is
    available (e.g. a page rendered on its own in a headless test). In the
    app the registry always exists, so users always get a working link."""
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:
        st.markdown(f"{icon or ''} **{label}**")


def require_result() -> dict:
    if "result" not in st.session_state:
        st.warning("Run an analysis from the **Home** page first.")
        st.stop()
    return st.session_state["result"]


def active_leverage_policy(result: dict) -> str:
    meta = st.session_state.get("bundle_metadata")
    if meta is not None:
        return meta.leverage_policy_name
    path = str(result.get("leverage_policy_path", ""))
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.replace("leverage_capital_policy.", "").replace(".json", "") or "unknown"


def regime_label(result: dict) -> None:
    """Read-only - the regime is fixed per deployment (no dropdown)."""
    cv = result["customer_view"]
    regime = str(cv["leverage_regime"].iloc[0]) if "leverage_regime" in cv.columns and len(cv) else "?"
    st.caption(f"🏛️ **Active leverage regime (read-only):** `{active_leverage_policy(result)}` "
               f"→ {'Supplementary Leverage Ratio (SLR) - unused lines carry leverage capital' if regime == 'SLR' else 'Tier 1 leverage ratio - unused lines carry no leverage capital'}.")


def pre_rebuild_notice(size) -> bool:
    if size is None or not size.has_scenarios:
        st.warning("These results come from a **pre-rebuild valuation** (an older results "
                   "bundle) - low/base/high scenarios are not available. Re-export the bundle "
                   "with the current engine to see the corrected values.")
        return True
    return False


def components_table(size, scenario: str = "base") -> pd.DataFrame:
    rows = []
    for name, c in size.scenarios[scenario]["components"].items():
        rows.append({
            "Component": name.replace("_", " "),
            "Low": size.scenarios["low"]["components"][name]["value_usd"],
            "Base": c["value_usd"],
            "High": size.scenarios["high"]["components"][name]["value_usd"],
            "Value type": VALUE_TYPE_LABELS.get(c["value_type"], c["value_type"]),
            "Evidence": PILOT_TAG if c["basis"] == "assumption" else "measured",
        })
    return pd.DataFrame(rows)


def value_summary(size, unpriced: bool = False) -> None:
    """Base with low-high range, then the component table."""
    if pre_rebuild_notice(size):
        return
    lo, ba, hi = (size.scenarios[s]["total_usd"] for s in ASSUME.SCENARIOS)
    c1, c2, c3 = st.columns(3)
    if unpriced:
        c1.metric("Value at risk (unpriced)", f"${size.unpriced_context_usd:,.0f}",
                  help="Not a forecast and never part of a portfolio total.")
        c2.metric("Conditional net, base", f"${ba:,.0f}")
        c3.metric("Conditional range", f"${lo:,.0f} – ${hi:,.0f}")
    else:
        c1.metric("Base value, year 1", f"${ba:,.0f}/yr")
        c2.metric("Low – high", f"${lo:,.0f} – ${hi:,.0f}")
        assumption = any(c["basis"] == "assumption"
                         for c in size.scenarios["base"]["components"].values())
        c3.metric("Evidence", PILOT_TAG if assumption else "measured")
    st.dataframe(components_table(size).style.format(
        {c: "${:,.0f}" for c in ("Low", "Base", "High")}), width="stretch", hide_index=True)
