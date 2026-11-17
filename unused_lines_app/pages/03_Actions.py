import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines.assumptions import SCENARIOS  # noqa: E402
from engine.unused_lines import levers as L, treatment as T  # noqa: E402

S.header("📊 Actions and value")
cfg = S.cfg()
c0, _ = st.columns([2, 3])
scn = c0.radio("Scenario", SCENARIOS, index=SCENARIOS.index(S.scenario()), format_func=str.capitalize,
               horizontal=True, help="Conservative, Base and Aggressive use the reference workbook's lever shares "
                                     "and customer responses.")
st.session_state["scenario"] = scn
run = S.run(scn)
s = run["summary"]
h = s["workbook_levers_headline"]
pend = s["pending_approval"]["headline_value"]
acts = R.actions(run, cfg, S.analyst())
approved = acts[acts["status"] == "approved"]
y1 = float(approved["year1"].sum())

# 1. headline sentence
Y.headline(f"The {scn.capitalize()} plan is worth {R.signed_short(h['headline_value'])} a year from approved actions "
           f"({R.signed_short(y1)} in year 1); {R.signed_short(pend)} more awaits your decision on dormant cards.")

# 2. cards, the annual value dominant
Y.cards([
    (S.term("headline"), R.signed_short(h["headline_value"]), "a year from approved actions, with interactions",
     Y.GREEN, S.define("headline")),
    (S.term("year1"), R.signed_short(y1), "approved actions in their first year", Y.BLUE, S.define("year1")),
    (S.term("pending"), R.signed_short(pend), "a year: right-size, close, do not reissue (B6)", Y.AMBER,
     S.define("pending")),
    (S.term("leaving"), f"{h['accounts_leaving']:,.0f}", "expected, approved actions", Y.GREY, S.define("leaving")),
], dominant=0)

# 3. one chart: annual value by action, year 1 alongside
st.write("")
lab = list(acts["chart_label"])
fig = go.Figure()
fig.add_bar(y=lab, x=acts["annual"], orientation="h", name="Annual value", marker=dict(color=Y.NAVY),
            text=[R.signed_short(v) for v in acts["annual"]], textposition="outside",
            hovertemplate="%{y}<br>Annual: %{x:$,.0f}<extra></extra>")
fig.add_bar(y=lab, x=acts["year1"], orientation="h", name="Year 1", marker=dict(color=Y.LIGHT),
            text=[R.signed_short(v) for v in acts["year1"]], textposition="outside",
            hovertemplate="%{y}<br>Year 1: %{x:$,.0f}<extra></extra>")
fig.add_vline(x=0, line_color="#334155", line_width=1)
fig.update_layout(title="Annual value by action, with year 1 alongside", barmode="group", height=120 + 70 * len(acts),
                  margin=dict(t=50, b=10, l=10), xaxis=dict(title="USD per year", tickformat="$,.0f",
                                                            range=Y.padded(list(acts["annual"]) + list(acts["year1"]), 0.25)),
                  yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.15), bargap=0.3)
st.plotly_chart(fig, width="stretch")

table = pd.DataFrame({
    "Action": acts["label"],
    "Customers affected": acts["customers"].map(lambda v: f"{v:,.0f}"),
    "Annual value": acts["annual"].map(S.signed),
    "Year-1 value": acts["year1"].map(S.signed),
    "Customers leaving": acts["leaving"].map(lambda v: f"{v:,.0f}"),
})
st.dataframe(table, width="stretch", hide_index=True,
             column_config={"Action": st.column_config.TextColumn(width="large")})
S.cap(f"Each action valued on its own; the annual value above includes their interactions. "
      f"{S.term('capital')}: {S.usd(s['capital_released_one_time'])}.")

# 4-5. what this means / what to decide
best = approved.loc[approved["annual"].idxmax()] if len(approved) else None
worst = approved.loc[approved["annual"].idxmin()] if len(approved) else None
c1, c2 = st.columns(2)
Y.means([
    (f"{best['label']} adds the most among approved actions: {R.signed_short(best['annual'])} a year."
     if best is not None else "No approved action in this scenario."),
    (f"{worst['label']} loses {R.short(-worst['annual'])} a year on its own: offer costs exceed the gain."
     if worst is not None and worst["annual"] < 0 else
     f"Approved actions cost few customers: about {h['accounts_leaving']:,.0f} expected to leave."),
    f"Dormant-card decisions (B6) would add {R.signed_short(pend)} a year.",
], where=c1)
Y.decide([
    f"Approve the dormant-card actions to add {R.signed_short(pend)} a year, or keep them on hold.",
    "Stopping automatic increases is assumption-based: confirm the no-notice treatment with compliance.",
    "Start with a pilot and a holdout; the customer responses are estimates.",
], where=c2)

# 6. details
st.write("")
names = ["By lever"] + (["By segment", "How the value is built", "Fixed-cost setting (B5)", "Timing"]
                        if S.analyst() else ["Timing"])
tab = dict(zip(names, st.tabs(names)))
tt = T.timing_table(run["levers"], cfg)
lt = run["levers"].join(tt[["year1_share", "year1_value", "starts", "full_value_when"]])
key = {v: k for k, v in L.LEVER_LABELS.items()}
with tab["By lever"]:
    if S.analyst():
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
    else:
        show = pd.DataFrame({"Lever": [G.LEVER_PLAIN[key[i]] for i in lt.index],
                             "Status": [R.STATUS_TEXT[R.lever_status(key[i], cfg)] for i in lt.index],
                             "Annual value": lt["headline_value"].map(S.signed).values})
        show = show[[key[i] not in G.NOT_RECOMMENDED for i in lt.index]]
        st.dataframe(show, width="stretch", hide_index=True)
with tab["Timing"]:
    tshow = pd.DataFrame({"Lever": [G.LEVER_PLAIN[key[i]] for i in lt.index], "Starts": lt["starts"].values,
                          "Full value": lt["full_value_when"].values,
                          "Year-1 share": lt["year1_share"].map(lambda v: f"{v:.0%}").values})
    if not S.analyst():
        tshow = tshow[[key[i] not in G.NOT_RECOMMENDED for i in lt.index]]
    st.dataframe(tshow, width="stretch", hide_index=True)
if S.analyst():
    with tab["By segment"]:
        sg = run["segments"]
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
    with tab["How the value is built"]:
        S.md(f"- **Headline value** {S.signed(h['headline_value'])} = change in card profit "
             f"{S.signed(h['card_profit_change'])} + reduction in expected drawdown loss {S.signed(-h['drawdown_change'])}.\n"
             f"- **Card profit alone:** {S.signed(h['card_profit_change'])} a year.\n"
             f"- **Relationship-adjusted change:** {S.signed(h['relationship_adjusted_change'])} (includes relationship "
             "profit lost with leavers).\n"
             f"- **Extra levers (assumption-based):** {S.signed(s['extra_levers']['headline_value'])}; "
             f"**pending approval (B6):** {S.signed(pend)}.\n"
             f"- **RWA change:** {S.signed(h['rwa_change'])}; unused lines removed {S.usd(h['unused_removed'])}.\n"
             "- **Value by type:** " + ", ".join(f"{k.replace('_', ' ')} {S.signed(h[k])}" for k in L.VALUE_TYPES) + ".")
        S.cap("Transactor right-sizing is valued to show its effect and is never recommended.")
    with tab["Fixed-cost setting (B5)"]:
        cur = cfg["costs"]["fixed_cost_basis"]
        other = [o for o in cfg["costs"]["fixed_cost_basis_options"] if o != cur][0]
        a = S.alt({"costs": {"fixed_cost_basis": other}})
        here = S.run("base")["summary"]
        f = S.frame()
        rows = {cur: (int(f["screened"].sum()), float(f.loc[f["screened"], "card_profit"].sum()),
                      here["workbook_levers_headline"]["headline_value"], here["pending_approval"]["headline_value"]),
                other: (a["screened"], a["card_profit"], a["summary"]["workbook_levers_headline"]["headline_value"],
                        a["summary"]["pending_approval"]["headline_value"])}
        b5 = pd.DataFrame(rows, index=["Screened accounts", "Card profit (screened)", "Base annual value",
                                       "Pending (B6)"]).T
        b5.index = [f"{k} (in use)" if k == cur else k for k in b5.index]
        st.dataframe(b5.style.format({"Screened accounts": "{:,.0f}", "Card profit (screened)": "${:,.0f}",
                                      "Base annual value": "${:+,.0f}", "Pending (B6)": "${:+,.0f}"}), width="stretch")
        S.cap("engine_allocated: the engine's fixed cost allocation per account; workbook_segment: the workbook's "
              "$30-60 a year by segment. Fixed cost stays when an account leaves, so the value changes through the "
              "accounts in scope. Change the setting on What-if.")
S.caveat()
