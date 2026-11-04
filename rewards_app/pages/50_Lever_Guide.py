import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S, style as Y  # noqa: E402
from rewards_app.lib.guide import (GUARDRAILS, LEVER_GUIDE, LEVER_TIMING, SEGMENT_ACTIONS, TIMELINE,  # noqa: E402
                                   TIMING_DRIVERS, TIMING_HEADLINE)
from engine.rewards.assumptions import LEVERS, SCENARIOS  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

st.title("📖 Lever guide & regulation")
st.caption("Summarised from the Reward Profitability Scenario Model v2's Lever Guide and Segment Definitions. "
           "Terms are illustrative designs - adapt to your products, test against a holdout, and clear with "
           "Compliance before launch.")

timing = S.cfg()["lever_timing"]
names = [g[0] for g in LEVER_GUIDE]  # LEVER_GUIDE is in LEVERS order


def table(df: pd.DataFrame, nowrap: tuple = ()) -> None:
    """st.table wraps long text; its cells are markdown, so '$' must not start
    maths. `nowrap` columns (figures) stay on one line."""
    out = df.map(lambda v: v.replace("$", "\\$") if isinstance(v, str) else v)
    st.table(out.style.set_properties(subset=list(nowrap), **{"white-space": "nowrap"}) if nowrap else out)


st.subheader("The nine levers")
table(pd.DataFrame(
    [(*g, f"Starts month {timing[k]['months_to_start']:g}; full value from about month "
          f"{timing[k]['months_to_full_value']:g}; {timing[k]['year1_share']:.0%} of the annual value in year 1")
     for g, k in zip(LEVER_GUIDE, LEVERS)],
    columns=["Lever", "What it is", "Example (Base scenario)", "Compliance", "When it pays"]).set_index("Lever"))

# ---------------------------------------------------- timing
st.subheader("When each lever pays off")
st.info(f"**{TIMING_HEADLINE}**")

S.require()
S.edited_badge()
scn = st.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
               horizontal=True)
st.session_state["scenario"] = scn
annual, year1 = (v.sum(axis=1) for v in S.lever_values(scn))
A, Y1 = annual.sum(), year1.sum()
Y.cards([
    (f"Full annual value - {scn.capitalize()}", S.signed(A), "change in card profit once every lever is fully in "
                                                             "place", Y.GREEN if A >= 0 else Y.RED),
    ("Year 1 - first 12 months after launch", S.signed(Y1),
     f"<b class='good'>{Y1 / A:.0%}</b> of the annual value" if A > 0 else "", Y.BLUE),
    ("Not yet earned in year 1", S.usd(A - Y1), "arrives from year 2, as fees and balance offers mature", Y.AMBER),
])
st.write("")

table(pd.DataFrame({
    "Lever": names,
    "Starts earning": [s for s, _ in LEVER_TIMING],
    "Full annual value": [f for _, f in LEVER_TIMING],
    "Share in year 1": [f"{timing[k]['year1_share']:.0%}" for k in LEVERS],
    f"Annual value ({scn.capitalize()})": [S.signed(annual[k]) if annual[k] else "not used" for k in LEVERS],
    "Year 1": [S.signed(year1[k]) if annual[k] else "not used" for k in LEVERS],
}).set_index("Lever"), nowrap=("Share in year 1", f"Annual value ({scn.capitalize()})", "Year 1"))
st.caption("The year-1 share is a planning estimate, not a rule: a lever worth $1M a year may deliver only part of "
           "that in its first year. Each lever's annual value is its share of the scenario's total change in card "
           "profit - what it adds on top of the other levers, averaged over every order they could be switched on "
           "in - so the nine add up exactly to the scenario total. Timings and shares are editable on "
           "**Levers & assumptions**.")

g1, g2 = st.container(), st.container()  # full width each: nine labelled bars
with g1:
    used = [k for k in annual.sort_values(ascending=False).index if annual[k]]
    lab = [names[LEVERS.index(k)] for k in used]
    fig = go.Figure()
    fig.add_bar(y=lab, x=[annual[k] for k in used], orientation="h", name="Full annual value", marker_color=Y.NAVY,
                text=[S.signed(annual[k]) for k in used], textposition="outside")
    fig.add_bar(y=lab, x=[year1[k] for k in used], orientation="h", name="Year 1", marker_color=Y.LIGHT,
                text=[S.signed(year1[k]) for k in used], textposition="outside")
    fig.update_layout(title=f"Annual value vs year 1, by lever - {scn.capitalize()}", height=520, barmode="group",
                      xaxis=dict(title="Change in card profit, USD", range=Y.padded([annual[k] for k in used], 0.45)),
                      yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.15),
                      margin=dict(t=60, b=20, l=10))
    st.plotly_chart(fig, width="stretch")
with g2:
    end = 24
    start = [timing[k]["months_to_start"] for k in LEVERS]
    full = [timing[k]["months_to_full_value"] for k in LEVERS]
    fig = go.Figure()
    fig.add_bar(y=names, base=start, x=[f - s for s, f in zip(start, full)], orientation="h", name="Ramping up",
                marker_color=Y.LIGHT, hovertemplate="%{y}: starts month %{base}<extra></extra>")
    fig.add_bar(y=names, base=full, x=[end - f for f in full], orientation="h", name="Full annual value",
                marker_color=Y.NAVY, text=[f"{timing[k]['year1_share']:.0%} in year 1" for k in LEVERS],
                textposition="inside", insidetextanchor="end", textfont=dict(color="white"),
                hovertemplate="%{y}: full value from month %{base}<extra></extra>")
    fig.add_vline(x=12, line_color=Y.RED, line_dash="dash", annotation_text="end of year 1",
                  annotation_position="top")
    fig.update_layout(title="Timeline: months after launch", height=520, barmode="overlay",
                      xaxis=dict(title="Month", range=[0, end], dtick=3), yaxis=dict(autorange="reversed"),
                      legend=dict(orientation="h", y=-0.15), margin=dict(t=60, b=20, l=10))
    st.plotly_chart(fig, width="stretch")

for col, (when, what) in zip(st.columns(len(TIMELINE)), TIMELINE):
    with col.container(border=True):
        st.markdown(f"**{when}**  \n{what}")

st.markdown("**What drives the timing**")
table(pd.DataFrame(TIMING_DRIVERS, columns=["Rule or factor", "Effect on timing"]).set_index("Rule or factor"))

# ---------------------------------------------------- segments, model, regulation
st.subheader("What to do, by segment")
for seg in ORDER + ["unassigned"]:
    g = SEGMENT_ACTIONS[seg]
    with st.expander(S.seg_label(seg)):
        st.markdown(f"**Who:** {g['why']}")
        st.markdown("\n".join(f"- {a}" for a in g["actions"]))
        st.markdown(f"**Watch-out:** {g['watch']}")

st.subheader("How the model works")
st.markdown(
    "- **Perceived reward value cut** = 1 - (new earn / old earn) x (1 - excluded spend) x (1 - cap effect) "
    "x (1 - steering x pass-through). Merchant-funded offers don't reduce perceived value.\n"
    "- **Leave probability** = min(cap, multiplier x [cut / 10% x attrition sensitivity + fee increase / $100 "
    "x fee sensitivity]).\n"
    "- Retained accounts' **spend** changes by cut / 10% x spend sensitivity. Migrated accounts earn "
    "non-rewards interchange on reduced spend and have their own product-change attrition.\n"
    "- **Fixed cost is held constant**: closing an account removes only its variable cost.\n"
    "- Non-card relationship profit is lost when an account leaves.\n"
    "- Every scenario figure is a **full annual value** (run-rate). **Year 1** = each lever's annual value x its "
    "year-1 share.")

st.subheader("Regulatory guardrails (US)")
st.markdown("\n".join(f"- {g}" for g in GUARDRAILS))
