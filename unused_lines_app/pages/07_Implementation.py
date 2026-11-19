import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import strategies as ST  # noqa: E402

S.header("🗓️ Implementation")
cfg = S.cfg()
im = cfg["implementation"]
hold = cfg["treatment"]["pilot"]["holdout_share"]
defs = cfg["strategies"]["definitions"]
ph = {p["name"]: p for p in im["phases"]}

# 1. headline sentence
Y.headline(f"The plan runs in four phases over about {im['months_total']} months: prepare (months "
           f"{ph['Prepare']['start']}–{ph['Prepare']['end']}), pilot with a random {hold:.0%} holdout (months "
           f"{ph['Pilot with holdout']['start']}–{ph['Pilot with holdout']['end']}), decide on the results (month "
           f"{im['decision_month']}), then roll out what worked and monitor monthly.")

# 2. one chart: the timeline per strategy
rows = [("Prepare (all strategies)", ph["Prepare"]["start"], ph["Prepare"]["end"], "#64748b", "Prepare")]
for key in cfg["strategies"]["order"]:
    d = defs[key]
    sts = [ST.step_status(cfg, d, s) for s in d["steps"]]
    colour = Y.STATUS_COLORS["awaiting_decision" if "awaiting_decision" in sts else sts[0]]
    for i, step in enumerate(im["by_strategy"][key]):
        c = Y.STATUS_COLORS["awaiting_decision"] if "approved" in step["step"] else colour
        rows.append((f"{d['number']}. {d['name']}", step["start"], step["end"], c, step["step"]))
rows.append(("Decide and scale", im["decision_month"], im["decision_month"], Y.NAVY, "Decide"))
t = pd.DataFrame(rows, columns=["lane", "start", "end", "colour", "step"])
fig = go.Figure()
for r in t.itertuples():
    fig.add_bar(y=[r.lane], x=[r.end - r.start + 1], base=[r.start - 1], orientation="h",
                marker=dict(color=r.colour, line=dict(color="#ffffff", width=2)), text=[r.step],
                textposition="inside", insidetextanchor="middle", insidetextfont=dict(color="#ffffff", size=13),
                hovertemplate=f"{r.step}: months {r.start}–{r.end}<extra></extra>", showlegend=False)
fig.add_vline(x=im["decision_month"] - 0.5, line_dash="dot", line_color=Y.NAVY)
fig.update_layout(title=f"Implementation timeline · {im['months_total']} months from approval", barmode="overlay",
                  height=430, margin=dict(t=50, b=10, l=10),
                  xaxis=dict(title="Month", tickmode="array", tickvals=[m - 0.5 for m in range(1, im["months_total"] + 1)],
                             ticktext=[f"M{m}" for m in range(1, im["months_total"] + 1)], range=[0, im["months_total"]]),
                  yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, width="stretch")
S.cap("Strategy 2 is tested, not scaled, because it loses money at today's offer costs. Strategy 3's actions start "
      "only after the dormant-card decision and the 90-day warning. Timing is indicative, from approval. Colours show "
      "each step's status: green approved, red test only, amber awaiting a decision, blue proposed.")

# 3. pilot design, roles, measures
c1, c2 = st.columns(2)
Y.means(G.PREPARE, where=c1, title="Before the pilot (prepare)")
Y.decide([p.format(holdout=hold) for p in G.PILOT], where=c2, title="Pilot design and success criteria")
with st.expander("Who does what (suggested roles)"):
    st.dataframe(pd.DataFrame(G.ROLES, columns=["Team", "Role"]), width="stretch", hide_index=True)
with st.expander("What we measure"):
    st.dataframe(pd.DataFrame(G.MEASURES, columns=["Measure", "What it tells us", "Compared with"]), width="stretch",
                 hide_index=True)
with st.expander("The four phases"):
    st.dataframe(pd.DataFrame([(p["name"], f"{p['start']}–{p['end']}", p["what"]) for p in im["phases"]],
                              columns=["Phase", "Months", "What happens"]), width="stretch", hide_index=True)
if S.analyst():
    with st.expander("Analyst: the pilot cells"):
        tr = S.treatment()
        st.dataframe(tr.groupby(["segment", "pilot_cell"]).size().unstack(fill_value=0).rename(index=S.seg_label),
                     width="stretch")
        S.cap(f"Seeded holdout of {hold:.0%} per group among accounts with an action (config treatment.pilot).")
S.caveat()
