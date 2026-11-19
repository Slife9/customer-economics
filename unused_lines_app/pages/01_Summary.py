import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402

S.header("🏠 Executive summary")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)
st_ = S.run("base")["strategies"]
ap = st_["approved_combined"]
stv = S.stress("base")
fa = S.fairness()

# 1. headline sentence (the report's summary)
Y.headline(f"{pb['share']:.0%} of open cards ({pb['accounts']:,} of {pb['open']:,}) lose money while holding "
           f"{R.short(pb['ucl'])} of unused credit that costs about {R.short(pb['cost'])} a year; four strategies could "
           f"deliver up to about {R.short(st_['total_potential'])} a year, {R.short(ap['headline_value'])} of it already "
           "approved.")

# 2. four cards
cols = Y.cards([
    ("The problem", f"{pb['accounts']:,} cards", f"lose {R.short(-pb['card_profit'])} a year "
     f"({R.short(pb['per_card'])} each) and use about {pb['used_at_statement']:.0%} of their limits at statement date",
     Y.AMBER, S.define("screened")),
    ("The cost of unused credit", R.short(pb["cost"]),
     f"a year: {R.short(pb['carrying'])} to hold + {R.short(pb['drawdown'])} expected drawdown loss", Y.RED,
     S.define("unused_cost")),
    ("Approved now", R.signed_short(ap["headline_value"]), "a year: Strategies 1 and 2 and the Invite, together",
     Y.GREEN, S.define("headline")),
    ("Total potential", R.signed_short(st_["total_potential"]),
     f"a year: + {R.short(st_['proposed'])} proposed + {R.short(st_['awaiting_decision'])} awaiting a decision",
     Y.BLUE, "Approved + proposed (Strategy 4) + awaiting a decision (Strategy 3's actions)."),
], dominant=2)
for col, (u, label) in zip(cols, [("problem", "The problem"), ("cost", "How unused credit costs money"),
                                  ("value", "What they are worth"), ("value", "What they are worth")]):
    S.page_link(u, label, "➡️", where=col)

# 3. the four strategies with status and value
st.write("")
Y.band("The four strategies (Base case, each on its own)")
rows = R.strategy_rows(st_)
tb = st_["table"]
items = []
for r in rows.itertuples():
    status = tb.loc[tb["strategy"] == r.key, "status"]
    sk = "awaiting_decision" if (status == "awaiting_decision").any() else status.iloc[0]
    items.append((r.number, r.name, sk, r.status, R.signed_short(r.value)))
Y.strategy_list(items)
S.cap(R.mix_sentence(st_) + " Strategies 1 and 2 overlap, so the stand-alone values "
      f"do not add up to the approved {R.short(ap['headline_value'])}. Capital freed "
      f"({S.usd(ap['capital_released'])}, one time) is never added to the annual value.")
S.page_link("strategies", "The four strategies", "🧭")

# status tiles
Y.band("Status")
Y.tiles([R.fairness_tile(fa), R.robustness_tile(stv), R.rules_tile()])
st.write("")

# 4. what is needed
hold = cfg["treatment"]["pilot"]["holdout_share"]
Y.decide([p.format(holdout=hold) for p in G.WHAT_IS_NEEDED], title="What is needed")
S.cap("All figures come from a synthetic stress book of 100,000 customers and assume the March 2026 Basel III "
      "endgame proposal is adopted; they are illustrative, not a forecast for any real bank.")

with st.expander("Key terms"):
    st.dataframe(pd.DataFrame(G.KEY_TERMS, columns=["Term", "Meaning"]), width="stretch", hide_index=True)
if S.analyst():
    with st.expander("Analyst: the approved value in detail"):
        S.md(f"- Approved combined (Base): {S.signed(ap['headline_value'])} = change in card profit "
             f"{S.signed(ap['card_profit_change'])} + reduction in expected drawdown loss "
             f"{S.signed(ap['drawdown_reduction'])}; relationship-adjusted {S.signed(ap['relationship_adjusted_change'])}.\n"
             f"- Proposed {S.signed(st_['proposed'])}; awaiting decision {S.signed(st_['awaiting_decision'])}; "
             f"warning letters {st_['warning_letters']:,.0f}.")
        st.dataframe(rows[["number", "name", "status", "value", "components"]], width="stretch", hide_index=True)
S.caveat()
