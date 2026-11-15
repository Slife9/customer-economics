import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS  # noqa: E402
from engine.unused_lines import segments as SG  # noqa: E402

S.header("💳 Unused Credit Line Management - overview")
f = S.frame()
cfg = S.cfg()
sc = f[f["screened"]]
n, N = len(sc), int((f["open_at_reporting_date"] & ~f["charged_off"]).sum())

# ---------------------------------------------------- today (measured + assumed)
Y.band("Today - the unprofitable low-use population, trailing 12 months")
Y.cards([
    ("Screened accounts", f"{n:,}", f"<b class='bad'>{n / max(N, 1):.1%}</b> of {N:,} open card accounts", Y.AMBER),
    ("Card profit on these accounts", S.usd(sc["card_profit"].sum()),
     f"{S.usd(sc['card_profit'].sum() / max(n, 1))} per account a year · measured credit cost, new capital and "
     "liquidity", Y.RED),
    ("Unused lines", S.usd(sc["ucl"].sum()), f"{S.usd(sc['ucl'].mean())} per account (12-month average)", Y.GREY),
    ("Carrying cost (capital + liquidity)", S.usd(sc["carrying_cost"].sum()),
     "capital on the unused part plus the LCR buffer carry, per year", Y.BLUE),
    ("Expected drawdown loss (beside profit)", S.usd(sc["drawdown_el"].sum()),
     "annual PD × LGD × LEQ × unused line - not deducted from card profit", Y.RED),
])
st.markdown(f"Value types: {Y.vt('measured')} card profit, unused lines · {Y.vt('regulatory')} "
            f"{Y.vt('business')} carrying cost · {Y.vt('workbook')} drawdown loss (LEQ)", unsafe_allow_html=True)

# ---------------------------------------------------- scenarios (expected)
st.write("")
c1, c2 = st.columns([3, 2])
with c1:
    Y.band("With the line-management levers - expected change per year")
with c2:
    scn = st.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
                   horizontal=True, label_visibility="collapsed")
st.session_state["scenario"] = scn
r = S.run(scn)
s = r["summary"]
h = s["workbook_levers_headline"]
go_m = cfg["stress_test"]["go_no_go_multiplier"]
st15 = S.run(scn, go_m)["summary"]["workbook_levers_headline"]
Y.cards([
    (f"Annual value - {scn.capitalize()}", S.signed(h["headline_value"]),
     f"change in card profit <b>{S.signed(h['card_profit_change'])}</b> + avoided drawdown loss "
     f"<b>{S.signed(-h['drawdown_change'])}</b>", Y.GREEN if h["headline_value"] >= 0 else Y.RED),
    ("Accounts expected to leave", f"{h['accounts_leaving']:,.0f}", f"of {n:,} screened · unused lines removed "
     f"{S.usd(h['unused_removed'])}", Y.AMBER),
    ("Capital released (one-time)", S.usd(s["capital_released_one_time"]),
     "a stock of capital, <b>never added</b> to the annual value", Y.BLUE),
    (f"If customers react {go_m}x more strongly", S.signed(st15["headline_value"]),
     "<b class='good'>still improves profit (go)</b>" if st15["headline_value"] > 0 else
     "<b class='bad'>no longer improves profit (no-go)</b>", Y.GREEN if st15["headline_value"] > 0 else Y.RED),
])
st.write("")
Y.cards([
    ("Pending approval (B6: dormant right-sizing, closures, non-reissue)", S.signed(s["pending_approval"]["headline_value"]),
     "valued in full, <b>outside</b> the headline until approved", Y.GREY),
    ("Extra levers (assumption-based; not in the reference workbook)", S.signed(s["extra_levers"]["headline_value"]),
     "suppress automatic increases; shown separately from the workbook levers", Y.GREY),
])

# ---------------------------------------------------- key takeaways
summ = SG.summary(f, cfg)
body = summ.drop(index="Total")
top = body["accounts"].idxmax()
cost = body["total_unused_line_cost"].idxmax()
sens = SG.drawdown_sensitivity(f)
lt = r["levers"]
best = lt[(lt["status"] == "headline") & (lt["group"] == "workbook")]["headline_value"].astype(float).idxmax()
points = [
    f"<b>{n:,}</b> of {N:,} open card accounts ({n / max(N, 1):.1%}) are unprofitable, use under 30% of their line "
    f"and have at least $5,000 unused - together {S.usd(sc['card_profit'].sum())} of card profit a year.",
    f"Their unused lines cost <b>{S.usd(sc['carrying_cost'].sum())}</b> a year to carry (capital + liquidity) and "
    f"carry <b>{S.usd(sc['drawdown_el'].sum())}</b> of expected drawdown loss - the larger of the two.",
    f"The largest group is <b>{top}</b> ({int(body.loc[top, 'accounts']):,} accounts); the highest unused-line cost "
    f"sits with <b>{cost}</b> ({S.usd(body.loc[cost, 'total_unused_line_cost'])} a year).",
    f"The <b>{scn.capitalize()}</b> scenario is worth <b>{S.signed(h['headline_value'])}</b> a year; the largest "
    f"contributor is <b>{best}</b>. Capital released ({S.usd(s['capital_released_one_time'])}) is one-time.",
    f"Screening on profit after expected drawdown loss would add <b>{sens['extra_accounts']:,}</b> accounts "
    f"({S.usd(-sens['extra_loss_after_drawdown'])} more loss after drawdown) - the sensitivity toggle on "
    f"<b>Levers & assumptions</b>.",
]
st.markdown('<div class="takeaways"><b>Key takeaways</b><ul>' + "".join(f"<li>{p}</li>" for p in points)
            + "</ul></div>", unsafe_allow_html=True)
S.caveat()

# ---------------------------------------------------- charts
st.divider()
g1, g2 = st.columns(2)
with g1:
    cols = ["carrying_cost", "drawdown_el"]
    fig = go.Figure()
    for col, name, color in [("carrying_cost", "Carrying cost (capital + liquidity)", Y.BLUE),
                             ("drawdown_el", "Expected drawdown loss", Y.RED)]:
        fig.add_bar(x=body.index, y=body[col], name=name, marker_color=color,
                    text=[S.usd(v) for v in body[col]], textposition="outside")
    fig.update_layout(title="Cost of the unused lines by segment, per year", barmode="group", height=470,
                      yaxis=dict(title="USD per year"), margin=dict(t=60, b=20), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, width="stretch")
with g2:
    vals = [S.run(x)["summary"]["workbook_levers_headline"]["headline_value"] for x in SCENARIOS]
    fig = go.Figure(go.Bar(x=[x.capitalize() for x in SCENARIOS], y=vals, text=[S.signed(v) for v in vals],
                           textposition="outside", marker_color=[Y.SCENARIO_COLORS[x] for x in SCENARIOS]))
    fig.add_hline(y=0, line_color="#334155", line_width=1)
    fig.update_layout(title="Annual value by scenario (workbook levers, headline)", height=470,
                      yaxis=dict(title="USD per year", range=Y.padded(vals, 0.2)), margin=dict(t=60, b=20))
    st.plotly_chart(fig, width="stretch")
S.page_link("dashboard", "Scenario dashboard - by segment and lever, year 1 vs full value", "📊")
