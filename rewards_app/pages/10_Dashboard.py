import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S, style as Y  # noqa: E402
from engine.rewards.assumptions import SCENARIOS, SEGMENTS  # noqa: E402

st.title("📊 Scenario dashboard")
S.require()
S.edited_badge()

scn = st.radio("Scenario for the segment detail", SCENARIOS, index=SCENARIOS.index(S.scenario()),
               format_func=str.capitalize, horizontal=True)
st.session_state["scenario"] = scn

# ---------------------------------------------------- all scenarios
results = {s: S.run(s) for s in SCENARIOS}
t = results["base"][0]
base_tot = results["base"][2].loc["total"]
rows = {"Baseline": {
    "Accounts": base_tot.accounts, "Total revenue": base_tot.baseline_revenue,
    "Reward cost": base_tot.baseline_reward_cost, "Sign-up bonus cost": base_tot.baseline_signup_bonus,
    "Reward cost % of revenue": base_tot.baseline_reward_share_of_revenue,
    "Contribution (variable)": base_tot.baseline_contribution,
    "Fully loaded card profit": base_tot.baseline_fully_loaded_profit,
    "Relationship-adjusted profit": base_tot.baseline_relationship_adjusted_profit,
    "Change in fully loaded card profit": None, "Year 1 change in card profit": None,
    "Change in relationship-adjusted profit": None,
    "Accounts lost": None, "Account attrition %": None,
    "Fully loaded profit per account": base_tot.baseline_profit_per_account}}
for s in SCENARIOS:
    x = results[s][2].loc["total"]
    year1 = S.lever_values(s, t=results[s][0])[1].values.sum()
    rows[s.capitalize()] = {
        "Accounts": x.accounts - x.accounts_lost, "Total revenue": x.post_revenue,
        "Reward cost": x.post_reward_cost, "Sign-up bonus cost": x.post_signup_bonus,
        "Reward cost % of revenue": x.post_reward_share_of_revenue,
        "Contribution (variable)": x.post_contribution,
        "Fully loaded card profit": x.post_fully_loaded_profit,
        "Relationship-adjusted profit": x.post_relationship_adjusted_profit,
        "Change in fully loaded card profit": x.change_fully_loaded_profit,
        "Year 1 change in card profit": year1,
        "Change in relationship-adjusted profit": x.change_relationship_adjusted_profit,
        "Accounts lost": x.accounts_lost, "Account attrition %": x.attrition_rate,
        "Fully loaded profit per account": x.post_profit_per_account}
comp = pd.DataFrame(rows)

st.subheader("Scenario comparison - all screened (unprofitable) reward accounts")
st.caption(f"Annual, trailing 12 cycles to {st.session_state['meta']['last']}. Baseline is measured; the "
           f"scenario columns apply the workbook's levers and response assumptions, at full annual value. The "
           f"year-1 row phases each lever in by its year-1 share (see **Lever guide & regulation**).")
fmt = comp.copy().astype(object)
for r in comp.index:
    f = S.pct if "%" in r else ((lambda v: "" if pd.isna(v) else f"{v:,.0f}") if r.startswith("Accounts") else S.usd)
    fmt.loc[r] = comp.loc[r].map(f)
st.dataframe(fmt, width="stretch")

k1, k2, k3 = st.columns(3)
sel = results[scn][2].loc["total"]
k1.metric(f"{scn.capitalize()}: change in fully loaded card profit", S.usd(sel.change_fully_loaded_profit))
k2.metric("Accounts lost", f"{sel.accounts_lost:,.0f}", f"{sel.attrition_rate:.1%} of screened", delta_color="off")
k3.metric("Reward cost % of revenue", S.pct(sel.post_reward_share_of_revenue),
          f"from {S.pct(sel.baseline_reward_share_of_revenue)}", delta_color="off")

fig = go.Figure(go.Bar(x=["Baseline"] + [s.capitalize() for s in SCENARIOS],
                       y=[comp.loc["Fully loaded card profit", c] for c in comp.columns],
                       marker_color=["#94a3b8", "#60a5fa", "#2563eb", "#1e3a8a"],
                       text=[S.usd(comp.loc["Fully loaded card profit", c]) for c in comp.columns],
                       textposition="outside"))
fig.update_layout(title="Fully loaded card profit of the screened accounts", height=430, margin=dict(t=50, b=20),
                  yaxis=dict(title="USD / year", range=Y.padded(comp.loc["Fully loaded card profit"].astype(float), 0.15)))
st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------- selected scenario by segment
st.divider()
st.subheader(f"{scn.capitalize()} scenario - by segment")
sm = results[scn][2]
seg_rows = []
for seg in SEGMENTS + ["unassigned", "total"]:
    x = sm.loc[seg]
    seg_rows.append({
        "Segment": "Total" if seg == "total" else S.seg_label(seg), "Accounts": int(x.accounts),
        "Baseline card profit": x.baseline_fully_loaded_profit, "Post-change card profit": x.post_fully_loaded_profit,
        "Change in card profit": x.change_fully_loaded_profit, "Attrition %": x.attrition_rate,
        "Baseline profit / acct": x.baseline_profit_per_account, "Post profit / acct": x.post_profit_per_account,
        "Change in relationship-adj. profit": x.change_relationship_adjusted_profit,
        "Reward cost % rev (post)": x.post_reward_share_of_revenue})
segdf = pd.DataFrame(seg_rows)
st.dataframe(segdf.style.format({c: S.usd for c in segdf.columns if "profit" in c.lower()}
                                | {"Attrition %": S.pct, "Reward cost % rev (post)": S.pct}),
             hide_index=True, width="stretch")
st.caption("Unassigned accounts get no reward lever - the workbook routes them to credit or operations "
           "levers. Their baseline is shown so the total reconciles.")

bar = segdf[segdf["Segment"] != "Total"]
fig2 = go.Figure(go.Bar(y=bar["Segment"], x=bar["Change in card profit"], orientation="h",
                        marker_color=[Y.GREEN if v >= 0 else Y.RED for v in bar["Change in card profit"]],
                        text=[S.usd(v) for v in bar["Change in card profit"]], textposition="outside"))
fig2.update_layout(title=f"Change in fully loaded card profit by segment - {scn.capitalize()}", height=430,
                   margin=dict(t=50, b=20, l=10), yaxis=dict(autorange="reversed"),
                   xaxis=dict(title="USD per year", range=Y.padded(bar["Change in card profit"].astype(float), 0.3)))
st.plotly_chart(fig2, width="stretch")

# ---------------------------------------------------- stress test
st.divider()
st.subheader("Stress test - customers more reactive than assumed")
st.caption("The workbook's guidance: re-run at 1.5x before approval, and proceed only if the scenario "
           "still improves profit.")
stress = []
for m in (1.0, 1.5, 2.0):
    x = S.run(scn, multiplier=m)[2].loc["total"]
    stress.append({"Response multiplier": f"{m:.1f}x", "Change in card profit": S.usd(x.change_fully_loaded_profit),
                   "Change in relationship-adj. profit": S.usd(x.change_relationship_adjusted_profit),
                   "Attrition": S.pct(x.attrition_rate)})
st.dataframe(pd.DataFrame(stress), hide_index=True, width="stretch")
S.caveat()
