import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import exposure as X  # noqa: E402

S.header("🧮 How unused credit costs money")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)
cap, liq = cfg["capital"], cfg["liquidity"]
ex = cfg["presentation"]["worked_example"]
rw = cap[f"risk_weight_{ex['risk_weight_basis']}"]
leq = cfg["drawdown_risk"]["leq_by_segment"][ex["segment"]]
w = X.worked_example(ex["limit_usd"], ex["average_balance_usd"], rw, cfg, ex["chance_of_default"],
                     ex["loss_if_default"], leq)
w45 = X.worked_example(ex["limit_usd"], ex["average_balance_usd"], cap["risk_weight_transactor"], cfg)
money = lambda v: f"${v:,.2f}"  # noqa: E731

# 1. headline sentence
Y.headline(f"Unused credit costs the bank in three ways - capital held aside, liquid assets kept ready, and losses when "
           f"the line is drawn before default - which add up to {money(w['total_unused_line_cost'])} a year for an "
           f"illustrative card with {S.usd(w['ucl'])} unused, {money(w['drawdown_el'])} of it drawdown risk.")

# 2. the worked example: three flows, every multiplier tagged by type
Y.band(f"Worked example: account {ex['account_id']} (illustrative)")
S.cap(f"{ex['description']} · limit {S.usd(ex['limit_usd'])} · average balance {S.usd(ex['average_balance_usd'])} · "
      f"unused line {S.usd(w['ucl'])}. Not a real customer.")
c1, c2 = st.columns([3, 1])
with c1:
    Y.flow("1. Capital", "money held aside", [
        ("box", S.usd(w["ucl"]), "unused line"), ("op", f"× {cap['ccf_unused_card_lines']:.0%}", "regulatory"),
        ("box", S.usd(w["exposure_unused"]), "exposure counted"), ("op", f"× {rw:.0%}", "regulatory"),
        ("box", S.usd(w["rwa_unused"]), "risk-weighted assets"), ("op", f"× {cap['capital_ratio']:.1%}", "business"),
        ("box", money(w["capital_required_unused"]), "capital held"), ("op", f"× {cap['cost_of_equity']:.0%}", "business"),
        ("total", money(w["capital_cost_unused"]), "cost a year")])
    Y.flow("2. Liquidity", "cash kept ready", [
        ("box", S.usd(w["ucl"]), "unused line"), ("op", f"× {liq['lcr_outflow_unused_card_lines']:.0%}", "regulatory"),
        ("box", S.usd(w["hqla"]), "liquid assets held"), ("op", f"× {liq['negative_carry']:.2%}", "business"),
        ("total", money(w["liquidity_cost"]), "cost a year")])
    Y.flow("3. Drawdown risk", "line used before default", [
        ("box", S.usd(w["ucl"]), "unused line"),
        ("op", f"× {ex['chance_of_default']:.0%} chance of default in a year", "measured"),
        ("op", f"× {ex['loss_if_default']:.0%} loss if default", "measured"),
        ("op", f"× {leq:.0%} of the line drawn first", "workbook"),
        ("total", money(w["drawdown_el"]), "expected loss a year")])
    S.md(" ".join(Y.tag(k) for k in ["measured", "regulatory", "business", "workbook"]), unsafe_allow_html=True)
with c2:
    st.markdown(Y.card("Per year", money(w["total_unused_line_cost"]),
                       f"Capital {money(w['capital_cost_unused'])}<br>Liquidity {money(w['liquidity_cost'])}<br>"
                       f"= Carrying cost {money(w['carrying_cost'])}<br>Drawdown risk {money(w['drawdown_el'])}",
                       Y.NAVY, "Total cost of the unused line", hero=True), unsafe_allow_html=True)
S.cap(f"If the same customer paid in full every month, the risk weight would be {cap['risk_weight_transactor']:.0%} and "
      f"the capital cost {money(w45['capital_cost_unused'])}.")

# the portfolio line
S.md(f"**Across all {pb['accounts']:,} cards:** carrying cost {R.short(pb['carrying'])} a year (capital about "
     f"{R.short(pb['capital'])}, liquidity about {R.short(pb['liquidity'])}) plus expected drawdown loss "
     f"{R.short(pb['drawdown'])} = about {R.short(pb['cost'])} a year. Every $1,000 of unused credit costs about "
     f"${pb['carrying'] / max(pb['ucl'], 1) * 1000:,.2f} a year to hold and carries about "
     f"${pb['drawdown'] / max(pb['ucl'], 1) * 1000:,.2f} a year of expected loss. The drawdown risk is the larger part.")

# details
with st.expander("The values behind the calculation, and why we use them"):
    st.dataframe(pd.DataFrame(G.assumptions_table(cfg), columns=["Value", "Used for", "Type", "Why we use it"]),
                 width="stretch", hide_index=True)
    S.cap("Only the account inputs (limits, balances, payment history, default probability, loss rate) are measured. "
          "The capital ratio, cost of equity and carry should be confirmed by the bank's finance team.")
with st.expander("Share of the unused line drawn before default, by customer group"):
    d = cfg["drawdown_risk"]["leq_by_segment"]
    rows = [(S.seg_label(k), f"{d[k]:.0%}") for k in ["deteriorating", "sock_drawer", "dormant", "transactors",
                                                     "relationship"]]
    rows.append((S.seg_label("unassigned"), f"{S.data()[1]['leq_unassigned_measured']:.0%} (portfolio average)"))
    st.dataframe(pd.DataFrame(rows, columns=["Group", "Share drawn before default"]), width="stretch", hide_index=True)
    S.cap("Workbook estimate: the most influential input. It will be replaced with each account's measured behaviour "
          "once real data is available.")
with st.expander("Working assumptions versus current law"):
    st.dataframe(pd.DataFrame(G.current_law(cfg), columns=["Topic", "Current US rules", "Working assumption"]),
                 width="stretch", hide_index=True)
    S.cap("If the proposal is not adopted, most of the capital and liquidity cost disappears. The drawdown risk, which "
          "is most of the cost and most of the value, applies under any rules.")
with st.expander("How it feeds into card profit"):
    S.md("The system starts from the card's profit after all costs, replaces the old capital charge with the new "
         "capital cost, and subtracts the liquidity cost. Expected drawdown loss is shown beside profit, not deducted, "
         "because realised drawdown losses already appear in the card's recorded credit losses; deducting the expected "
         "figure too would count them twice.")
if S.analyst():
    with st.expander("Analyst: formulas, current-rules comparison"):
        S.md(f"- Capital cost = UCL × CCF {cap['ccf_unused_card_lines']:.0%} × RW × capital ratio "
             f"{cap['capital_ratio']:.1%} × cost of equity {cap['cost_of_equity']:.0%}\n"
             f"- Liquidity cost = UCL × LCR outflow {liq['lcr_outflow_unused_card_lines']:.0%} × negative carry "
             f"{liq['negative_carry']:.2%}\n- Drawdown loss = annual PD × LGD × LEQ × UCL (LEQ source "
             f"`{cfg['drawdown_risk']['leq_source']}`)")
        sc = f[f["screened"]]
        cur = X.current_rules(sc, cfg)
        st.dataframe(pd.DataFrame({
            "Working assumptions": [sc["rwa"].sum(), sc["rwa_unused"].sum(), sc["capital_cost"].sum(),
                                    sc["liquidity_cost"].sum(), float("nan")],
            "Current US rules": [cur["rwa_current_rules"].sum(), 0.0, cur["capital_cost_current_rules"].sum(),
                                 cur["liquidity_cost_current_rules"].sum(), cur["slr_capital_required"].sum()]},
            index=["RWA", "RWA from unused lines", "Capital cost a year", "Liquidity cost a year",
                   "SLR capital (10% CCF, 3%)"]).map(S.usd), width="stretch")
S.caveat()
