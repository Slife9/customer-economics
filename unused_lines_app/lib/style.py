"""Presentation for the Unused Credit Line Management app: larger, more
legible text, chart fonts, and the page template's pieces (headline
sentence, figure cards with one dominant, traffic-light status tiles,
"What this means" and "What to decide / do" boxes).

Copied from rewards_app/lib/style.py on feature/l1-rewards-system (495b0ec),
not merged; kept self-contained so the two apps can evolve independently.
Changes: segment colours for this module's segments, a value-type badge, the
decision-page template (revision C).

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
SEGMENT_COLORS = {"deteriorating": "#b91c1c", "relationship": "#0f766e", "dormant": "#64748b",
                  "sock_drawer": "#0891b2", "transactors": BLUE, "unassigned": GREY}
VALUE_TYPE_COLORS = {"measured": "#15803d", "regulatory": "#7c3aed", "business": "#b45309",
                     "workbook": "#0891b2", "derived": "#334155"}
# Strategy status (revision E): approved, approved but loses money today (test only),
# awaiting decision, proposed. Always shown with the status text, never colour alone.
STATUS_COLORS = {"approved": "#15803d", "approved_test_only": "#b91c1c", "awaiting_decision": "#d97706",
                 "proposed": "#2563eb"}
HOLDING, DRAWDOWN = "#2563eb", "#b91c1c"
TILE = {"green": ("#15803d", "#f0fdf4", "✅", "OK"), "amber": ("#b45309", "#fffbeb", "⚠️", "Watch"),
        "red": ("#b91c1c", "#fef2f2", "⛔", "Act"), "grey": ("#475569", "#f8fafc", "ℹ️", "Note")}

CSS = """
<style>
html { font-size: 18px; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 1.05rem; line-height: 1.55; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { font-size: 0.98rem !important; color: #475569; }
[data-testid="stMetricLabel"] p { font-size: 1.05rem !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-size: 2.1rem !important; }
[data-testid="stSidebarNav"] a span, [data-testid="stSidebarNavLink"] span { font-size: 1.05rem !important; }
[data-testid="stWidgetLabel"] p { font-size: 1.02rem !important; }
h1 { font-size: 2.1rem !important; }
h2 { font-size: 1.6rem !important; }
h3 { font-size: 1.35rem !important; }
.headline { font-size: 1.35rem; line-height: 1.45; color: #0f172a; font-weight: 500; margin: 2px 0 14px;
            border-left: 5px solid #2563eb; padding: 4px 0 4px 14px; }
.kpi { background: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid var(--accent, #2563eb);
       border-radius: 10px; padding: 14px 16px 12px; height: 100%; box-shadow: 0 1px 2px rgba(15,23,42,.06); }
.kpi.hero { background: #f8fafc; border: 2px solid var(--accent, #2563eb); border-left-width: 8px; }
.kpi .label { font-size: 0.98rem; font-weight: 600; color: #334155; margin-bottom: 6px; hyphens: none;
              word-break: normal; overflow-wrap: normal; }
.kpi .label .i { color: #94a3b8; font-weight: 400; cursor: help; }
.kpi .value { font-size: clamp(1.05rem, 1.8vw, 1.9rem); font-weight: 700; color: #0f172a; line-height: 1.15;
              font-variant-numeric: tabular-nums; white-space: nowrap; }
.kpi.hero .value { font-size: clamp(1.4rem, 2.6vw, 2.7rem); }
.kpi .sub { font-size: 0.92rem; color: #475569; margin-top: 6px; }
.kpi .sub b.good { color: #15803d; } .kpi .sub b.bad { color: #b91c1c; }
.band { font-size: 0.85rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #64748b;
        margin: 6px 0 8px; }
.tile { border-radius: 10px; padding: 12px 14px; height: 100%; border: 1px solid #e2e8f0;
        border-top: 5px solid var(--c); background: var(--bg); }
.tile .name { font-size: .85rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: #475569; }
.tile .state { font-size: 1.0rem; font-weight: 700; color: var(--c); margin: 4px 0 2px; }
.tile .basis { font-size: .9rem; color: #334155; line-height: 1.4; }
.takeaways { background: #f4f6fb; border-radius: 10px; padding: 12px 20px; height: 100%; }
.takeaways li { font-size: 1.05rem; margin: 5px 0; }
.decide { background: #fff7ed; border: 1px solid #fed7aa; border-left: 6px solid #d97706; border-radius: 10px;
          padding: 12px 20px; height: 100%; }
.decide li { font-size: 1.05rem; margin: 5px 0; }
.rec { background: #eff6ff; border: 1px solid #bfdbfe; border-left: 8px solid #2563eb; border-radius: 10px;
       padding: 16px 20px; font-size: 1.25rem; line-height: 1.5; color: #0f172a; }
.rec.none { background: #f8fafc; border-color: #e2e8f0; border-left-color: #94a3b8; }
.vt { display: inline-block; padding: 1px 8px; border-radius: 9px; font-size: .82rem; font-weight: 600; color: #fff; margin-right: 4px; }
.flag { background: #fef2f2; border: 1px solid #fecaca; border-left: 6px solid #b91c1c; border-radius: 10px; padding: 12px 16px; }
.segcard { border: 1px solid #e2e8f0; border-top: 5px solid var(--c); border-radius: 10px; padding: 10px 14px;
           height: 100%; background: #fff; }
.segcard .t { font-weight: 700; font-size: 1.02rem; color: #0f172a; }
.segcard .n { color: #475569; font-size: .9rem; margin-bottom: 6px; }
.segcard table { width: 100%; border-collapse: collapse; font-size: .92rem; }
.segcard td { padding: 2px 0; border: none; } .segcard td.v { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
.segcard .a { margin-top: 6px; font-size: .9rem; color: #1e3a8a; }
.chip { display: inline-block; padding: 1px 10px; border-radius: 10px; font-size: .85rem; font-weight: 700;
        color: var(--c); border: 1.5px solid var(--c); background: #fff; white-space: nowrap; }
.strat { border: 1px solid #e2e8f0; border-top: 6px solid var(--c); border-radius: 10px; padding: 12px 16px;
         background: #fff; height: 100%; }
.strat .h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.strat .t { font-weight: 700; font-size: 1.12rem; color: #0f172a; }
.strat .v { font-weight: 700; font-size: 1.35rem; font-variant-numeric: tabular-nums; color: #0f172a; white-space: nowrap; }
.strat p { margin: 6px 0; font-size: .98rem; color: #334155; }
.strat ul { margin: 4px 0 4px 18px; padding: 0; } .strat li { font-size: .95rem; margin: 2px 0; }
.srow { display: grid; grid-template-columns: 2.2rem 1fr auto auto; gap: 10px; align-items: center;
        padding: 9px 4px; border-bottom: 1px solid #e2e8f0; font-size: 1.05rem; }
.srow .n { font-weight: 700; color: #64748b; } .srow .v { font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.flow { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 14px; margin-bottom: 10px; background: #fff; }
.flow .ft { font-weight: 700; font-size: 1.02rem; color: #0f172a; } .flow .fs { color: #64748b; font-size: .9rem; }
.flow .steps { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 8px; }
.flow .box { border: 1px solid #cbd5e1; border-radius: 8px; padding: 4px 10px; background: #f8fafc; text-align: center; }
.flow .box b { display: block; font-size: 1.1rem; font-variant-numeric: tabular-nums; }
.flow .box span { font-size: .8rem; color: #475569; }
.flow .box.total { background: #eff6ff; border-color: #93c5fd; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: .9rem; font-weight: 700; color: #fff; }
.journey { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0; }
.journey .s { flex: 1 1 140px; border: 1px solid #e2e8f0; border-left: 5px solid var(--c); border-radius: 8px;
              padding: 6px 10px; background: #f8fafc; font-size: .92rem; }
.journey .s b { display: block; font-size: .98rem; }
.notdo { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 6px solid #64748b; border-radius: 10px; padding: 12px 20px; }
.notdo li { font-size: 1.02rem; margin: 4px 0; }
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if "unused_lines" not in pio.templates:
        t = go.layout.Template()
        t.layout.font = dict(size=16, color="#1e293b")
        t.layout.title = dict(font=dict(size=19))
        t.layout.legend = dict(font=dict(size=15))
        t.layout.xaxis = dict(tickfont=dict(size=15), title=dict(font=dict(size=16)), gridcolor="#eef2f7")
        t.layout.yaxis = dict(tickfont=dict(size=15), title=dict(font=dict(size=16)), gridcolor="#eef2f7")
        t.layout.hoverlabel = dict(font=dict(size=15))
        t.data.bar = [go.Bar(textfont=dict(size=15), constraintext="none", cliponaxis=False)]
        t.data.waterfall = [go.Waterfall(textfont=dict(size=15), constraintext="none", cliponaxis=False)]
        t.data.scatter = [go.Scatter(textfont=dict(size=15), cliponaxis=False)]
        t.data.pie = [go.Pie(textfont=dict(size=16))]
        pio.templates["unused_lines"] = t
        pio.templates.default = "plotly_white+unused_lines"


def padded(values, pad: float = 0.3) -> list[float]:
    """Axis range with room for outside bar labels, both signs."""
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    return [lo - (pad * span if lo < 0 else 0), hi + (pad * span if hi > 0 else 0)]


def band(text: str) -> None:
    st.markdown(f'<div class="band">{html.escape(text)}</div>', unsafe_allow_html=True)


def headline(text: str) -> None:
    """The page's headline sentence, generated from results by the caller."""
    st.markdown(f'<div class="headline">{html.escape(text)}</div>', unsafe_allow_html=True)


def card(label: str, value: str, sub: str = "", accent: str = BLUE, hover: str = "", hero: bool = False) -> str:
    """One figure card. `sub` may carry <b class="good|bad"> markup built by
    the caller from numbers, never from data text. `hover` is a one-line
    definition shown on mouse-over."""
    title = f' title="{html.escape(hover)}"' if hover else ""
    tip = f' <span class="i">ⓘ</span>' if hover else ""
    return (f'<div class="kpi{" hero" if hero else ""}" style="--accent:{accent}"{title}>'
            f'<div class="label">{html.escape(label)}{tip}</div>'
            f'<div class="value">{html.escape(value)}</div><div class="sub">{sub}</div></div>')


def cards(items: list[tuple], dominant: int | None = None, widths: list[float] | None = None) -> list:
    """Up to four cards: (label, value, sub, accent[, hover]). The `dominant`
    card is drawn larger. Returns the columns (for links under a card)."""
    if dominant is not None and widths is None:
        widths = [1.35 if i == dominant else 1 for i in range(len(items))]
    cols = st.columns(widths or len(items))
    for i, (col, item) in enumerate(zip(cols, items)):
        label, value, sub, accent, *rest = item
        col.markdown(card(label, value, sub, accent, rest[0] if rest else "", i == dominant), unsafe_allow_html=True)
    return cols


def tiles(items: list[tuple]) -> None:
    """Traffic-light status tiles: (name, colour green|amber|red|grey,
    state text, basis text). Icon and word with the colour - never colour
    alone."""
    for col, (name, colour, state, basis) in zip(st.columns(len(items)), items):
        c, bg, icon, word = TILE[colour]
        col.markdown(f'<div class="tile" style="--c:{c};--bg:{bg}"><div class="name">{html.escape(name)}</div>'
                     f'<div class="state">{icon} {html.escape(word)}: {html.escape(state)}</div>'
                     f'<div class="basis">{html.escape(basis)}</div></div>', unsafe_allow_html=True)


def _box(css: str, title: str, points: list[str], where=st) -> None:
    where.markdown(f'<div class="{css}"><b>{html.escape(title)}</b><ul>'
                   + "".join(f"<li>{html.escape(p)}</li>" for p in points) + "</ul></div>", unsafe_allow_html=True)


def means(points: list[str], where=st, title: str = "What this means") -> None:
    """'What this means': plain-English takeaways."""
    _box("takeaways", title, points, where)


def decide(points: list[str], where=st, title: str = "What to decide / do") -> None:
    _box("decide", title, points, where)


def recommendation(text: str, none: bool = False) -> None:
    st.markdown(f'<div class="rec{" none" if none else ""}">{html.escape(text)}</div>', unsafe_allow_html=True)


def segment_card(title: str, note: str, rows: list[tuple[str, str]], action: str, colour: str) -> str:
    return (f'<div class="segcard" style="--c:{colour}"><div class="t">{html.escape(title)}</div>'
            f'<div class="n">{html.escape(note)}</div><table>'
            + "".join(f"<tr><td>{html.escape(k)}</td><td class='v'>{html.escape(v)}</td></tr>" for k, v in rows)
            + f'</table><div class="a">→ {html.escape(action)}</div></div>')


def chip(status: str, text: str) -> str:
    """A status chip: colour plus the status in words."""
    return f'<span class="chip" style="--c:{STATUS_COLORS[status]}">{html.escape(text)}</span>'


def strategy_list(rows: list[tuple[int, str, str, str, str]]) -> None:
    """Compact strategy rows: (number, name, status key, status text, value text)."""
    st.markdown("".join(f'<div class="srow"><span class="n">{n}</span><span>{html.escape(name)}</span>'
                        f'{chip(sk, stext)}<span class="v">{html.escape(v)}</span></div>'
                        for n, name, sk, stext, v in rows), unsafe_allow_html=True)


def strategy_card(number: int, name: str, status: str, status_text: str, value: str, what: str,
                  who: list[str], why: str, extra: str = "", where=st) -> None:
    """One strategy: what, who, why, status and value. `extra` is markup built
    by the caller (the Strategy 3 journey), never from data text."""
    where.markdown(
        f'<div class="strat" style="--c:{STATUS_COLORS[status]}"><div class="h"><span class="t">{number}. '
        f'{html.escape(name)}</span><span class="v">{html.escape(value)}</span></div>'
        f'<div>{chip(status, status_text)}</div><p><b>What:</b> {html.escape(what)}</p>'
        f'<p><b>Who:</b></p><ul>' + "".join(f"<li>{html.escape(w)}</li>" for w in who) + "</ul>"
        + extra + f'<p><b>Why:</b> {html.escape(why)}</p></div>', unsafe_allow_html=True)


def journey(steps: list[tuple[str, str, str]]) -> str:
    """Markup for a step-by-step journey: (title, text, status key)."""
    return '<div class="journey">' + "".join(
        f'<div class="s" style="--c:{STATUS_COLORS[s]}"><b>{html.escape(t)}</b>{html.escape(x)}</div>'
        for t, x, s in steps) + "</div>"


def tag(kind: str) -> str:
    """A value-type tag for the worked example (the report's colour key)."""
    return (f'<span class="tag" style="background:{VALUE_TYPE_COLORS[kind]}">'
            f"{html.escape(VALUE_TYPE_LABELS[kind])}</span>")


def flow(title: str, sub: str, items: list[tuple], where=st) -> None:
    """One cost flow of the worked example. items: ("box", value, label) or
    ("op", text, value-type kind) or ("total", value, label)."""
    parts = []
    for kind, a, b in items:
        if kind == "op":
            parts.append(f'<span class="tag" style="background:{VALUE_TYPE_COLORS[b]}">{html.escape(a)}</span>')
        else:
            parts.append(f'<div class="box{" total" if kind == "total" else ""}"><b>{html.escape(a)}</b>'
                         f'<span>{html.escape(b)}</span></div>')
    where.markdown(f'<div class="flow"><div class="ft">{html.escape(title)} <span class="fs">{html.escape(sub)}</span>'
                   f'</div><div class="steps">{"".join(parts)}</div></div>', unsafe_allow_html=True)


def not_done(points: list[str], where=st) -> None:
    where.markdown('<div class="notdo"><b>What we deliberately don\'t do</b><ul>'
                   + "".join(f"<li>{html.escape(p)}</li>" for p in points) + "</ul></div>", unsafe_allow_html=True)


VALUE_TYPE_LABELS = {"measured": "Measured", "regulatory": "Assumed (regulatory)",
                     "business": "Assumed (business)", "workbook": "Workbook estimate", "derived": "Derived"}


def vt(kind: str) -> str:
    """A small coloured badge for a value type (measured / assumed / ...)."""
    return (f'<span class="vt" style="background:{VALUE_TYPE_COLORS[kind]}">'
            f"{html.escape(VALUE_TYPE_LABELS[kind])}</span>")
