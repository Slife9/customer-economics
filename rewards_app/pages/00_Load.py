import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rewards_app.lib import state as S  # noqa: E402

st.title("📂 Load portfolio")
st.caption("Which reward accounts lose money, why, and what each reward lever would be worth - "
           "the Reward Profitability Scenario Model v2 run on your portfolio's own data. The bundled "
           "100,000-customer sample loads automatically; use this page to switch to your own data.")

c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("Load a portfolio")
    choice = st.radio("Bundled sample", list(S.SAMPLES), index=0)
    if st.button("Load sample", type="primary"):
        try:
            with st.spinner("Loading the account P&L…"):
                S.load_sample(choice)
        except FileNotFoundError as e:
            st.error(str(e))
    up = st.file_uploader("…or upload a zipped portfolio (the generator's table CSVs). A 100,000-customer "
                          "portfolio takes several minutes to build.", type="zip")
    if up is not None and st.button("Load upload"):
        try:
            with st.spinner("Validating and building the account P&L…"):
                S.load(S.extract_zip(up.getvalue(), "upload"), up.name)
        except Exception as e:  # contract violations and missing tables, shown plainly
            st.error(f"Could not load this portfolio: {e}")

with c2:
    st.subheader("How it works")
    st.markdown(
        "1. **Measure** each card account's trailing-12-month P&L from the engine's ledger, "
        "plus any sign-up bonus earned (a reward-model cost, kept out of the engine's profit).\n"
        "2. **Screen**: accounts that lose money after all costs *and* whose reward cost is at "
        "least half their revenue.\n"
        "3. **Segment** them by the model's priority rules - Relationship, Quasi-Cash, Bonus "
        "Chasers, Optimizers, Low-Spend - or Unassigned.\n"
        "4. **Value** the nine reward levers per account with the model's customer-response "
        "assumptions, under Conservative, Base or Aggressive.")
    st.caption("Assumptions are the workbook's illustrative industry averages, editable on "
               "**Levers & assumptions**.")

if S.loaded():
    st.divider()
    meta = st.session_state["meta"]
    t = S.frame()
    n = int(t["screened"].sum())
    st.success(f"Loaded **{st.session_state['label']}** - {meta['accounts']:,} card accounts held by "
               f"{t['customer'].nunique():,} customers, {meta['cycles']} cycles ({meta['first']} to {meta['last']}).")
    if st.session_state.get("added_tables"):
        st.info("Computed the reward tables this portfolio was missing: "
                + ", ".join(st.session_state["added_tables"]))
    m1, m2, m3 = st.columns(3)
    m1.metric("Unprofitable reward accounts (screened)", f"{n:,}", f"{n / meta['accounts']:.0%} of accounts",
              delta_color="off")
    m2.metric("Their fully loaded card profit, trailing 12m", S.usd(t.loc[t.screened, "fully_loaded_profit"].sum()))
    m3.metric("Their reward cost as % of revenue",
              S.pct(t.loc[t.screened, "reward_cost_incl_bonus"].sum() / t.loc[t.screened, "revenue"].sum()))
    st.markdown("Next: **Overview** for the headline figures, **Scenario dashboard** for what the levers are "
                "worth, or **Segments** for who these customers are.")
