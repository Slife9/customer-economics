import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import segments as SG  # noqa: E402

S.header("🧩 Segments")
cfg = S.cfg()
f = S.frame()
r, sc = cfg["segments"]["rules"], cfg["screen"]

# ---------------------------------------------------- screen and rules
Y.band("The screen (system mode)")
S.md(
    f"- Card profit below $0: measured credit cost, the old capital charge **replaced** by the new one, the new "
    f"liquidity cost subtracted; expected drawdown loss **beside** it (toggle on **Levers & assumptions**: currently "
    f"**{'on' if sc['include_expected_drawdown_loss'] else 'off'}**)\n"
    f"- Average utilisation below {sc['max_utilisation']:.0%}; unused line at least ${sc['min_unused_usd']:,.0f}\n"
    f"- Open at least {sc['min_history_months']} months; open and not charged off\n"
    f"- No fraud-compromise card event in the last 2 cycles (fraud-block proxy - approximate)")
Y.band("Segments, in priority order (first match wins)")
mapping = [
    ("1", "Credit-Deteriorating", f"PD 12 Month ≥ {r['deteriorating']['pd_annual_min']:.0%}", "exact (Table8)"),
    ("", "", f"or bureau score down ≥ {r['deteriorating']['score_drop_6m_min']} points in 6 months",
     "new data (Table29, synthetic; partly correlated with PD by construction)"),
    ("2", "Relationship / Premium", f"non-card profit ≥ ${r['relationship']['noncard_profit_min_usd']:,.0f}", "exact"),
    ("", "", f"or deposits ≥ ${r['relationship']['deposits_plus_investments_min_usd']:,.0f}",
     "approximate (investments not in the data)"),
    ("", "", "or Segment Premier / Private Banking", "approximate (premium proxy)"),
    ("3", "Dormant", f"no transaction for ≥ {r['dormant']['inactive_months_min']} months and a $0 balance in every cycle",
     "exact; confirmation signals: activation (Table30, synthetic), reissue (Table3), digital sessions (Table12)"),
    ("4", "Sock-Drawer", f"active ≤ {r['sock_drawer']['active_months_max']} of 12 months and spend < "
     f"${r['sock_drawer']['spend_max_usd']:,.0f}", "exact"),
    ("5", "Low-Utilization Transactors", f"paid in full (or nothing due) ≥ {r['transactors']['paid_in_full_months_min']} "
     f"of 12, peak statement utilisation < {r['transactors']['peak_utilisation_max']:.0%}, spend ≥ "
     f"${r['transactors']['spend_min_usd']:,.0f}", "exact (statement balance = ending balance + payment)"),
    ("6", "Unassigned", "none of the above - no lever; its economics are shown", ""),
]
st.dataframe(pd.DataFrame(mapping, columns=["#", "Segment", "Rule", "Mapping to system data"]),
             width="stretch", hide_index=True)
S.cap("The segmentation transactor rule (≥ 10 of 12) is separate from the **regulatory transactor test** "
           "(12 of 12, no plan or promotional balance) that sets the 45% risk weight.")

# ---------------------------------------------------- economics
st.divider()
Y.band("Counts and economics by segment, per year")
summ = SG.summary(f, cfg)
show = summ[["accounts", "share_of_screened", "ucl", "carrying_cost", "drawdown_el", "total_unused_line_cost",
             "card_profit", "relationship_adjusted_profit", "card_profit_per_account"]].copy()
fmt = {c: S.usd for c in show.columns if c not in ("accounts", "share_of_screened")}
fmt["share_of_screened"] = S.pct
fmt["accounts"] = lambda v: f"{v:,.0f}"
show = show.apply(lambda col: col.map(fmt[col.name]))
show.columns = ["Accounts", "Share", "Unused lines", "Carrying cost (capital + liquidity)", "Expected drawdown loss",
                "Total unused-line cost", "Card profit", "Relationship-adjusted profit", "Card profit per account"]
st.dataframe(show, width="stretch")
S.md(f"{Y.vt('measured')} accounts, unused lines, card profit · {Y.vt('regulatory')}{Y.vt('business')} "
            f"carrying cost · {Y.vt('workbook')} drawdown loss (LEQ)", unsafe_allow_html=True)
sens = SG.drawdown_sensitivity(f)
S.cap(f"Screen including expected drawdown loss: {sens['accounts_screened_toggle']:,} accounts instead of "
           f"{sens['accounts_screened_default']:,} (+{sens['extra_accounts']:,}; "
           f"{S.usd(-sens['extra_loss_after_drawdown'])} more loss after drawdown).")

body = summ.drop(index="Total")
wb = cfg["workbook"]["segments"]
n_wb = sum(v["accounts"] for v in wb.values())
keys = cfg["segments"]["order"]
ref = [wb[k]["accounts"] / n_wb if k in wb else 0.0 for k in keys]
fig = go.Figure()
fig.add_bar(x=body.index, y=body["share_of_screened"], name="This dataset", marker_color=Y.BLUE,
            text=[S.pct(v) for v in body["share_of_screened"]], textposition="outside")
fig.add_bar(x=body.index, y=ref, name="Reference workbook", marker_color=Y.GREY,
            text=[S.pct(v) for v in ref], textposition="outside")
fig.update_layout(title="Share of the screened population", barmode="group", height=430, yaxis=dict(tickformat=".0%"),
                  margin=dict(t=60, b=20), legend=dict(orientation="h", y=-0.25))
st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------- what to do
st.divider()
Y.band("What each segment is, and the actions the workbook suggests")
for k in keys:
    a = G.SEGMENT_ACTIONS[k]
    with st.expander(S.seg_label(k)):
        S.md(f"**Why:** {a['why']}\n\n" + "\n".join(f"- {x}" for x in a["actions"])
                    + f"\n\n**Watch:** {a['watch']}")
