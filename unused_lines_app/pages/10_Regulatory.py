import copy
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402
from engine.unused_lines import assumptions as A, exposure as X, treatment as T  # noqa: E402

S.header("⚖️ Regulatory settings")
cfg = S.cfg()

# ---------------------------------------------------- toggles (session only)
Y.band("Bank profile - exploration only, never saved")
bp = cfg["bank_profile"]
c1, c2, c3 = st.columns(3)
apply_to = c1.radio("Apply the conservative LCR assumption to", bp["apply_to_options"],
                    index=bp["apply_to_options"].index(bp["apply_to"]),
                    format_func={"category_I_III": "Category I-III banks (default)", "all_banks": "All banks"}.get)
category = c2.radio("This bank is", bp["bank_category_options"], index=bp["bank_category_options"].index(bp["bank_category"]),
                    format_func={"category_I_III": "Category I-III (default)",
                                 "category_IV_or_other": "Category IV or other"}.get)
show_cmp = c3.toggle("Show the current US rules comparison", value=bp["comparison_view_current_rules_enabled"])
if (apply_to, category) != (bp["apply_to"], bp["bank_category"]):
    new = copy.deepcopy(cfg)
    new["bank_profile"]["apply_to"], new["bank_profile"]["bank_category"] = apply_to, category
    S.set_cfg(new)
    st.rerun()
st.caption(f"Liquidity cost applies: **{'yes' if A.liquidity_applies(cfg) else 'no'}**. Capital uses the 10% CCF and "
           "45% / 75% / 100% risk weights for every bank under the working assumptions.")

# ---------------------------------------------------- parameters
Y.band("Parameters")
cap, liq = cfg["capital"], cfg["liquidity"]
rows = [
    ("CCF on unused card lines", f"{cap['ccf_unused_card_lines']:.0%}", "regulatory", "No card line ever gets 0% (working assumption; current law 0%)"),
    ("Risk weight - transactor", f"{cap['risk_weight_transactor']:.0%}", "regulatory", "Paid in full (or nothing due) every cycle for 12 months, no plan / promotional balance"),
    ("Risk weight - non-transactor", f"{cap['risk_weight_non_transactor']:.0%}", "regulatory", "Any revolving, plan or promotional balance; under 12 months of history"),
    ("Risk weight - dormant zero-balance (B5)", f"{cap['risk_weight_dormant_zero_balance']:.0%}", "regulatory", "Provisional, pending the open decision"),
    ("Risk weight - non-qualifying retail", f"{cap['risk_weight_non_qualifying_retail']:.0%}", "regulatory", f"Aggregate retail exposure above ${cap['regulatory_retail_aggregate_limit_usd']:,.0f}"),
    ("Capital ratio", f"{cap['capital_ratio']:.1%}", "business", "Illustrative (B4)"),
    ("Cost of equity", f"{cap['cost_of_equity']:.0%}", "business", "Illustrative (B4); capital cost = RWA × 1.26% a year"),
    ("LCR outflow on unused card lines", f"{liq['lcr_outflow_unused_card_lines']:.0%}", "regulatory", "Conservative assumption: cancellable lines are not 'committed' under current law"),
    ("Negative carry on the HQLA buffer", f"{liq['negative_carry']:.2%}", "business", "Funding cost minus HQLA yield"),
    ("Drawdown loss", "annual PD × LGD × LEQ × unused", "workbook", "Annual PD (Table8 PD 12 Month), never lifetime; LEQ by segment from the workbook"),
    ("Operational risk", "excluded", "regulatory", "Bank-level only: not in account or lever economics"),
    ("SLR", "not calculated", "regulatory", "Risk-based capital assumed to bind; shown in the comparison view"),
]
st.markdown("<table><tr><th>Parameter</th><th>Value</th><th>Type</th><th>Note</th></tr>" + "".join(
    f"<tr><td>{a}</td><td><b>{b}</b></td><td>{Y.vt(c)}</td><td>{d}</td></tr>" for a, b, c, d in rows)
    + "</table>", unsafe_allow_html=True)

# ---------------------------------------------------- worked examples
st.divider()
Y.band("Worked examples - the unused part of one card line, per year")
ex = [("Dormant $10,000 card", 10000, 0, cap["risk_weight_dormant_zero_balance"]),
      ("$10,000 line, $2,000 balance (revolver)", 10000, 2000, cap["risk_weight_non_transactor"]),
      ("$10,000 line, $2,000 balance (transactor)", 10000, 2000, cap["risk_weight_transactor"])]
cols = st.columns(3)
for col, (name, lim, bal, rw) in zip(cols, ex):
    e = X.worked_example(lim, bal, rw, cfg)
    col.markdown(f"**{name}**")
    col.markdown(
        f"- Unused line: {S.usd(e['ucl'])}\n"
        f"- Exposure on it: {S.usd(e['ucl'])} × {cap['ccf_unused_card_lines']:.0%} = **{S.usd(e['exposure_unused'])}**\n"
        f"- RWA: × {rw:.0%} = **{S.usd(e['rwa_unused'])}**\n"
        f"- Capital: × {cap['capital_ratio']:.1%} = ${e['capital_required_unused']:,.2f}\n"
        f"- Capital cost: × {cap['cost_of_equity']:.0%} = **${e['capital_cost_unused']:,.2f}** a year\n"
        f"- HQLA: {S.usd(e['ucl'])} × {liq['lcr_outflow_unused_card_lines']:.0%} = {S.usd(e['hqla'])}\n"
        f"- Liquidity cost: × {liq['negative_carry']:.2%} = **${e['liquidity_cost']:,.2f}** a year\n"
        f"- **Carrying cost: ${e['carrying_cost']:,.2f} a year**")

# ---------------------------------------------------- current rules comparison
f = S.frame()
sc = f[f["screened"]]
if show_cmp:
    st.divider()
    Y.band("Current US rules comparison - read-only, never the default")
    cur = X.current_rules(sc, cfg)
    comp = pd.DataFrame({
        "Working assumptions (March 2026 proposal adopted)": [sc["rwa"].sum(), sc["rwa_unused"].sum(), sc["capital_cost"].sum(),
                                                              sc["liquidity_cost"].sum(), float("nan")],
        "Current US rules": [cur["rwa_current_rules"].sum(), 0.0, cur["capital_cost_current_rules"].sum(),
                             cur["liquidity_cost_current_rules"].sum(), cur["slr_capital_required"].sum()],
    }, index=["RWA", "RWA from unused lines", "Capital cost a year", "Liquidity cost a year",
              "SLR capital (10% CCF, 3%; Category I-III)"])
    st.dataframe(comp.map(S.usd), width="stretch")
    st.caption("Current law: 0% CCF on unconditionally cancellable lines, 100% on drawn balances, no LCR outflow on "
               "cancellable lines. The comparison shows how much of the value depends on the assumptions.")

# ---------------------------------------------------- fairness
st.divider()
Y.band("Fair lending - four-fifths test by metro (geography proxy, not BISG)")
fa = S.fairness()
fails = {k: v for k, v in fa["summary"].items() if v["groups_failing"]}
if fails:
    st.markdown('<div class="flag"><b>Four-fifths failures - review before any pilot.</b><ul>' + "".join(
        f"<li>{k.replace('_', ' ').capitalize()}: <b>{v['groups_failing']}</b> of {v['groups_tested']} metros fail</li>"
        for k, v in fails.items()) + "</ul></div>", unsafe_allow_html=True)
names = {"module_decreases_and_closures": "Module decreases and closures", "ml_adverse_actions":
         "ML adverse actions (decrease, freeze)", "ml_increases": "ML increases"}
tabs = st.tabs([names[k] for k in names if k in fa])
for tab, k in zip(tabs, [k for k in names if k in fa]):
    with tab:
        df = fa[k].copy()
        st.dataframe(df, width="stretch", hide_index=True)
st.caption(fa["proxy_method"] + ". Selection rates are compared with the population rate; groups under 30 "
           "customers are not tested (the system's fairness module).")
with st.expander("The ML credit-limit model (second opinion only)"):
    st.markdown("\n".join(f"- {x}" for x in T.ml_rules_text()))
