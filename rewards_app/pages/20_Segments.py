import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402
from engine.rewards.assumptions import SEGMENTS  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

st.title("🧩 Segments")
S.require()
t = S.frame()
c = S.cfg()
th = c["thresholds"]
ref = c["excel_reference_baseline"]

# ---------------------------------------------------- screen funnel
st.subheader("Who gets in: the screen")
elig = t["open_at_last"] & ~t["charged_off"] & (t["tenure_months"] >= th["screen_min_tenure_months"])
loss = elig & (t["fully_loaded_profit"] < th["screen_max_fully_loaded_profit_usd"])
steps = [("Card accounts", len(t)), ("Open, not charged off, open >= 6 months", int(elig.sum())),
         ("…losing money after all costs", int(loss.sum())),
         (f"…and reward cost >= {th['screen_min_reward_cost_share_of_revenue']:.0%} of revenue", int(t["screened"].sum()))]
fig = go.Figure(go.Funnel(y=[s[0] for s in steps], x=[s[1] for s in steps], textinfo="value+percent initial"))
fig.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10))
st.plotly_chart(fig, width="stretch")
st.caption("Profit and reward cost include a sign-up bonus earned in the trailing 12 months (Table26), as the "
           "workbook does - a reward-model cost that the engine's own net economic profit leaves out.")

# ---------------------------------------------------- mix vs workbook
st.subheader("Segment mix - this portfolio vs the workbook")
s = t[t["screened"]]
n = len(s)
ref_total = sum(ref["accounts"].values())
mix = pd.DataFrame([{"Segment": S.seg_label(k), "Accounts": int((s["segment"] == k).sum()),
                     "Share": (s["segment"] == k).sum() / n if n else 0,
                     "Workbook share": ref["accounts"][k] / ref_total if k in ref["accounts"] else None}
                    for k in ORDER + ["unassigned"]])
fig = go.Figure([go.Bar(name="This portfolio", x=mix["Segment"], y=mix["Share"], marker_color="#2563eb"),
                 go.Bar(name="Workbook (illustrative)", x=mix["Segment"], y=mix["Workbook share"], marker_color="#cbd5e1")])
fig.update_layout(barmode="group", height=340, yaxis_tickformat=".0%", margin=dict(t=10, b=10))
st.plotly_chart(fig, width="stretch")
st.dataframe(mix.style.format({"Share": S.pct, "Workbook share": S.pct}), hide_index=True, width="stretch")

# ---------------------------------------------------- profiles
st.subheader("Segment profiles - observed (per account, trailing 12m) vs workbook")
prof = []
for k in SEGMENTS + ["unassigned"]:
    g = s[s["segment"] == k]
    spend = g["spend"].sum()
    rec = {"Segment": S.seg_label(k), "Accounts": len(g),
           "Annual spend": g["spend"].mean() if len(g) else None,
           "Interchange rate": g["ic_tx"].sum() / spend if spend else None,
           "Reward earn rate": g["points_value"].sum() / spend if spend else None,
           "Revolving balance": g["revolving_balance"].mean() if len(g) else None,
           "APR": g["apr"].mean() if len(g) else None,
           "Reward cost % revenue": g["reward_cost_incl_bonus"].sum() / g["revenue"].sum() if len(g) else None,
           "Card profit / account": g["fully_loaded_profit"].mean() if len(g) else None}
    prof.append(rec)
    if k in SEGMENTS:
        prof.append({"Segment": "   workbook", "Accounts": None, "Annual spend": ref["annual_spend_usd"][k],
                     "Interchange rate": ref["interchange_rate"][k], "Reward earn rate": ref["earn_rate"][k],
                     "Revolving balance": ref["revolving_balance_usd"][k], "APR": ref["apr"][k],
                     "Reward cost % revenue": None, "Card profit / account": None})
pdf = pd.DataFrame(prof)
st.dataframe(pdf.style.format({"Annual spend": S.usd, "Revolving balance": S.usd, "Card profit / account": S.usd,
                               "Interchange rate": "{:.2%}", "Reward earn rate": "{:.2%}", "APR": "{:.1%}",
                               "Reward cost % revenue": S.pct, "Accounts": "{:,.0f}"}, na_rep=""),
             hide_index=True, width="stretch", height=460)

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
                f"transactors match no segment. Workbook guidance: keep Unassigned below about 10% or refine the "
                f"thresholds.")
    st.dataframe(pd.DataFrame({"Programme": prog.index, "Accounts": prog.values,
                               "Median spend": [S.usd(u.loc[u.program == p, "spend"].median()) for p in prog.index],
                               "Paid in full >= 10 months": [S.pct((u.loc[u.program == p, "paid_in_full_months"] >= 10).mean())
                                                             for p in prog.index]}),
                 hide_index=True, width="stretch")
