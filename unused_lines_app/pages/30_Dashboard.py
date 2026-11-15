import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS  # noqa: E402
from engine.unused_lines import levers as L, treatment as T, workbook as W  # noqa: E402

S.header("📊 Scenario dashboard")
cfg = S.cfg()
f = S.frame()
c1, c2 = st.columns([2, 3])
scn = c1.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize, horizontal=True)
st.session_state["scenario"] = scn
mult = c2.select_slider("Stress multiplier (customer response)", options=cfg["stress_test"]["multipliers"], value=1.0,
                        help="Raises attrition, spend loss and PD uplift and lowers response rates.")
r = S.run(scn, mult)
s = r["summary"]
h = s["workbook_levers_headline"]

Y.cards([
    ("Annual value (headline)", S.signed(h["headline_value"]),
     f"card profit {S.signed(h['card_profit_change'])} + avoided drawdown loss {S.signed(-h['drawdown_change'])}", Y.GREEN),
    ("Relationship-adjusted change", S.signed(h["relationship_adjusted_change"]), "includes relationship profit lost "
     "with leavers", Y.BLUE),
    ("RWA change", S.signed(h["rwa_change"]), f"unused lines removed {S.usd(h['unused_removed'])}", Y.GREY),
    ("Capital released - one-time", S.usd(s["capital_released_one_time"]),
     "<b>shown separately; never added to annual values</b>", Y.BLUE),
])

# ---------------------------------------------------- by lever
st.divider()
Y.band("By lever - full annual value and year 1")
tt = T.timing_table(r["levers"], cfg)
lt = r["levers"].join(tt[["year1_share", "year1_value", "starts", "full_value_when"]])
show = pd.DataFrame({
    "Group": lt["group"], "Status": lt["status"],
    "Accounts targeted": lt["accounts_targeted"].map(lambda v: f"{v:,.0f}"),
    "Accounts leaving": lt["accounts_leaving"].map(lambda v: f"{v:,.0f}"),
    "Unused removed": lt["unused_removed"].map(S.usd),
    "Δ card profit": lt["card_profit_change"].map(S.signed),
    "Δ drawdown loss": lt["drawdown_change"].map(S.signed),
    "Full annual value": lt["headline_value"].map(S.signed),
    "Year-1 value": lt["year1_value"].map(S.signed),
    "Capital released (one-time)": lt["capital_released"].map(S.usd),
}, index=lt.index)
st.dataframe(show, width="stretch")


def subtotal(mask):
    x = lt[mask]
    return (x["headline_value"].astype(float).sum(), x["year1_value"].astype(float).sum())


wbk = (lt["group"] == "workbook") & (lt["status"] == "headline")
ext = (lt["group"] != "workbook") & (lt["status"] == "headline")
pend = lt["status"] == "pending approval"
st.markdown(
    f"- **Workbook levers (headline):** full {S.signed(subtotal(wbk)[0])} · year 1 {S.signed(subtotal(wbk)[1])} "
    f"(combined with interactions: {S.signed(h['headline_value'])})\n"
    f"- **Extra levers (assumption-based; not in the reference workbook):** full {S.signed(subtotal(ext)[0])} · "
    f"year 1 {S.signed(subtotal(ext)[1])}\n"
    f"- **Pending approval (B6):** full {S.signed(subtotal(pend)[0])} · year 1 {S.signed(subtotal(pend)[1])}")
st.caption("Value by type for the headline: " + ", ".join(
    f"{k.replace('_', ' ')} {S.signed(h[k])}" for k in L.VALUE_TYPES) + ". Transactor right-sizing is valued to "
    "show its effect and is never recommended.")

# ---------------------------------------------------- by segment
st.divider()
Y.band("By segment - combined headline levers")
sg = r["segments"]
seg = pd.DataFrame({
    "Accounts leaving": sg["accounts_leaving"].map(lambda v: f"{v:,.1f}"),
    "Unused removed": sg["unused_removed"].map(S.usd),
    "Carrying cost before": sg["carrying_before"].map(S.usd), "Carrying cost after": sg["carrying_after"].map(S.usd),
    "Drawdown loss before": sg["drawdown_before"].map(S.usd), "Drawdown loss after": sg["drawdown_after"].map(S.usd),
    "Δ card profit": sg["card_profit_change"].map(S.signed),
    "Δ relationship-adjusted": sg["relationship_adjusted_change"].map(S.signed),
    "Annual value": sg["headline_value"].map(S.signed),
    "Capital released (one-time)": sg["capital_released"].map(S.usd),
}, index=[S.seg_label(i) if i != "total" else "Total" for i in sg.index])
st.dataframe(seg, width="stretch")

# ---------------------------------------------------- stress
st.divider()
Y.band("Stress test - Base scenario")
stv = L.stress(f, cfg, "base")
g = stv.attrs["go_no_go"]
fig = go.Figure()
fig.add_bar(x=[f"{m}x" for m in stv.index], y=stv["wb_headline_value"], name="Annual value (headline)",
            marker_color=[Y.GREEN if v > 0 else Y.RED for v in stv["wb_headline_value"]],
            text=[S.signed(v) for v in stv["wb_headline_value"]], textposition="outside")
fig.add_scatter(x=[f"{m}x" for m in stv.index], y=stv["wb_card_profit_change"], name="Change in card profit only",
                mode="lines+markers", line=dict(color=Y.AMBER))
fig.add_hline(y=0, line_color="#334155", line_width=1)
fig.update_layout(height=420, margin=dict(t=30, b=20), yaxis=dict(title="USD per year"),
                  legend=dict(orientation="h", y=-0.25))
st.plotly_chart(fig, width="stretch")
st.markdown(f"**Go/no-go:** at {g['multiplier']}x the Base scenario is worth {S.signed(g['headline_value'])} a year - "
            + ("**go**." if g["go"] else "**no-go**.")
            + f" On card profit alone it is {S.signed(g['card_profit_change'])}: the value comes from avoided drawdown loss.")
S.caveat()

# ---------------------------------------------------- workbook reproduction
with st.expander("Workbook-reproduction mode (the reference workbook's own formulas and inputs)"):
    d = W.dashboard(cfg)
    ref = cfg["workbook"]["dashboard_reference"]
    rep = pd.DataFrame({sc: {"Change in fully loaded profit": d[sc]["change_in_fully_loaded_profit"],
                             "Workbook Dashboard": ref[sc]["change_in_fully_loaded_profit"],
                             "Accounts lost": d[sc]["accounts_lost"],
                             "Capital released (one-time)": d[sc]["capital_released"]} for sc in SCENARIOS}).T
    st.dataframe(rep.map(lambda v: f"{v:,.0f}"), width="stretch")
    st.caption("Original 85% / 55% weights and the workbook's modelled loss, used for the ±1% test only. The system's "
               "results above come from account data with the corrected rules.")
