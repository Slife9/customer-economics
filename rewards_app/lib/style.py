"""Presentation for the L1 rewards app: larger, more legible text, chart
fonts, and the figure cards used on the overview.

apply() runs once per page from Home.py, so every page gets it. Tables
(st.dataframe) draw on a canvas that CSS cannot reach - their size follows
theme.baseFontSize, set by the launch command (see rewards_app/README.md).
"""
from __future__ import annotations
import html

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BLUE, NAVY, LIGHT, GREY = "#2563eb", "#1e3a8a", "#60a5fa", "#94a3b8"
GREEN, RED, AMBER = "#15803d", "#b91c1c", "#b45309"
SCENARIO_COLORS = {"conservative": LIGHT, "base": BLUE, "aggressive": NAVY}
SEGMENT_COLORS = {"relationship": "#0f766e", "quasi_cash": "#b45309", "bonus_chasers": "#7c3aed",
                  "optimizers": BLUE, "low_spend": "#0891b2", "unassigned": GREY}

CSS = """
<style>
html { font-size: 18px; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 1.05rem; line-height: 1.55; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { font-size: 0.98rem !important; color: #475569; }
[data-testid="stMetricLabel"] p { font-size: 1.05rem !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-size: 2.1rem !important; }
[data-testid="stSidebarNav"] a span, [data-testid="stSidebarNavLink"] span { font-size: 1.05rem !important; }
[data-testid="stWidgetLabel"] p { font-size: 1.02rem !important; }
h1 { font-size: 2.3rem !important; }
h2 { font-size: 1.75rem !important; }
h3 { font-size: 1.45rem !important; }
.kpi { background: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid var(--accent, #2563eb);
       border-radius: 10px; padding: 16px 18px 14px; height: 100%; box-shadow: 0 1px 2px rgba(15,23,42,.06); }
.kpi .label { font-size: 1.0rem; font-weight: 600; color: #334155; margin-bottom: 6px; hyphens: none;
              word-break: normal; overflow-wrap: normal; }
.kpi .value { font-size: clamp(1.05rem, 1.9vw, 2.15rem); font-weight: 700; color: #0f172a; line-height: 1.15;
              font-variant-numeric: tabular-nums; white-space: nowrap; }
.kpi .sub { font-size: 0.95rem; color: #475569; margin-top: 6px; }
.kpi .sub b.good { color: #15803d; } .kpi .sub b.bad { color: #b91c1c; }
.band { font-size: 0.85rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #64748b;
        margin: 6px 0 8px; }
.takeaways { background: #f4f6fb; border-radius: 10px; padding: 14px 20px; }
.takeaways li { font-size: 1.08rem; margin: 6px 0; }
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if "rewards" not in pio.templates:
        t = go.layout.Template()
        t.layout.font = dict(size=16, color="#1e293b")
        t.layout.title = dict(font=dict(size=20))
        t.layout.legend = dict(font=dict(size=15))
        t.layout.xaxis = dict(tickfont=dict(size=15), title=dict(font=dict(size=16)))
        t.layout.yaxis = dict(tickfont=dict(size=15), title=dict(font=dict(size=16)))
        t.layout.hoverlabel = dict(font=dict(size=15))
        t.data.bar = [go.Bar(textfont=dict(size=15), constraintext="none", cliponaxis=False)]
        t.data.waterfall = [go.Waterfall(textfont=dict(size=15), constraintext="none", cliponaxis=False)]
        t.data.scatter = [go.Scatter(textfont=dict(size=15), cliponaxis=False)]
        t.data.pie = [go.Pie(textfont=dict(size=16))]
        pio.templates["rewards"] = t
        pio.templates.default = "plotly_white+rewards"


def padded(values, pad: float = 0.3) -> list[float]:
    """Axis range with room for outside bar labels, both signs."""
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    return [lo - (pad * span if lo < 0 else 0), hi + (pad * span if hi > 0 else 0)]


def band(text: str) -> None:
    st.markdown(f'<div class="band">{html.escape(text)}</div>', unsafe_allow_html=True)


def card(label: str, value: str, sub: str = "", accent: str = BLUE) -> str:
    """One figure card. `sub` may carry <b class="good|bad"> markup built by
    the caller from numbers, never from data text."""
    return (f'<div class="kpi" style="--accent:{accent}"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(value)}</div><div class="sub">{sub}</div></div>')


def cards(items: list[tuple]) -> None:
    for col, item in zip(st.columns(len(items)), items):
        col.markdown(card(*item), unsafe_allow_html=True)
