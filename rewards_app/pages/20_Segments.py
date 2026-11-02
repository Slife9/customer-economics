import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S, style as Y  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

st.title("🧩 Segments")
S.require()
t = S.frame()
c = S.cfg()
th = c["thresholds"]

# ---------------------------------------------------- screen funnel
st.subheader("Who gets in: the screen")
elig = t["open_at_last"] & ~t["charged_off"] & (t["tenure_months"] >= th["screen_min_tenure_months"])
loss = elig & (t["fully_loaded_profit"] < th["screen_max_fully_loaded_profit_usd"])
steps = [("Card accounts", len(t)), ("Open, not charged off, open >= 6 months", int(elig.sum())),
         ("…losing money after all costs", int(loss.sum())),
         (f"…and reward cost >= {th['screen_min_reward_cost_share_of_revenue']:.0%} of revenue", int(t["screened"].sum()))]
fig = go.Figure(go.Funnel(y=[s[0] for s in steps], x=[s[1] for s in steps], texttemplate="%{value:,}<br>%{percentInitial:.0%}", textfont=dict(size=16),
                          marker=dict(color=[Y.GREY, Y.LIGHT, Y.AMBER, Y.RED])))
fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10))
st.plotly_chart(fig, width="stretch")
st.caption("Profit and reward cost include a sign-up bonus earned in the trailing 12 months (Table26), as the "
           "workbook does - a reward-model cost that the engine's own net economic profit leaves out.")

# ---------------------------------------------------- mix
st.subheader("Segment mix")
s = t[t["screened"]]
n = len(s)
keys = ORDER + ["unassigned"]
mix = pd.DataFrame([{"Segment": S.seg_label(k), "Accounts": int((s["segment"] == k).sum()),
                     "Share": (s["segment"] == k).sum() / n if n else 0,
                     "Annual card profit": s.loc[s["segment"] == k, "fully_loaded_profit"].sum()}
                    for k in keys])
cols = [Y.SEGMENT_COLORS[k] for k in keys]
m1, m2 = st.columns(2)
with m1:
    fig = go.Figure(go.Bar(y=mix["Segment"], x=mix["Accounts"], orientation="h", marker_color=cols,
                           text=[f"{a:,} ({sh:.0%})" for a, sh in zip(mix["Accounts"], mix["Share"])],
                           textposition="outside"))
    fig.update_layout(title="Unprofitable reward accounts by segment", height=430, margin=dict(t=60, b=10, l=10),
                      xaxis=dict(title="Accounts", range=Y.padded(mix["Accounts"], 0.45)),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")
with m2:
    fig = go.Figure(go.Bar(y=mix["Segment"], x=mix["Annual card profit"], orientation="h", marker_color=cols,
                           text=[S.usd(v) for v in mix["Annual card profit"]], textposition="outside"))
    fig.update_layout(title="Annual card loss by segment", height=430, margin=dict(t=60, b=10, l=10),
                      xaxis=dict(title="USD per year", range=Y.padded(mix["Annual card profit"], 0.45)),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------- profiles
st.subheader("Segment profiles - per account, trailing 12 months")
prof = []
for k in keys:
    g = s[s["segment"] == k]
    spend = g["spend"].sum()
    prof.append({"Segment": S.seg_label(k), "Accounts": len(g),
                 "Annual spend": g["spend"].mean() if len(g) else None,
                 "Interchange rate": g["ic_tx"].sum() / spend if spend else None,
                 "Reward earn rate": g["points_value"].sum() / spend if spend else None,
                 "Revolving balance": g["revolving_balance"].mean() if len(g) else None,
                 "APR": g["apr"].mean() if len(g) else None,
                 "Reward cost % revenue": g["reward_cost_incl_bonus"].sum() / g["revenue"].sum() if len(g) else None,
                 "Card profit / account": g["fully_loaded_profit"].mean() if len(g) else None})
pdf = pd.DataFrame(prof)
st.dataframe(pdf.style.format({"Annual spend": S.usd, "Revolving balance": S.usd, "Card profit / account": S.usd,
                               "Interchange rate": "{:.2%}", "Reward earn rate": "{:.2%}", "APR": "{:.1%}",
                               "Reward cost % revenue": S.pct, "Accounts": "{:,.0f}"}, na_rep=""),
             hide_index=True, width="stretch")

ok = pdf[pdf["Accounts"] > 0]
p1, p2 = st.columns(2)
with p1:
    fig = go.Figure()
    fig.add_bar(y=ok["Segment"], x=ok["Reward earn rate"], orientation="h", name="Rewards paid", marker_color=Y.RED,
                text=[f"{v:.2%}" for v in ok["Reward earn rate"]], textposition="outside")
    fig.add_bar(y=ok["Segment"], x=ok["Interchange rate"], orientation="h", name="Interchange earned",
                marker_color=Y.BLUE, text=[f"{v:.2%}" for v in ok["Interchange rate"]], textposition="outside")
    fig.update_layout(title="Rewards paid vs interchange earned, % of spend", barmode="group", height=520,
                      xaxis=dict(tickformat=".1%", range=[0, ok[["Reward earn rate", "Interchange rate"]].max().max() * 1.35]),
                      yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.15),
                      margin=dict(t=60, b=10, l=10))
    st.plotly_chart(fig, width="stretch")
with p2:
    fig = go.Figure(go.Bar(y=ok["Segment"], x=ok["Annual spend"], orientation="h",
                           marker_color=[Y.SEGMENT_COLORS[k] for k, a in zip(keys, pdf["Accounts"]) if a > 0],
                           text=[S.usd(v) for v in ok["Annual spend"]], textposition="outside"))
    fig.update_layout(title="Average annual spend per account", height=520, margin=dict(t=60, b=10, l=10),
                      xaxis=dict(title="USD", range=Y.padded(ok["Annual spend"], 0.35)), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------- rules
st.subheader("Segment rules (priority order - first match wins)")
rules = pd.DataFrame([
    {"Priority": 1, "Segment": S.seg_label("relationship"),
     "Rule": f"Non-card relationship profit >= ${th['relationship_min_noncard_profit_usd']:,} a year, or deposits >= ${th['relationship_min_deposit_balance_usd']:,}"},
    {"Priority": 2, "Segment": S.seg_label("quasi_cash"),
     "Rule": f"Spend in Table25 quasi-cash / low-interchange MCCs >= {th['quasi_cash_min_spend_share']:.0%}, or effective interchange <= {th['quasi_cash_max_effective_interchange']:.2%}"},
    {"Priority": 3, "Segment": S.seg_label("bonus_chasers"),
     "Rule": f"Tenure <= {th['bonus_chaser_max_tenure_months']} months, sign-up bonus paid, and spend after the window down >= {th['bonus_chaser_min_spend_drop']:.0%} or no purchases since the window"},
    {"Priority": 4, "Segment": S.seg_label("optimizers"),
     "Rule": f"Paid in full >= {th['optimizer_min_paid_in_full_months']} of 12 months, bonus-category share >= {th['optimizer_min_bonus_category_share']:.0%}, annual spend >= ${th['optimizer_min_annual_spend_usd']:,}"},
    {"Priority": 5, "Segment": S.seg_label("low_spend"),
     "Rule": f"Annual spend < ${th['low_spend_max_annual_spend_usd']:,}, tenure >= {th['low_spend_min_tenure_months']} months, active >= {th['low_spend_min_active_months']} of 12 months"},
    {"Priority": 6, "Segment": S.seg_label("unassigned"), "Rule": "None of the above - not a rewards issue alone; review"},
])
st.dataframe(rules, hide_index=True, width="stretch")
st.caption(f"Confirming indicator for bonus chasers (shown in the drill-down, not required): >= "
           f"{th['bonus_chaser_min_inquiries_12m']} credit inquiries in 12 months (Table27).")

# ---------------------------------------------------- unassigned
u = s[s["segment"] == "unassigned"]
if len(u):
    st.subheader(f"Why {len(u):,} accounts are Unassigned")
    prog = u["program"].value_counts()
    flat = u["program"].eq("CORE_CASHBACK_1_5").mean()
    st.markdown(f"**{flat:.0%}** are on the flat-rate cash-back card. Earning 1.5 points worth 1.15 cents each "
                f"(about 1.7% of spend) against about 1.7% interchange, a full-paying customer loses money on "
                f"every dollar - but the workbook's Optimizer rule needs *bonus-category* spend, so flat-rate "
                f"transactors match no segment. Guidance: keep Unassigned below about 10% or refine the "
                f"thresholds on **Levers & assumptions**.")
    st.dataframe(pd.DataFrame({"Programme": prog.index, "Accounts": prog.values,
                               "Median spend": [S.usd(u.loc[u.program == p, "spend"].median()) for p in prog.index],
                               "Paid in full >= 10 months": [S.pct((u.loc[u.program == p, "paid_in_full_months"] >= 10).mean())
                                                             for p in prog.index]}),
                 hide_index=True, width="stretch")
