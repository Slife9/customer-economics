import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import segments as SG  # noqa: E402

S.header("📉 The problem")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)

# 1. headline sentence
Y.headline(f"{pb['accounts']:,} cards ({pb['share']:.1%} of open cards) lose money while holding large unused "
           f"limits: {R.short(pb['card_profit'])} a year in card losses and {R.short(pb['ucl'])} of unused credit.")

# 2. cards
Y.cards([
    (S.term("screened"), f"{pb['accounts']:,}", f"{pb['share']:.1%} of {pb['open']:,} open cards", Y.AMBER,
     S.define("screened")),
    (S.term("card_profit"), R.short(pb["card_profit"]), f"a year ({S.usd(pb['per_card'])} per card)", Y.RED,
     S.define("card_profit")),
    (S.term("unused"), R.short(pb["ucl"]), f"{S.usd(pb['ucl_per_card'])} per card that could be drawn at any time",
     Y.BLUE, S.define("unused")),
    ("Share of the limit used", f"about {pb['used_at_statement']:.0%}", "at statement date, before the customer's "
     "payment", Y.GREY, "Average over 12 months of the statement balance divided by the limit."),
], dominant=0)

# 3. one chart: used vs unused at statement date
st.write("")
c1, c2 = st.columns([3, 2])
used = pb["statement_balance"]
fig = go.Figure(go.Pie(labels=["Used (statement balance)", "Unused"], values=[used, max(pb["limits"] - used, 0.0)],
                       hole=0.62, sort=False, direction="clockwise",
                       marker=dict(colors=[Y.NAVY, "#cbd5e1"], line=dict(color="#fff", width=2)), textinfo="none",
                       hovertemplate="%{label}: %{value:$,.0f} (%{percent:.0%})<extra></extra>"))
fig.update_layout(height=360, margin=dict(t=10, b=10, l=10, r=10),
                  legend=dict(orientation="h", yanchor="top", y=-0.02, x=0.5, xanchor="center"),
                  annotations=[dict(text=f"<b>{1 - pb['used_at_statement']:.0%}</b><br>unused<br>"
                                         f"<span style='font-size:14px'>{pb['used_at_statement']:.0%} used</span>",
                                    x=0.5, y=0.5, font=dict(size=22), showarrow=False)])
with c1:
    Y.band("How much of their limits these cards use (statement date, 12-month average)")
    st.plotly_chart(fig, width="stretch")
with c2:
    Y.band("How the cards were selected: all six tests")
    S.md("\n".join(f"{i}. {text}" for i, (_, text) in enumerate(G.selection_tests(cfg), 1)))
S.md(f"A credit card is a promise: the customer can borrow up to the limit at any time, without asking. Most customers "
     f"use only part of it. The unused part is not free: the bank holds capital and liquid assets against it, and "
     f"customers in financial trouble often draw it just before defaulting. About {pb['no_statement_balance']:.0%} of "
     "these cards carried no statement balance all year.")

# details
with st.expander("The figures in a table"):
    st.dataframe(pd.DataFrame([
        ("Cards selected", f"{pb['accounts']:,} of {pb['open']:,} open cards ({pb['share']:.1%})"),
        ("Card profit on these cards", f"{S.usd(pb['card_profit'])} a year ({S.usd(pb['per_card'])} per card)"),
        ("Unused credit", f"{R.short(pb['ucl'])} ({S.usd(pb['ucl_per_card'])} per card)"),
        ("Share of the limit used at statement date", f"about {pb['used_at_statement']:.0%} "
         f"({R.short(pb['statement_balance'])} of {R.short(pb['limits'])} in limits)"),
        ("Cards with no statement balance all year", f"about {pb['no_statement_balance']:.0%}"),
    ], columns=["Measure", "Value"]), width="stretch", hide_index=True)
    basis = cfg["balance_basis"]
    S.cap("Usage is the 12-month average at statement date (before the customer's payment). Unused credit is the "
          "12-month average of limit minus the balance outstanding during the month (the average of the statement and "
          "after-payment balances)." if basis["cost"] == "midpoint" else
          "Unused credit uses the balance after the customer's monthly payment.")
with st.expander("How many open cards pass each test"):
    st.dataframe(pd.DataFrame(R.funnel(f, cfg), columns=["Test (cumulative)", "Open cards still in"]).assign(
        **{"Open cards still in": lambda d: d["Open cards still in"].map(lambda v: f"{v:,}")}),
        width="stretch", hide_index=True)
if S.analyst():
    with st.expander("Analyst: screen settings and sensitivity"):
        sens = SG.drawdown_sensitivity(f)
        S.md(f"- Utilisation basis: `balance_basis.screen = {cfg['balance_basis']['screen']}`; cost basis "
             f"`balance_basis.cost = {cfg['balance_basis']['cost']}`; lever values "
             f"`balance_basis.lever_values = {cfg['balance_basis']['lever_values']}`.\n"
             f"- Counting expected drawdown loss in the screen would add **{sens['extra_accounts']:,}** cards "
             f"({S.usd(-sens['extra_loss_after_drawdown'])} more loss after expected losses); default off.")
        st.dataframe(pd.DataFrame([(SG.SCREEN_LABELS[k].format(**cfg["screen"]), int((~f[f"met:{k}"]).sum()))
                                   for k in SG.SCREEN_LABELS], columns=["Criterion", "Accounts failing it"]),
                     width="stretch", hide_index=True)
S.caveat()
