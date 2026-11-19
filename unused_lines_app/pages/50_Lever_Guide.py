import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import levers as L, strategies as ST  # noqa: E402

S.header("📖 Levers & lever guide")
S.analyst_only()
cfg = S.cfg()
S.cap(G.COMPLIANCE_NOTE)
defs = cfg["strategies"]["definitions"]
in_strategy = {}
for k in cfg["strategies"]["order"]:
    for s in defs[k]["steps"]:
        for lv in s["levers"]:
            in_strategy.setdefault(lv, []).append(f"{defs[k]['number']} ({s['name']})")

Y.band("Every lever, valued on its own (Base) - the strategies are built from these")
run = S.run("base")
lt = run["levers"]
key = {v: k for k, v in L.LEVER_LABELS.items()}
st.dataframe(pd.DataFrame({
    "Strategy": ["; ".join(in_strategy.get(key[i], ["none (excluded by policy)"])) for i in lt.index],
    "Status": lt["status"], "Accounts targeted": lt["accounts_targeted"].map(lambda v: f"{v:,.0f}"),
    "Annual value": lt["headline_value"].map(S.signed), "Δ card profit": lt["card_profit_change"].map(S.signed),
    "Δ drawdown loss": lt["drawdown_change"].map(S.signed), "Accounts leaving": lt["accounts_leaving"].map(lambda v: f"{v:,.0f}"),
    "Unused removed": lt["unused_removed"].map(S.usd), "Capital released (one-time)": lt["capital_released"].map(S.usd),
}, index=lt.index), width="stretch")
S.cap("Stand-alone lever values, without the 90-day warning. The engagement campaign serves two strategies: unused "
      "cards (Strategy 3's Invite) and everyone else (Strategy 2). Strategy values with the warning are on the "
      "strategies and value pages.")

Y.band("Levers - what they do, compliance and timing")
rows = []
for k, (what, example, comp) in G.LEVERS.items():
    t = cfg["timing"][k]
    status = ("pending approval (B6)" if L.pending(cfg, k) else "excluded by policy" if L.excluded(cfg, k) else
              "extra (assumption-based)" if k in L.EXTRA_LEVERS else "workbook lever")
    code = cfg["treatment"]["reason_by_lever"][k]
    rows.append({"Lever": L.LEVER_LABELS[k], "Strategy": "; ".join(in_strategy.get(k, ["none"])),
                 "Plain action": G.LEVER_PLAIN[k], "Status": status, "What it does": what,
                 "Example": example, "Reason code": code,
                 "Adverse-action notice": "yes" if cfg["treatment"]["reason_codes"][code]["adverse_action_notice"] else "no",
                 "Compliance": comp, "Starts": t["starts"], "Full value": t["full_value"],
                 "Year-1 share": f"{t['year1_share']:.0%}"})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

Y.band("Reason codes and their notice rules")
rc = cfg["treatment"]["reason_codes"]
st.dataframe(pd.DataFrame([(k, v["action"], v["notice"], "yes" if v["adverse_action_notice"] else "no",
                            "yes" if v["fcra_check"] else "no", v["compliance_flag"]) for k, v in rc.items()],
                          columns=["Reason code", "Action", "Notice", "Adverse-action notice", "FCRA check",
                                   "Compliance flag"]), width="stretch", hide_index=True)

Y.band("Rules and customer safeguards")
st.dataframe(pd.DataFrame(G.RULES, columns=["Action", "Requirement", "Reference"]), width="stretch", hide_index=True)
S.md("\n".join(f"- **{a}:** {b}" for a, b in G.safeguards(cfg)) + "\n"
     "- **Reason codes:** " + ", ".join(rc) + f" - every action carries one; OTHER stays below "
     f"{cfg['treatment']['other_max_share_of_actions']:.0%} of actions.\n"
     f"- **Next step:** always a pilot with a holdout ({cfg['treatment']['pilot']['holdout_share']:.0%}, stratified by group).")
