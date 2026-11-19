import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import levers as L, treatment as T  # noqa: E402

S.header("📊 What the strategies are worth")
cfg = S.cfg()
base = S.run("base")
st_ = base["strategies"]
ap = st_["approved_combined"]
lo = S.run("conservative")["strategies"]["approved_combined"]["headline_value"]
hi = S.run("aggressive")["strategies"]["approved_combined"]["headline_value"]
stv = S.stress("base")
g = stv.attrs["go_no_go"]
pb = R.problem(S.frame())

# 1. headline sentence
Y.headline(f"If all four strategies go ahead, the value is about {R.short(st_['total_potential'])} a year in the Base "
           f"case: {R.short(ap['headline_value'])} approved, {R.short(st_['proposed'])} proposed and "
           f"{R.short(st_['awaiting_decision'])} awaiting a decision.")
S.cap(R.mix_sentence(st_))

# 2. cards
Y.cards([
    ("Approved", R.signed_short(ap["headline_value"]), "a year: Strategies 1 and 2 and the Invite, together", Y.GREEN,
     S.define("headline")),
    ("Proposed", R.signed_short(st_["proposed"]), "a year: Strategy 4, stop automatic increases",
     Y.STATUS_COLORS["proposed"], "Assumption-based: valued from the bank's history of automatic increases."),
    ("Awaiting a decision", R.signed_short(st_["awaiting_decision"]), "a year: Strategy 3's actions, after the "
     "90-day warning", Y.STATUS_COLORS["awaiting_decision"], "Right-size, close (24+ months unused), don't reissue."),
    ("Total potential", R.signed_short(st_["total_potential"]), "a year if all four go ahead", Y.NAVY,
     "Approved + proposed + awaiting a decision."),
], dominant=3)

# 3. one chart: stand-alone value per strategy, coloured by status
st.write("")
bars = R.chart_bars(st_, cfg)
colour = [Y.STATUS_COLORS["approved_test_only"] if v < 0 else Y.STATUS_COLORS[s]
          for s, v in zip(bars["status"], bars["value"])]
ylab = [f"<b>{lab}</b><br><span style='font-size:13px'>{t}</span>" for lab, t in zip(bars["label"], bars["status_text"])]
fig = go.Figure(go.Bar(y=ylab, x=bars["value"], orientation="h",
                       marker=dict(color=colour, line=dict(color="#ffffff", width=2)),
                       text=[R.signed_short(v) for v in bars["value"]], textposition="outside",
                       hovertemplate="%{x:$,.0f} a year<extra></extra>"))
fig.add_vline(x=0, line_color="#334155", line_width=1)
fig.update_layout(title="What each strategy is worth a year, on its own (Base case)", height=130 + 72 * len(bars),
                  margin=dict(t=50, b=10, l=10), xaxis=dict(title="USD per year", tickformat="$,.0f",
                                                           range=Y.padded(list(bars["value"]), 0.25)),
                  yaxis=dict(autorange="reversed"), showlegend=False, bargap=0.35)
st.plotly_chart(fig, width="stretch")
S.cap("Values are for each strategy on its own. Strategies 1 and 2 (with the Invite) together give the approved "
      f"{R.short(ap['headline_value'])} a year: some customers receive more than one action, so the parts do not add "
      "up exactly. Red: approved but loses money at today's offer costs, so tested only.")

# the approved actions in detail
Y.band("The approved actions in more detail (Base case)")
st.dataframe(pd.DataFrame([
    ("Annual value", f"{R.short(ap['headline_value'])}: {R.short(ap['drawdown_reduction'])} less expected drawdown "
                     f"loss, {R.signed_short(ap['card_profit_change'])} of card profit"),
    ("Range, cautious to bold scenario", f"{R.short(lo)} to {R.short(hi)}"),
    (f"If customers react {g['multiplier'] - 1:.0%} more strongly than assumed",
     f"{R.short(g['headline_value'])}: {'still worth it' if g['go'] else 'not worth it'}"),
    ("Customers expected to leave", f"{ap['accounts_leaving']:,.0f} of {pb['accounts']:,}"),
    ("Unused credit removed", R.short(ap["unused_removed"])),
    ("Capital freed (one time, not annual)", R.short(ap["capital_released"])),
], columns=["Measure", "Value"]), width="stretch", hide_index=True)
S.md(f"**Most of the value is lower risk.** The approved {R.short(ap['headline_value'])} is "
     f"{R.short(ap['drawdown_reduction'])} less expected drawdown loss and {R.signed_short(ap['card_profit_change'])} "
     "of card profit lost to campaign costs and customers spending less or leaving. On card profit alone it is "
     "slightly negative. Capital freed is a one-time amount and is never added to the annual value.")

# details
rows = R.strategy_rows(st_)
with st.expander("Each strategy: value, components, customers"):
    st.dataframe(pd.DataFrame({
        "Strategy": rows["number"].astype(str) + ". " + rows["name"], "Status": rows["status"],
        "Annual value (on its own)": rows["value"].map(S.signed), "Made up of": rows["components"],
        "Customers affected": rows["customers"].map(lambda v: f"{v:,}"),
        "Expected to leave": rows["leaving"].map(lambda v: f"{v:,.0f}"),
        "Unused credit removed": rows["unused_removed"].map(R.short),
        "Capital freed (one time)": rows["capital"].map(R.short),
    }), width="stretch", hide_index=True, column_config={"Made up of": st.column_config.TextColumn(width="large")})
    S.cap("Strategy 4 removes no existing credit: it avoids next year's increases, shown as unused credit avoided; it "
          "frees no capital today.")
if S.analyst():
    run = base
    s = run["summary"]
    h = s["workbook_levers_headline"]
    with st.expander("Analyst: every lever, by segment, timing, fixed-cost setting"):
        lt = run["levers"]
        tt = T.timing_table(lt, cfg)
        st.dataframe(pd.DataFrame({
            "Group": lt["group"], "Status": lt["status"],
            "Accounts targeted": lt["accounts_targeted"].map(lambda v: f"{v:,.0f}"),
            "Accounts leaving": lt["accounts_leaving"].map(lambda v: f"{v:,.0f}"),
            "Unused removed": lt["unused_removed"].map(S.usd), "Δ card profit": lt["card_profit_change"].map(S.signed),
            "Δ drawdown loss": lt["drawdown_change"].map(S.signed), "Full annual value": lt["headline_value"].map(S.signed),
            "Year-1 value": tt["year1_value"].map(S.signed), "Capital released (one-time)": lt["capital_released"].map(S.usd),
        }, index=lt.index), width="stretch")
        sg = run["segments"]
        st.dataframe(pd.DataFrame({
            "Annual value": sg["headline_value"].map(S.signed), "Δ card profit": sg["card_profit_change"].map(S.signed),
            "Δ relationship-adjusted": sg["relationship_adjusted_change"].map(S.signed),
            "Unused removed": sg["unused_removed"].map(S.usd), "Accounts leaving": sg["accounts_leaving"].map(lambda v: f"{v:,.1f}"),
        }, index=[S.seg_label(i) if i != "total" else "Total" for i in sg.index]), width="stretch")
        S.md(f"- Levers combined (Base): {S.signed(h['headline_value'])}; relationship-adjusted "
             f"{S.signed(h['relationship_adjusted_change'])}; value by type: "
             + ", ".join(f"{k.replace('_', ' ')} {S.signed(h[k])}" for k in L.VALUE_TYPES) + ".\n"
             f"- Robustness: {g['statement']}.")
        cur = cfg["costs"]["fixed_cost_basis"]
        other = [o for o in cfg["costs"]["fixed_cost_basis_options"] if o != cur][0]
        a = S.alt({"costs": {"fixed_cost_basis": other}})
        S.md(f"- Fixed-cost setting `{other}` (B5): approved {S.signed(a['strategies']['approved_combined']['headline_value'])}, "
             f"{a['screened']:,} cards selected (setting in use `{cur}`: {S.signed(ap['headline_value'])}, "
             f"{pb['accounts']:,}).")
        fig2 = go.Figure(go.Bar(x=[f"{m:g}x" for m in stv.index], y=stv["wb_headline_value"],
                                marker=dict(color=[Y.GREEN if v > 0 else Y.RED for v in stv["wb_headline_value"]])))
        fig2.add_scatter(x=[f"{m:g}x" for m in stv.index], y=stv["wb_card_profit_change"], name="Card profit only",
                         mode="lines+markers", line=dict(color=Y.AMBER))
        fig2.update_layout(title="Approved value by customer reaction multiplier", height=320, showlegend=False,
                           margin=dict(t=50, b=10), yaxis=dict(tickformat="$,.0f"))
        st.plotly_chart(fig2, width="stretch")
S.caveat()
