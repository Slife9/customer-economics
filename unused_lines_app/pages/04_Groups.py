import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import segments as SG  # noqa: E402

S.header("🧩 Customers and where the cost sits")
cfg = S.cfg()
f = S.frame()
pb = R.problem(f)
order = cfg["segments"]["order"]
gt = R.group_table(f, cfg)
top = gt["total"].idxmax()
big = gt["cards"].idxmax()

# 1. headline sentence
Y.headline(f"The biggest group is not where the cost and risk sit: {S.seg_label(top).lower()} are "
           f"{gt.loc[top, 'share']:.0%} of the cards but carry the largest cost, {R.short(gt.loc[top, 'total'])} a year "
           f"and {gt.loc[top, 'drawdown'] / max(pb['drawdown'], 1):.0%} of all expected drawdown loss.")

# 2. the six groups: counts, rule, how cards qualify
S.cap(f"The {pb['accounts']:,} cards fall into six groups, each defined by a rule. A card goes into the first group "
      f"whose rule it meets, in the order below. {S.seg_label(big)} are the largest group ({gt.loc[big, 'share']:.0%}).")
groups = pd.DataFrame({
    "#": range(1, len(order) + 1),
    "Group": [S.seg_label(k) for k in order],
    "Cards": [f"{int(gt.loc[k, 'cards']):,}" for k in order],
    "Share": [f"{gt.loc[k, 'share']:.0%}" for k in order],
    "Rule a card must meet": [G.group_rule(k, cfg) for k in order],
})
st.dataframe(groups, width="stretch", hide_index=True,
             column_config={"Rule a card must meet": st.column_config.TextColumn(width="large")})

# 3. one chart: cost to hold vs expected drawdown loss, stacked
by = gt.sort_values("total", ascending=True)
names = [S.seg_label(k) for k in by.index]
fig = go.Figure()
for col, label, colour in [("carrying", "Cost to hold (capital + liquidity)", Y.HOLDING),
                           ("drawdown", "Expected drawdown loss", Y.DRAWDOWN)]:
    fig.add_bar(y=names, x=by[col], orientation="h", name=label,
                marker=dict(color=colour, line=dict(color="#ffffff", width=2)),
                hovertemplate="%{y}<br>" + label + ": %{x:$,.0f} a year<extra></extra>")
fig.add_scatter(y=names, x=by["total"], mode="text", text=[R.short(v) for v in by["total"]], textposition="middle right",
                showlegend=False, hoverinfo="skip")
fig.update_layout(title="Total cost of unused lines by group, per year", barmode="stack", height=400,
                  margin=dict(t=50, b=10, l=10), xaxis=dict(title="USD per year", tickformat="$,.0f",
                                                           range=[0, float(by["total"].max()) * 1.18]),
                  legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
st.plotly_chart(fig, width="stretch")

# 4. the four takeaways
rel, tr, dor = gt.loc["relationship"], gt.loc["transactors"], gt.loc["dormant"]
Y.means([
    f"{S.seg_label('deteriorating')}: small group, biggest priority - their chance of drawing the line before default "
    "is high.",
    f"{S.seg_label('dormant')}: {dor['ucl'] / max(pb['ucl'], 1):.0%} of the unused credit at modest risk, so much of "
    "their cost is simply holding the lines.",
    f"{S.seg_label('relationship')}: the biggest card loss ({R.short(rel['card_profit'])}), but not caused by unused "
    "credit; their other products more than make up for it, so they get a light touch.",
    f"{S.seg_label('transactors')}: plenty of unused credit at little risk; cutting it saves little and risks "
    "upsetting good customers.",
], )

# details
with st.expander("How cards qualify in practice"):
    for k in order:
        S.md(f"- **{S.seg_label(k)}:** {R.qualify(f, k, cfg)}")
    S.cap("Investments are not in the data, so the relationship deposit rule uses deposits only.")
with st.expander("Full figures by group"):
    tab = pd.DataFrame({
        "Cards": gt["cards"].map(lambda v: f"{v:,.0f}"),
        "Unused credit": gt["ucl"].map(lambda v: f"${v / 1e6:,.1f}M"),
        "Cost to hold": gt["carrying"].map(lambda v: f"${v / 1e6:,.2f}M"),
        "Expected drawdown loss": gt["drawdown"].map(lambda v: f"${v / 1e6:,.2f}M"),
        "Total cost of unused lines": gt["total"].map(lambda v: f"${v / 1e6:,.2f}M"),
        "Card profit": gt["card_profit"].map(lambda v: R.short(v)),
    })
    tab.index = [S.seg_label(k) for k in order]
    tot = gt[["cards", "ucl", "carrying", "drawdown", "total", "card_profit"]].sum()
    tab.loc["Total"] = [f"{tot['cards']:,.0f}", f"${tot['ucl'] / 1e6:,.1f}M", f"${tot['carrying'] / 1e6:,.2f}M",
                        f"${tot['drawdown'] / 1e6:,.2f}M", f"${tot['total'] / 1e6:,.2f}M", R.short(tot["card_profit"])]
    st.dataframe(tab, width="stretch")
if S.analyst():
    with st.expander("Analyst: segment summary, rule mapping and the LEQ comparison"):
        summ = SG.summary(f, cfg)
        st.dataframe(summ.style.format("{:,.2f}"), width="stretch")
        sc = f[f["screened"]]
        base = sc["pd_used"] * sc["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"]) * sc["ucl"]
        cmp = pd.DataFrame({
            "Mean LEQ (account Behavioral CCF)": sc.groupby("rule_segment")["leq_measured"].mean(),
            "Workbook LEQ": sc.groupby("rule_segment")["leq_workbook"].mean(),
            "Drawdown loss - account LEQ": (base * sc["leq_measured"].fillna(sc["leq_workbook"])).groupby(sc["rule_segment"]).sum(),
            "Drawdown loss - workbook LEQ": (base * sc["leq_workbook"]).groupby(sc["rule_segment"]).sum(),
        }).reindex(order)
        cmp.index = [S.seg_label(k) for k in order]
        st.dataframe(cmp.style.format("{:,.3f}", subset=cmp.columns[:2]).format("${:,.0f}", subset=cmp.columns[2:]),
                     width="stretch")
        S.cap(f"LEQ source in use: `{cfg['drawdown_risk']['leq_source']}`. The account Behavioral CCF is a generator "
              "parameter on this synthetic data (0.42, or 0.798 after a risk-deterioration limit event): "
              "ISSUES_FOUND.md #16. The segmentation transactor rule (10 of 12) is separate from the regulatory "
              "transactor test (12 of 12) that sets the 45% risk weight.")
S.caveat()
