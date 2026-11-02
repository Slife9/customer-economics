import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402
from rewards_app.lib.guide import SEGMENT_ACTIONS  # noqa: E402
from engine.rewards import segments as SG  # noqa: E402
from engine.rewards.assumptions import SCENARIOS  # noqa: E402
from engine.rewards.segments import ORDER  # noqa: E402

st.title("🔎 Customer drill-down")
S.require()
S.edited_badge()
scn = st.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
               horizontal=True)
st.session_state["scenario"] = scn
t, post, _ = S.run(scn)
s = t[t["screened"]]

# ---------------------------------------------------- worklist
st.subheader("Worklist - screened (unprofitable) reward accounts")
f1, f2, f3 = st.columns(3)
segs = f1.multiselect("Segment", ORDER + ["unassigned"], format_func=S.seg_label)
progs = f2.multiselect("Programme", sorted(s["program"].dropna().unique()))
search = f3.text_input("Search masked account or customer ID")
view = s
if segs:
    view = view[view["segment"].isin(segs)]
if progs:
    view = view[view["program"].isin(progs)]
if search:
    q = search.strip().upper()
    view = view[view.index.str.contains(q, regex=False) | view["customer"].str.contains(q, regex=False)]
wl = pd.DataFrame({
    "Account": view.index, "Customer": view["customer"], "Segment": view["segment"].map(S.seg_label),
    "Programme": view["program"], "Annual spend": view["spend"], "Card profit (12m)": view["fully_loaded_profit"],
    f"Change ({scn})": post.loc[view.index, "fully_loaded_profit"] - view["fully_loaded_profit"],
    "Leave probability": post.loc[view.index, "attrition"]}).sort_values("Card profit (12m)")
st.caption(f"{len(wl):,} of {len(s):,} screened accounts.")
st.dataframe(wl.style.format({"Annual spend": S.usd, "Card profit (12m)": S.usd, f"Change ({scn})": S.usd,
                              "Leave probability": S.pct}), hide_index=True, width="stretch", height=320)
st.download_button("Download this worklist (CSV)", wl.to_csv(index=False), f"l1_rewards_worklist_{scn}.csv",
                   "text/csv")

# ---------------------------------------------------- one account
st.divider()
c1, c2 = st.columns(2)
pick = c1.selectbox("Pick an account (first 1,000 of the worklist)", [""] + wl["Account"].head(1000).tolist())
typed = c2.text_input("…or type any masked account number (screened or not)")
acct = (typed.strip().upper() or pick)
if not acct:
    st.caption("Pick an account to see why it is in scope, its P&L and what each lever does to it.")
    st.stop()
if acct not in t.index:
    st.error(f"{acct} is not a card account in this portfolio.")
    st.stop()

row = t.loc[acct]
seg = row["segment"] if row["screened"] else None
st.subheader(f"{acct} - customer {row['customer']}")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Segment", S.seg_label(seg) if seg else "Not screened")
p2.metric("Programme", str(row["program_name"]))
p3.metric("Tenure", f"{row['tenure_months']:.0f} months")
p4.metric("Card profit, trailing 12m", S.usd(row["fully_loaded_profit"]))
q1, q2, q3, q4 = st.columns(4)
q1.metric("Annual spend", S.usd(row["spend"]))
q2.metric("Earn rate vs interchange", f"{row['earn_rate']:.2%} / {row['effective_interchange']:.2%}"
          if pd.notna(row["effective_interchange"]) else "n/a")
q3.metric("Paid in full (of 12)", f"{row['paid_in_full_months']:.0f}")
q4.metric("Credit inquiries, 12m", "n/a" if pd.isna(row["inquiries_12m"]) else f"{row['inquiries_12m']:.0f}")

trace = SG.segment_trace(t, acct, S.cfg())
mark = lambda b: "✅ met" if b else "❌ not met"
st.markdown("**The screen**")
st.dataframe(pd.DataFrame(trace["screen"]).assign(met=lambda d: d["met"].map(mark)), hide_index=True, width="stretch")
st.markdown("**Segment rules, in priority order** (first fully met set wins)")
for sgt in trace["segments"]:
    with st.expander(f"{'✅' if sgt['all_met'] else '▫️'} {S.seg_label(sgt['segment'])}",
                     expanded=bool(seg and sgt["segment"] == seg)):
        st.dataframe(pd.DataFrame(sgt["rules"]).assign(met=lambda d: d["met"].map(mark)),
                     hide_index=True, width="stretch")

if not seg:
    st.info("Not in the screened population, so no reward lever is valued for this account.")
    st.stop()

# ---------------------------------------------------- P&L before / after
st.markdown(f"**P&L - measured baseline vs {scn.capitalize()} (expected value)**")
p = post.loc[acct]
lines = [("Interchange", "interchange", "interchange"), ("Net interest (after funding)", "net_interest", "net_interest"),
         ("Promo cost on new balance", None, "promo_cost"), ("Annual fee", "annual_fee", "annual_fee"),
         ("Other fees", "other_fee", "other_fee"), ("Reward cost", "reward", "reward"),
         ("Sign-up bonus (reward-model cost)", "signup_bonus", "signup_bonus"), ("Credit loss", "credit_loss", "credit_loss"),
         ("Variable operating cost", "variable_opex", "variable_opex"), ("Capital", "capital", "capital"),
         ("Migrated-account contribution", None, "migrated_contribution"), ("Fixed cost (held constant)", "fixed_cost", "fixed_cost"),
         ("Fully loaded card profit", "fully_loaded_profit", "fully_loaded_profit"),
         ("Non-card relationship profit", "noncard_profit", "noncard_profit"),
         ("Relationship-adjusted profit", "relationship_adjusted_profit", "relationship_adjusted_profit")]
pl = pd.DataFrame([{"Line": n, "Baseline": row[b] if b else 0.0, scn.capitalize(): p[a]} for n, b, a in lines])
pl["Change"] = pl[scn.capitalize()] - pl["Baseline"]
st.dataframe(pl.style.format({c: S.usd for c in ["Baseline", scn.capitalize(), "Change"]}), hide_index=True,
             width="stretch")
r1, r2, r3 = st.columns(3)
r1.metric("Perceived reward value cut", S.pct(p["perceived_value_cut"]))
r2.metric("Probability of leaving", S.pct(p["attrition"]))
r3.metric("Spend change if staying", S.pct(p["spend_change"]))
st.caption("Lines are scaled the way the workbook scales them; all post-change values are expected values "
           "(probability-weighted), not a prediction for this customer. Costs are shown as positive amounts.")

g = SEGMENT_ACTIONS[seg]
st.markdown(f"**Why this segment:** {g['why']}")
st.markdown("**Recommended actions**\n" + "\n".join(f"- {a}" for a in g["actions"]))
st.markdown(f"**Watch-out:** {g['watch']}")
S.caveat()
