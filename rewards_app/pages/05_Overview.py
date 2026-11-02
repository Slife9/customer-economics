import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S, style as Y  # noqa: E402
from engine.rewards.assumptions import SCENARIOS, SEGMENTS  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

S.require()
meta = st.session_state["meta"]
t = S.frame()
s = t[t["screened"]]

customers = meta.get("customers") or t["customer"].nunique()
st.title("🎁 L1 Rewards Profitability - overview")
st.caption(f"{st.session_state['label']} · {customers:,} customers, {len(t):,} card accounts · "
           f"trailing 12 months to {meta['last']}")
S.page_link("upload", "Analyse your own data - upload a portfolio", "📤")
S.edited_badge()


def reward_share(sm, when: str):
    """Reward cost incl. sign-up bonuses as a share of revenue, per row of a summary."""
    return (sm[f"{when}_reward_cost"] + sm[f"{when}_signup_bonus"]) / sm[f"{when}_revenue"].where(sm[f"{when}_revenue"] != 0)


# ---------------------------------------------------- today (measured)
n, N = len(s), len(t)
loss = s["fully_loaded_profit"].sum()
share_incl = s["reward_cost_incl_bonus"].sum() / s["revenue"].sum() if n else float("nan")
Y.band("Today - measured from the portfolio's data, trailing 12 months")
Y.cards([
    ("Customers in the portfolio", f"{customers:,}",
     f"{N:,} card accounts analysed · {meta['cycles']} months of history", Y.GREY),
    ("Unprofitable reward accounts", f"{n:,}", f"<b class='bad'>{n / N:.1%}</b> of card accounts", Y.AMBER),
    ("Annual card loss on these accounts", S.usd(loss), f"{S.usd(loss / n) if n else ''} per account per year", Y.RED),
    ("Their reward cost as % of revenue", S.pct(share_incl),
     "rewards and sign-up bonuses paid for every $1 of revenue", Y.RED),
])

# ---------------------------------------------------- scenarios (expected)
st.write("")
c1, c2 = st.columns([3, 2])
with c1:
    Y.band("With the reward levers - expected change per year")
with c2:
    scn = st.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
                   horizontal=True, label_visibility="collapsed")
st.session_state["scenario"] = scn

runs = {sc: S.run(sc, t=t) for sc in SCENARIOS}
tot = {sc: runs[sc][2].loc["total"] for sc in SCENARIOS}
sm = runs[scn][2]
x = tot[scn]
stress = S.run(scn, multiplier=1.5, t=t)[2].loc["total"].change_fully_loaded_profit
gain = x.change_fully_loaded_profit
Y.cards([
    (f"Profit improvement - {scn.capitalize()}", ("+" if gain >= 0 else "") + S.usd(gain),
     f"card loss goes from {S.usd(x.baseline_fully_loaded_profit)} to <b class='{'good' if x.post_fully_loaded_profit >= 0 else 'bad'}'>"
     f"{S.usd(x.post_fully_loaded_profit)}</b>", Y.GREEN if gain >= 0 else Y.RED),
    ("Accounts expected to leave", f"{x.accounts_lost:,.0f}", f"{x.attrition_rate:.1%} of the unprofitable accounts", Y.AMBER),
    ("Reward cost as % of revenue, after", S.pct(reward_share(sm, "post")["total"]),
     f"down from {S.pct(reward_share(sm, 'baseline')['total'])} today", Y.BLUE),
    ("If customers react 1.5x more strongly", ("+" if stress >= 0 else "") + S.usd(stress),
     "<b class='good'>still improves profit</b>" if stress > 0 else "<b class='bad'>no longer improves profit</b>",
     Y.GREEN if stress > 0 else Y.RED),
])

# ---------------------------------------------------- key takeaways
mix = s["segment"].value_counts()
seg_loss = s.groupby("segment")["fully_loaded_profit"].sum()
top_mix, top_loss = mix.index[0], seg_loss.idxmin()
gains = sm.loc[SEGMENTS, "change_fully_loaded_profit"]
top_gain = gains.idxmax()
u = int(mix.get("unassigned", 0))
points = [
    f"<b>{n:,}</b> of {N:,} card accounts ({n / N:.1%}) lose money once rewards are paid - together "
    f"<b>{S.usd(loss)}</b> a year.",
    f"The largest group is <b>{S.seg_label(top_mix)}</b> ({mix[top_mix]:,} accounts, {mix[top_mix] / n:.0%}); the "
    f"biggest loss sits with <b>{S.seg_label(top_loss)}</b> ({S.usd(seg_loss[top_loss])}).",
    f"The <b>{scn.capitalize()}</b> scenario improves card profit by <b>{S.usd(gain)}</b> a year "
    f"({gain / -loss:.0%} of today's loss) while about <b>{x.accounts_lost:,.0f}</b> accounts "
    f"({x.attrition_rate:.1%}) are expected to leave." if loss < 0 else
    f"The <b>{scn.capitalize()}</b> scenario changes card profit by <b>{S.usd(gain)}</b> a year.",
    f"<b>{S.seg_label(top_gain)}</b> deliver {gains[top_gain] / gains.sum():.0%} of the improvement."
    if gains.sum() > 0 else "",
    f"<b>{u:,}</b> accounts ({u / n:.0%}) are Unassigned: unprofitable, but not a rewards problem alone, so no "
    f"reward lever is applied to them." if u else "",
]
st.markdown('<div class="takeaways"><b>Key takeaways</b><ul>' + "".join(f"<li>{p}</li>" for p in points if p)
            + "</ul></div>", unsafe_allow_html=True)
S.caveat()

# ---------------------------------------------------- charts
labels = [sc.capitalize() for sc in SCENARIOS]
order = [k for k in ORDER + ["unassigned"] if k in mix.index]
segs = [k for k in SEGMENTS if k in sm.index and sm.loc[k, "accounts"] > 0]
st.divider()

g1, g2 = st.columns(2)
with g1:
    vals = [tot["base"].baseline_fully_loaded_profit] + [tot[sc].post_fully_loaded_profit for sc in SCENARIOS]
    fig = go.Figure(go.Bar(x=["Today"] + labels, y=vals, text=[S.usd(v) for v in vals], textposition="outside",
                           marker_color=[Y.RED] + [Y.SCENARIO_COLORS[sc] for sc in SCENARIOS]))
    fig.add_hline(y=0, line_color="#334155", line_width=1)
    fig.update_layout(title="Annual card profit of the unprofitable accounts", height=450,
                      yaxis=dict(title="USD per year", range=Y.padded(vals, 0.15)), margin=dict(t=60, b=20))
    st.plotly_chart(fig, width="stretch")
with g2:
    gain_v = [tot[sc].change_fully_loaded_profit for sc in SCENARIOS]
    lost_v = [tot[sc].accounts_lost for sc in SCENARIOS]
    fig = go.Figure()
    fig.add_bar(x=labels, y=gain_v, name="Profit improvement", marker_color=[Y.SCENARIO_COLORS[sc] for sc in SCENARIOS],
                text=["+" + S.usd(v) for v in gain_v], textposition="outside")
    fig.add_scatter(x=labels, y=lost_v, name="Accounts expected to leave", yaxis="y2", mode="lines+markers+text",
                    line=dict(color=Y.AMBER, width=3), marker=dict(size=13), text=[f"{v:,.0f} leave" for v in lost_v],
                    textposition="middle right", textfont=dict(color=Y.AMBER))
    fig.update_layout(title="Profit gained vs accounts lost, by scenario", height=450, margin=dict(t=60, b=20),
                      yaxis=dict(title="Profit improvement, USD", range=Y.padded(gain_v, 0.15)),
                      yaxis2=dict(title="Accounts leaving", overlaying="y", side="right", showgrid=False,
                                  range=[0, max(lost_v) * 2.4 or 1]),
                      legend=dict(orientation="h", y=-0.12))
    st.plotly_chart(fig, width="stretch")

g3, g4 = st.columns(2)
with g3:
    fig = go.Figure(go.Pie(labels=[S.seg_label(k) for k in order], values=[mix[k] for k in order], hole=0.5, sort=False,
                           marker=dict(colors=[Y.SEGMENT_COLORS[k] for k in order]), textinfo="percent",
                           hovertemplate="%{label}: %{value:,} accounts (%{percent})<extra></extra>"))
    fig.update_layout(title="Who the unprofitable accounts are", height=450, margin=dict(t=60, b=20),
                      annotations=[dict(text=f"<b>{n:,}</b><br>accounts", showarrow=False, font=dict(size=20))])
    st.plotly_chart(fig, width="stretch")
with g4:
    sl = seg_loss.reindex(order)
    fig = go.Figure(go.Bar(y=[S.seg_label(k) for k in order], x=sl.values, orientation="h",
                           marker_color=[Y.SEGMENT_COLORS[k] for k in order],
                           text=[S.usd(v) for v in sl.values], textposition="outside"))
    fig.update_layout(title="Where today's loss sits (annual card profit)", height=450,
                      xaxis=dict(title="USD per year", range=Y.padded(sl.values, 0.4)),
                      yaxis=dict(autorange="reversed"), margin=dict(t=60, b=20, l=10, r=20))
    st.plotly_chart(fig, width="stretch")

lines = [("Interchange", "interchange", 1), ("Net interest", "net_interest", 1), ("Annual fees", "annual_fee", 1),
         ("Other fees", "other_fee", 1), ("Rewards", "reward", -1), ("Sign-up bonuses", "signup_bonus", -1),
         ("Credit losses", "credit_loss", -1), ("Operating cost", "variable_opex", -1), ("Capital", "capital", -1),
         ("Fixed cost", "fixed_cost", -1)]
v = [sign * s[col].sum() for _, col, sign in lines]
fig = go.Figure(go.Waterfall(x=[l for l, _, _ in lines] + ["Card profit"], y=v + [loss],
                             measure=["relative"] * len(v) + ["total"], text=[S.usd(a) for a in v + [loss]],
                             textposition="outside", increasing=dict(marker_color=Y.GREEN),
                             decreasing=dict(marker_color=Y.RED), totals=dict(marker_color=Y.NAVY),
                             connector=dict(line=dict(color="#cbd5e1"))))
fig.update_layout(title="Why they lose money: revenue in, costs out, today (all unprofitable reward accounts)",
                  height=500, yaxis_title="USD per year", margin=dict(t=60, b=20))
st.plotly_chart(fig, width="stretch")

g5, g6 = st.columns(2)
with g5:
    gv = sm.loc[segs, "change_fully_loaded_profit"]
    fig = go.Figure(go.Bar(y=[S.seg_label(k) for k in segs], x=gv.values, orientation="h",
                           marker_color=[Y.SEGMENT_COLORS[k] for k in segs],
                           text=[("+" if a >= 0 else "") + S.usd(a) for a in gv.values], textposition="outside"))
    fig.update_layout(title=f"Where the improvement comes from - {scn.capitalize()}", height=450,
                      xaxis=dict(title="Change in annual card profit, USD", range=Y.padded(gv.values, 0.35)),
                      yaxis=dict(autorange="reversed"), margin=dict(t=60, b=20, l=10, r=20))
    st.plotly_chart(fig, width="stretch")
with g6:
    before, after = reward_share(sm, "baseline")[segs], reward_share(sm, "post")[segs]
    names = [S.seg_label(k) for k in segs]
    fig = go.Figure()
    fig.add_bar(y=names, x=before, orientation="h", name="Today", marker_color=Y.RED,
                text=[S.pct(a) for a in before], textposition="outside")
    fig.add_bar(y=names, x=after, orientation="h", name=f"After - {scn.capitalize()}", marker_color=Y.BLUE,
                text=[S.pct(a) for a in after], textposition="outside")
    fig.update_layout(title="Reward cost as % of revenue, by segment", height=450, barmode="group",
                      xaxis=dict(tickformat=".0%", range=[0, max(before.max(), after.max()) * 1.3]),
                      yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.15),
                      margin=dict(t=60, b=20, l=10))
    st.plotly_chart(fig, width="stretch")

mults = [1.0, 1.25, 1.5, 1.75, 2.0]
fig = go.Figure()
for sc in SCENARIOS:
    ys = [S.run(sc, multiplier=m, t=t)[2].loc["total"].change_fully_loaded_profit for m in mults]
    fig.add_scatter(x=mults, y=ys, name=sc.capitalize(), mode="lines+markers+text",
                    line=dict(color=Y.SCENARIO_COLORS[sc], width=3), marker=dict(size=11),
                    text=[S.usd(a) if m in (1.0, 2.0) else "" for a, m in zip(ys, mults)], textposition="top center")
fig.add_hline(y=0, line_color=Y.RED, line_dash="dash", annotation_text="break-even", annotation_position="bottom right")
fig.update_layout(title="Stress test: profit improvement if customers react more strongly than assumed", height=450,
                  xaxis=dict(title="Customer response vs assumed (1x = as assumed)", tickvals=mults,
                             ticktext=[f"{m:g}x" for m in mults], range=[0.9, 2.1]),
                  yaxis=dict(title="Profit improvement, USD", rangemode="tozero"),
                  legend=dict(orientation="h", y=-0.2), margin=dict(t=60, b=20))
st.plotly_chart(fig, width="stretch")

st.caption("Today = measured from the portfolio's ledger. Scenario figures are expected values from the reward "
           "model's lever and customer-response assumptions (editable on **Levers & assumptions**). Detail: "
           "**Scenario dashboard**, **Segments**, **Customer drill-down**.")
