"""Shared presentation helpers for the Executive Overview and Portfolio
Economics pages - the two pages the business asked to set this app's
design/usability standard, so other pages should reuse this rather than
inventing their own fact/estimate/recommendation labeling convention.
"""
from __future__ import annotations

_KIND_STYLE = {
    "measured": ("\U0001F4CF", "Measured", "#16a34a"),
    "diagnostic": ("\U0001F9EE", "Diagnostic", "#d97706"),
    "recommendation": ("\U0001F3AF", "Recommendation", "#2563eb"),
}


def tag(kind: str) -> str:
    """An inline HTML badge distinguishing a hard fact (measured straight
    from the ledger/transaction data) from a policy-dependent estimate
    (diagnostic) or a lever/routing output (recommendation). Pass the
    result to st.markdown(..., unsafe_allow_html=True) next to a header,
    metric, or caption."""
    icon, label, color = _KIND_STYLE[kind]
    return (f'<span style="background:{color}1a;color:{color};'
           f'border:1px solid {color}55;border-radius:999px;'
           f'padding:1px 10px;font-size:0.75rem;font-weight:600;'
           f'white-space:nowrap;">{icon} {label}</span>')


def legend() -> str:
    """The one-line explanation of the three tags, shown once per page."""
    return (f"Labels used on this page: {tag('measured')} straight from your "
           f"uploaded data &nbsp;&nbsp; {tag('diagnostic')} a policy-based "
           f"estimate &nbsp;&nbsp; {tag('recommendation')} a lever or "
           f"routing output.")
