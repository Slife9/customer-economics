import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import segments as SG  # noqa: E402

S.header("🧩 Where the cost sits")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)
order = cfg["segments"]["order"]
summ = SG.summary(f, cfg)
body = summ.drop(index="Total")
body.index = order                                   # summary() keeps the config order
seg_value = S.run("base")["segments"]["headline_value"]
top = body["total_unused_line_cost"].idxmax()

# 1. headline sentence
Y.headline(f"{S.seg_label(top)} carry the largest share of the cost: {R.short(body.loc[top, 'total_unused_line_cost'])} "
           f"of the {R.short(pb['cost'])} a year that unused lines cost on {pb['accounts']:,} loss-making, "
           "low-use accounts.")

# 2. cards: the problem (dominant) and the cost of unused lines
Y.cards([
    (S.term("screened"), f"{pb['accounts']:,}", f"{pb['accounts'] / max(pb['open'], 1):.1%} of {pb['open']:,} open "
     f"card accounts · {R.short(pb['ucl'])} of unused lines", Y.AMBER, S.define("screened")),
    (S.term("card_profit"), R.short(pb["card_profit"]), "a year on these cards", Y.RED, S.define("card_profit")),
    (S.term("carrying"), R.short(pb["carrying"]), "a year: capital + liquidity buffer", Y.BLUE, S.define("carrying")),
    (S.term("drawdown"), R.short(pb["drawdown"]), "a year: shown beside profit, not deducted", Y.RED,
     S.define("drawdown")),
], dominant=0)

# six compact segment cards
st.write("")
Y.band("The six groups (first matching rule wins)")
for row in (order[:3], order[3:]):
    for col, k in zip(st.columns(3), row):
        b = body.loc[k]
        col.markdown(Y.segment_card(
            S.seg_label(k), f"{int(b['accounts']):,} accounts ({b['share_of_screened']:.0%})",
            [(S.term("card_profit") if S.analyst() else "Annual loss", R.short(b["card_profit"])),
             (S.term("unused_cost"), R.short(b["total_unused_line_cost"])),
             ("Value of approved actions", R.signed_short(float(seg_value.get(k, 0.0))))],
            G.SEGMENT_ACTIONS[k]["plain_action"], Y.SEGMENT_COLORS[k]), unsafe_allow_html=True)
    st.write("")

# 3. one chart: holding cost vs expected drawdown loss by segment
names = [S.seg_label(k) for k in order]
fig = go.Figure()
for col, key, colour in [("carrying_cost", "carrying", Y.HOLDING), ("drawdown_el", "drawdown", Y.DRAWDOWN)]:
    fig.add_bar(y=names, x=body[col], orientation="h", name=S.term(key), marker=dict(color=colour),
                text=[R.short(v) for v in body[col]], textposition="outside",
                hovertemplate="%{y}<br>" + S.term(key) + ": %{x:$,.0f} a year<extra></extra>")
fig.update_layout(title="Cost of holding unused lines vs expected losses if they are drawn, per year",
                  barmode="group", height=430, margin=dict(t=50, b=10, l=10), bargap=0.25, bargroupgap=0.08,
                  xaxis=dict(title="USD per year", tickformat="$,.0f", range=Y.padded(list(body["drawdown_el"])
                                                                                     + list(body["carrying_cost"]), 0.18)),
                  yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, width="stretch")

# 4-5. what this means / what to do
dd_top = body["drawdown_el"].idxmax()
big = body["accounts"].idxmax()
c1, c2 = st.columns(2)
Y.means([
    f"{S.seg_label(big)} are the largest group: {int(body.loc[big, 'accounts']):,} accounts.",
    f"{S.seg_label(dd_top)} carry the most expected loss if their lines are drawn.",
    ("Expected losses outweigh holding costs overall: trimming risky lines matters most."
     if pb["drawdown"] > pb["carrying"] else "Holding costs outweigh expected losses overall."),
], where=c1)
Y.decide([
    f"Trim limits for {S.seg_label('sock_drawer')} and {S.seg_label('deteriorating')}.",
    f"Wake up {S.seg_label('dormant')}; right-size or close them only once approved (B6).",
    f"Leave {S.seg_label('transactors')}' limits alone; stop automatic increases instead.",
], where=c2)

# 6. details
st.write("")
tabs = ["Full table", "Rules and thresholds", "Screen sensitivity"] + (
    ["LEQ: account vs workbook (B2)"] if S.analyst() else [])
tab = st.tabs(tabs)
with tab[0]:
    if S.analyst():
        show = summ[["accounts", "share_of_screened", "ucl", "carrying_cost", "drawdown_el", "total_unused_line_cost",
                     "card_profit", "relationship_adjusted_profit", "card_profit_per_account"]].copy()
        fmt = {c: S.usd for c in show.columns if c not in ("accounts", "share_of_screened")}
        fmt["share_of_screened"] = S.pct
        fmt["accounts"] = lambda v: f"{v:,.0f}"
        show = show.apply(lambda col: col.map(fmt[col.name]))
        show.columns = ["Accounts", "Share", "Unused lines", "Carrying cost (capital + liquidity)",
                        "Expected drawdown loss", "Total unused-line cost", "Card profit under the assumed capital rules",
                        "Relationship-adjusted profit", "Card profit per account"]
        st.dataframe(show, width="stretch")
        S.md(f"{Y.vt('measured')} accounts, unused lines, card profit · {Y.vt('regulatory')}{Y.vt('business')} "
             f"carrying cost · {Y.vt('workbook')} drawdown loss (LEQ)", unsafe_allow_html=True)
    else:
        show = pd.DataFrame({"Group": [S.seg_label(k) for k in order] + ["Total"],
                             "Accounts": [f"{int(v):,}" for v in summ["accounts"]],
                             "Annual loss": summ["card_profit"].map(S.usd).values,
                             "Cost of holding": summ["carrying_cost"].map(S.usd).values,
                             "Expected losses": summ["drawdown_el"].map(S.usd).values})
        st.dataframe(show, width="stretch", hide_index=True)
with tab[1]:
    r, sc = cfg["segments"]["rules"], cfg["screen"]
    S.md(f"**In scope** when all of these hold: card profit below $0; average use below {sc['max_utilisation']:.0%} of "
         f"the line; at least ${sc['min_unused_usd']:,.0f} unused; open at least {sc['min_history_months']} months; "
         "open and not charged off; no recent fraud event. Protected customers (hardship, SCRA) get no action.")
    mapping = [
        (S.seg_label("deteriorating"), f"PD 12 Month ≥ {r['deteriorating']['pd_annual_min']:.0%}, or bureau score down "
         f"≥ {r['deteriorating']['score_drop_6m_min']} points in 6 months", "exact (Table8); score history synthetic (Table29)"),
        (S.seg_label("relationship"), f"non-card profit ≥ ${r['relationship']['noncard_profit_min_usd']:,.0f}, deposits ≥ "
         f"${r['relationship']['deposits_plus_investments_min_usd']:,.0f}, or Premier / Private Banking",
         "approximate (investments not in the data)"),
        (S.seg_label("dormant"), f"no transaction for ≥ {r['dormant']['inactive_months_min']} months and a $0 balance in "
         "every cycle", "exact; activation (Table30) synthetic"),
        (S.seg_label("sock_drawer"), f"active ≤ {r['sock_drawer']['active_months_max']} of 12 months and spend < "
         f"${r['sock_drawer']['spend_max_usd']:,.0f}", "exact"),
        (S.seg_label("transactors"), f"paid in full (or nothing due) ≥ {r['transactors']['paid_in_full_months_min']} of 12, "
         f"peak statement use < {r['transactors']['peak_utilisation_max']:.0%}, spend ≥ "
         f"${r['transactors']['spend_min_usd']:,.0f}", "exact"),
        (S.seg_label("unassigned"), "none of the above", ""),
    ]
    rules = pd.DataFrame(mapping, columns=["Group", "Rule", "Mapping to system data"])
    st.dataframe(rules if S.analyst() else rules[["Group", "Rule"]], width="stretch", hide_index=True)
    if S.analyst():
        S.cap("The segmentation transactor rule (≥ 10 of 12) is separate from the regulatory transactor test "
              "(12 of 12, no plan or promotional balance) that sets the 45% risk weight.")
    for k in order:
        a = G.SEGMENT_ACTIONS[k]
        with st.expander(S.seg_label(k)):
            S.md(f"**Why:** {a['why']}\n\n" + "\n".join(f"- {x}" for x in a["actions"]) + f"\n\n**Watch:** {a['watch']}")
with tab[2]:
    sens = SG.drawdown_sensitivity(f)
    S.md(f"Counting expected losses as part of the card's loss would bring **{sens['extra_accounts']:,}** more accounts "
         f"into scope ({sens['accounts_screened_toggle']:,} instead of {sens['accounts_screened_default']:,}; "
         f"{S.usd(-sens['extra_loss_after_drawdown'])} more loss after expected losses). Default: off "
         f"(currently {'on' if cfg['screen']['include_expected_drawdown_loss'] else 'off'}).")
if S.analyst():
    with tab[3]:
        sc = f[f["screened"]]
        base = sc["pd_used"] * sc["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"]) * sc["ucl"]
        cmp = pd.DataFrame({
            "Accounts": sc.groupby("rule_segment").size(),
            "Mean LEQ (account Behavioral CCF)": sc.groupby("rule_segment")["leq_measured"].mean(),
            "Workbook LEQ": sc.groupby("rule_segment")["leq_workbook"].mean(),
            "Drawdown loss - account LEQ": (base * sc["leq_measured"].fillna(sc["leq_workbook"])).groupby(sc["rule_segment"]).sum(),
            "Drawdown loss - workbook LEQ": (base * sc["leq_workbook"]).groupby(sc["rule_segment"]).sum(),
        }).reindex(order)
        cmp.loc["Total"] = [cmp["Accounts"].sum(), float("nan"), float("nan"),
                            cmp["Drawdown loss - account LEQ"].sum(), cmp["Drawdown loss - workbook LEQ"].sum()]
        cmp.index = [S.seg_label(k) for k in order] + ["Total"]
        st.dataframe(cmp.style.format({"Accounts": "{:,.0f}", "Mean LEQ (account Behavioral CCF)": "{:.3f}",
                                       "Workbook LEQ": "{:.3f}", "Drawdown loss - account LEQ": "${:,.0f}",
                                       "Drawdown loss - workbook LEQ": "${:,.0f}"}, na_rep=""), width="stretch")
        S.cap(f"Setting in use: drawdown_risk.leq_source = **{cfg['drawdown_risk']['leq_source']}** (change on What-if). "
              "The account Behavioral CCF is a generator parameter on this synthetic data (0.42, or 0.798 after a "
              "risk-deterioration limit event): see ISSUES_FOUND.md #16. Imputed PDs (B1) on screened accounts: "
              f"{int(sc['pd_imputed'].sum()):,}.")
S.caveat()
