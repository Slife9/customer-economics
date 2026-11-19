import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import strategies as ST  # noqa: E402

S.header("🧭 The four strategies")
cfg = S.cfg()
st_ = S.run("base")["strategies"]
tb = st_["table"]
defs = cfg["strategies"]["definitions"]
order = cfg["strategies"]["order"]


def main_status(key: str) -> str:
    s = tb.loc[tb["strategy"] == key, "status"]
    return "awaiting_decision" if (s == "awaiting_decision").any() else s.iloc[0]


# 1. headline sentence
labels = [f"Strategy {defs[k]['number']} {st_['strategies'][k]['status_label'].lower()}" for k in order]
Y.headline("Four strategies, each matched to a customer problem: " + "; ".join(labels) + ".")

# 2. one card per strategy (what, who, why, status, value)
for row in (order[:2], order[2:]):
    cols = st.columns(2)
    for col, key in zip(cols, row):
        d, v, txt = defs[key], st_["strategies"][key], G.strategy_text(key, cfg)
        extra = Y.journey([(s["name"], f" {R.signed_short(v['components'][s['name']])} a year",
                            ST.step_status(cfg, d, s)) for s in d["steps"]]) if key == "use_it_or_lose_it" else ""
        value = R.signed_short(v["headline_value"]) + " a year"
        Y.strategy_card(d["number"], d["name"], main_status(key), v["status_label"], value, txt["what"], txt["who"],
                        txt["why"], extra, where=col)
    st.write("")

# the warning step
S.md("**The 90-day warning (Strategy 3)** - what we assume customers do when warned "
     "(*assumption; to be tested in the pilot*):")
wt = G.strategy_text("use_it_or_lose_it", cfg)["warning"]
st.dataframe(pd.DataFrame([(a, f"{b:.0%}") for a, b in wt], columns=["Response", "Share of customers warned"]),
             width="stretch", hide_index=True)
S.cap(f"A customer who responds to the Invite is not warned. Each letter costs "
      f"${cfg['warning']['letter_cost_usd']:,.2f}; the warning never carries a fee. Letters in the Base case: "
      f"{st_['warning_letters']:,.0f}.")

# what we deliberately don't do
Y.not_done(cfg["strategies"]["not_done"])

# details
with st.expander("Safeguards on every cut"):
    S.md("\n".join(f"- **{a}:** {b}" for a, b in G.safeguards(cfg)[:2]))
with st.expander("Points to settle"):
    S.md("- Whether one small purchase resets the clock (today's setting: "
         + ("one transaction" if cfg["warning"]["min_use_to_reset"] == "one_transaction"
            else f"at least ${cfg['warning']['min_spend_to_reset_usd']:,.0f} of spend") + ").\n"
         "- The warning wording, which compliance must approve.\n"
         "- The response shares to the warning, measured in the pilot.")
if S.analyst():
    with st.expander("Analyst: the levers inside each strategy"):
        show = tb[["number", "strategy_name", "step_name", "status_label", "headline_value", "card_profit_change",
                   "drawdown_reduction", "customers", "accounts_leaving", "unused_removed", "capital_released",
                   "letters"]].copy()
        st.dataframe(show.style.format({c: "{:,.0f}" for c in show.columns[4:]}), width="stretch", hide_index=True)
        lv = pd.DataFrame([(defs[k]["number"], s["name"], ", ".join(s["levers"]),
                            ", ".join(S.seg_label(x) for x in (s["segments"] or [])) or "any selected card")
                           for k in order for s in defs[k]["steps"]],
                          columns=["Strategy", "Step", "Levers", "Groups"])
        st.dataframe(lv, width="stretch", hide_index=True)
        S.cap("Pay-in-full right-sizing (lever transactor_rightsizing) is valued on the Levers page and excluded by "
              "policy; it is in no strategy.")
S.caveat()
