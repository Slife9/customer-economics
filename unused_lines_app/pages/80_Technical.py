import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS  # noqa: E402
from engine.unused_lines import exposure as X, workbook as W  # noqa: E402

S.header("🛠️ Technical")
S.analyst_only()
cfg = S.cfg()
f = S.frame()
sc = f["screened"]

# ---------------------------------------------------- reconciliation (B4)
Y.band("Card profit: main engine vs this module (reconciliation)")
S.md("The module's card profit is **card profit under the assumed capital rules**: the main engine's card profit "
     "(`card_net`) with today's capital charge added back, the March 2026 proposal's capital cost and the liquidity "
     "buffer cost subtracted (and, with the workbook fixed-cost setting, the fixed-cost difference). Each step, to "
     "the cent:")
money = lambda v: f"{v + 0.0:,.2f}"  # noqa: E731  (+ 0.0: no "-0.00")
both = pd.DataFrame({"Accounts in scope (screened), USD a year": X.reconciliation(f, sc).set_index("step")["usd"],
                     "Every card account, USD a year": X.reconciliation(f).set_index("step")["usd"]})
st.dataframe(both.map(money), width="stretch")
by = pd.DataFrame({S.seg_label(k): X.reconciliation(f, sc & (f["rule_segment"] == k)).set_index("step")["usd"]
                   for k in cfg["segments"]["order"]})
st.markdown("**By group (screened accounts), USD a year**")
st.dataframe(by.map(lambda v: f"{v + 0.0:,.0f}"), width="stretch")

# ---------------------------------------------------- workbook reproduction
st.divider()
Y.band("Workbook-reproduction mode (the reference workbook's own formulas and inputs)")
d = W.dashboard(cfg)
ref = cfg["workbook"]["dashboard_reference"]
rep = pd.DataFrame({s: {"Change in fully loaded profit": d[s]["change_in_fully_loaded_profit"],
                        "Workbook Dashboard": ref[s]["change_in_fully_loaded_profit"],
                        "Accounts lost": d[s]["accounts_lost"],
                        "Capital released (one-time)": d[s]["capital_released"]} for s in SCENARIOS}).T
st.dataframe(rep.map(lambda v: f"{v:,.0f}"), width="stretch")
S.cap("Original 85% / 55% weights and the workbook's modelled loss, used for the ±1% test only. The system's "
      "results come from account data with the corrected rules.")
wb = X.workbook_baseline(cfg).loc["total"]
S.cap(f"Workbook baseline: RWA ${wb['rwa']:,.0f}; fully loaded profit ${wb['fully_loaded_profit']:,.0f}.")

# ---------------------------------------------------- value types
st.divider()
Y.band("Value types (analyst view)")
S.md(" ".join(Y.vt(k) for k in Y.VALUE_TYPE_LABELS), unsafe_allow_html=True)
S.md("- **Measured:** from the portfolio's own data (card profit, balances, PD, the account Behavioral CCF).\n"
     "- **Assumed (regulatory):** the March 2026 Basel III endgame proposal treated as adopted; the conservative "
     "LCR outflow.\n"
     "- **Assumed (business):** capital ratio, cost of equity, carry, fixed-cost basis - illustrative.\n"
     "- **Workbook estimate:** LEQ (workbook setting), lever shares, response rates from the Unused Line RWA "
     "Scenario Model.\n"
     "- **Derived:** computed from the above (card profit under the assumed capital rules, totals).")

# ---------------------------------------------------- calibration, methodology
st.divider()
Y.band("Calibration and methodology")
S.page_link("data", "Data & calibration: the calibration report against the reference workbook", "🧪")
S.md("\n".join(f"- **{t}:** `{p}`" for t, p in G.METHODOLOGY_LINKS))
S.cap("Assumptions file: engine/unused_lines/config/unused_line_assumptions.json · workbook inputs: "
      f"engine/unused_lines/config/workbook_model.json · assumptions sha256 {st.session_state.get('cfg_sha', '')[:12]}")
