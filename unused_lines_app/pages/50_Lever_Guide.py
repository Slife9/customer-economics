import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import levers as L  # noqa: E402

S.header("📖 Lever guide & regulation")
cfg = S.cfg()
S.cap(G.COMPLIANCE_NOTE)

Y.band("Levers - what they do, compliance and timing")
rows = []
for k, (what, example, comp) in G.LEVERS.items():
    t = cfg["timing"][k]
    status = ("pending approval (B6)" if L.pending(cfg, k) else
              "extra (assumption-based)" if k in L.EXTRA_LEVERS else "workbook lever")
    rows.append({"Lever": L.LEVER_LABELS[k], "Status": status, "What it does": what, "Example": example,
                 "Reason code": cfg["treatment"]["reason_by_lever"][k], "Compliance": comp,
                 "Starts": t["starts"], "Full value": t["full_value"], "Year-1 share": f"{t['year1_share']:.0%}"})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

Y.band("Notices and customer protections")
st.dataframe(pd.DataFrame(G.NOTICE_RULES, columns=["When", "Rule"]), width="stretch", hide_index=True)
sm = cfg["levers"]["system_mode"]
S.md(
    f"- **Line-cut rules:** the new line is at least max(${sm['floor_minimum_line_usd']:,}, balance × "
    f"{sm['floor_balance_multiple']}); a cut is at most {cfg['levers']['max_reduction_per_review']:.0%} of the line per "
    f"review and at least {sm['min_cut_share']:.0%} and ${sm['min_cut_usd']:,}, or there is no cut.\n"
    f"- **Closures** are inactivity closures only: inactive ≥ {sm['closure_min_inactive_months']} months and still "
    "inactive after the reactivation campaign.\n"
    "- **Reason codes:** " + ", ".join(cfg["treatment"]["reason_codes"]) + " - every action carries one.\n"
    "- **Never** an inactivity fee.\n"
    "- **Next step:** always a pilot with a holdout (default 10%, stratified by segment).")

Y.band("Value types used on every page")
S.md(" ".join(Y.vt(k) for k in Y.VALUE_TYPE_LABELS), unsafe_allow_html=True)
S.md("- **Measured:** from the portfolio's own data (card profit, balances, PD).\n"
            "- **Assumed (regulatory):** the March 2026 Basel III endgame proposal treated as adopted; the "
            "conservative LCR outflow.\n"
            "- **Assumed (business):** capital ratio, cost of equity, carry - illustrative.\n"
            "- **Workbook estimate:** LEQ, lever shares, response rates from the Unused Line RWA Scenario Model.")
