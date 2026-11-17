import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402

S.header("🏠 Executive summary")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)
run = S.run("base")
s = run["summary"]
h = s["workbook_levers_headline"]
pend = s["pending_approval"]["headline_value"]
stv = S.stress("base")
fa = S.fairness()
fs = fa["summary"]["module_decreases_and_closures"]
acts = R.actions(run, cfg, S.analyst())

# 1. headline sentence
Y.headline(f"{pb['accounts']:,} card accounts lose money while holding large unused lines. Approved actions are "
           f"worth {R.signed_short(h['headline_value'])} a year; dormant-card actions worth "
           f"{R.signed_short(pend)} more await your decision.")

# 2. four cards, the annual value dominant; each links to its home page
cols = Y.cards([
    (S.term("screened"), f"{pb['accounts']:,}",
     f"of {pb['open']:,} open card accounts · {R.short(pb['card_profit'])} a year on these cards", Y.AMBER,
     S.define("screened")),
    (S.term("unused_cost"), R.short(pb["cost"]),
     f"a year: {R.short(pb['carrying'])} holding + {R.short(pb['drawdown'])} expected losses", Y.RED,
     S.define("unused_cost")),
    (S.term("headline"), R.signed_short(h["headline_value"]), "a year from approved actions (Base scenario)",
     Y.GREEN, S.define("headline")),
    (S.term("pending"), R.signed_short(pend), "a year: dormant-card actions (B6)", Y.AMBER, S.define("pending")),
], dominant=2)
for col, (u, label) in zip(cols, [("cost", "Where the cost sits"), ("cost", "Where the cost sits"),
                                  ("actions", "Actions and value"), ("actions", "Actions and value")]):
    S.page_link(u, label, "➡️", where=col)

# 3. one chart: annual value by the three plain actions, by status
st.write("")
t = R.by_action_status(acts)
fig = go.Figure()
for stt, name in [("approved", "Approved"), ("awaiting", "Awaiting your decision"), ("extra", "Extra (assumption-based)")]:
    fig.add_bar(y=[G.ACTIONS[a][0] for a in t.index], x=t[stt], orientation="h", name=name,
                marker=dict(color=Y.STATUS_COLORS[stt], line=dict(color="#ffffff", width=2)),
                text=[R.signed_short(v) if abs(v) >= 1 else "" for v in t[stt]], textposition="auto",
                insidetextfont=dict(color="#ffffff"),
                hovertemplate="%{y}<br>" + name + ": %{x:$,.0f} a year<extra></extra>")
fig.add_vline(x=0, line_color="#334155", line_width=1)
fig.update_layout(title="Annual value by action", barmode="relative", height=330, margin=dict(t=50, b=10, l=10),
                  xaxis=dict(title="USD per year", tickformat="$,.0f"), yaxis=dict(autorange="reversed"),
                  legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
st.plotly_chart(fig, width="stretch")
S.cap(f"Each action valued on its own. Approved actions together, with their interactions: "
      f"{R.signed_short(h['headline_value'])} a year. One-time capital freed: {S.usd(s['capital_released_one_time'])} "
      "(not annual, never added to the annual value).")

# status tiles
Y.band("Status")
Y.tiles([R.robustness_tile(stv), R.fairness_tile(fa), R.calibration_tile(S.calibration(), cfg), R.rules_tile(),
         R.decisions_tile(run)])
st.write("")

# 4. what this means / 5. what to decide
c1, c2 = st.columns(2)
share = pb["accounts"] / max(pb["open"], 1)
risk_led = -h["drawdown_change"] > abs(h["card_profit_change"])
Y.means([
    f"{share:.0%} of open cards lose money while most of their limit sits unused.",
    (f"Expected losses if lines are drawn ({R.short(pb['drawdown'])}) outweigh the cost of holding them "
     f"({R.short(pb['carrying'])})." if pb["drawdown"] > pb["carrying"] else
     f"Holding unused lines ({R.short(pb['carrying'])}) costs more than their expected losses "
     f"({R.short(pb['drawdown'])})."),
    ("The value comes mostly from lower expected losses; card profit alone barely moves." if risk_led else
     "The value comes mostly from higher card profit."),
], where=c1)
failing = ", ".join(fs["failing_groups"])
Y.decide([
    f"Approve or reject the dormant-card actions (B6): right-size, close, do not reissue - "
    f"{R.signed_short(pend)} a year.",
    (f"Commission a fair-lending review before any pilot: {fs['groups_failing']} metros fail ({failing})."
     if fs["groups_failing"] else
     "Commission a fair-lending review before any pilot: no metro fails; "
     f"{fs['groups_insufficient']} have too few actions to test."),
    f"Pilot first, with a {cfg['treatment']['pilot']['holdout_share']:.0%} holdout: responses are estimates, "
    "not measured.",
], where=c2)

st.write("")
l1, l2, l3, l4 = st.columns(4)
S.page_link("cost", "Where the cost sits", "🧩", where=l1)
S.page_link("actions", "Actions and value", "📊", where=l2)
S.page_link("risks", "Risks and checks", "🛡️", where=l3)
S.page_link("customers", "Customer evidence", "🔎", where=l4)

# 6. details
with st.expander("Details: how the annual value is built"):
    rows = acts[["label", "status", "annual"]].copy()
    rows["status"] = rows["status"].map(R.STATUS_TEXT)
    rows["annual"] = rows["annual"].map(S.signed)
    rows.columns = ["Action", "Status", "Annual value (each on its own)"]
    st.dataframe(rows, width="stretch", hide_index=True)
    if S.analyst():
        S.md(f"- **Headline value** (workbook levers combined, Base): {S.signed(h['headline_value'])} = change in "
             f"card profit {S.signed(h['card_profit_change'])} + reduction in expected drawdown loss "
             f"{S.signed(-h['drawdown_change'])}.\n"
             f"- **Relationship-adjusted change:** {S.signed(h['relationship_adjusted_change'])} (includes the "
             "relationship profit lost with leavers).\n"
             f"- **Extra levers (in the headline status, shown apart):** {S.signed(s['extra_levers']['headline_value'])}.\n"
             "- Value by type: " + ", ".join(f"{k.replace('_', ' ')} {S.signed(h[k])}" for k in
                                             ["avoided_loss", "cost_saving", "revenue", "lost_profit"]) + ".")
    S.caveat()
