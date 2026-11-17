import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G, results as R  # noqa: E402
from engine.unused_lines import exposure as X  # noqa: E402

S.header("🛡️ Risks and checks")
cfg = S.cfg()
stv = S.stress("base")
g = stv.attrs["go_no_go"]
fa = S.fairness()
fs = fa["summary"]["module_decreases_and_closures"]
tr = S.treatment()

# 1. headline sentence
Y.headline(f"The plan {'still pays off' if g['go'] else 'stops paying off'} if customers react {g['multiplier']:g}x "
           "more strongly than estimated; "
           + (f"{fs['groups_failing']} metros need a fair-lending review before any pilot."
              if fs["groups_failing"] else "no metro fails the fair-lending test, but review it before any pilot."))

# 2. the four red-flag tiles (decision number 5 lives here)
Y.tiles([R.robustness_tile(stv), R.fairness_tile(fa), R.rules_tile(), R.notices_tile(tr, cfg)])
st.write("")

# 3. one chart: the stress test
fig = go.Figure()
x = [f"{m:g}x" for m in stv.index]
fig.add_bar(x=x, y=stv["wb_headline_value"], name=S.term("headline"),
            marker=dict(color=[Y.GREEN if v > 0 else Y.RED for v in stv["wb_headline_value"]]),
            text=[R.signed_short(v) for v in stv["wb_headline_value"]], textposition="outside",
            hovertemplate="%{x}: %{y:$,.0f} a year<extra></extra>")
if S.analyst():
    fig.add_scatter(x=x, y=stv["wb_card_profit_change"], name="Change in card profit only", mode="lines+markers",
                    line=dict(color=Y.AMBER, width=2), marker=dict(size=9),
                    hovertemplate="%{x}: card profit %{y:$,.0f}<extra></extra>")
fig.add_hline(y=0, line_color="#334155", line_width=1)
fig.update_layout(title=(f"{S.term('go_no_go')}: annual value by customer reaction (Base)" if S.analyst()
                         else S.term("go_no_go")), height=400,
                  margin=dict(t=50, b=10), yaxis=dict(title="USD per year", tickformat="$,.0f",
                                                      range=Y.padded(list(stv["wb_headline_value"])
                                                                     + (list(stv["wb_card_profit_change"])
                                                                        if S.analyst() else []), 0.2)),
                  xaxis=dict(title="Customer reaction multiplier (1x = the workbook's estimate)"),
                  legend=dict(orientation="h", y=-0.3))
st.plotly_chart(fig, width="stretch")
S.cap(g["statement"] + ".")

# one worked example
dormant = X.worked_example(10000, 0, cfg["capital"]["risk_weight_dormant_zero_balance"], cfg)
cap, liq = cfg["capital"], cfg["liquidity"]
Y.band("Worked example")
if S.analyst():
    S.md(f"**A dormant $10,000 card** (unused line $10,000, risk weight {cap['risk_weight_dormant_zero_balance']:.0%}): "
         f"exposure $10,000 × {cap['ccf_unused_card_lines']:.0%} = **{S.usd(dormant['exposure_unused'])}**; RWA × "
         f"{cap['risk_weight_dormant_zero_balance']:.0%} = **{S.usd(dormant['rwa_unused'])}**; capital × "
         f"{cap['capital_ratio']:.1%} = ${dormant['capital_required_unused']:,.2f}; capital cost × "
         f"{cap['cost_of_equity']:.0%} = **${dormant['capital_cost_unused']:,.2f}**; HQLA $10,000 × "
         f"{liq['lcr_outflow_unused_card_lines']:.0%} = {S.usd(dormant['hqla'])}; liquidity cost × "
         f"{liq['negative_carry']:.2%} = **${dormant['liquidity_cost']:,.2f}**; "
         f"**carrying cost ${dormant['carrying_cost']:,.2f} a year**.")
else:
    S.md(f"A $10,000 card that is never used costs the bank **${dormant['carrying_cost']:,.2f} a year** to hold: "
         f"${dormant['capital_cost_unused']:,.2f} for the capital held against it and ${dormant['liquidity_cost']:,.2f} "
         "for the liquidity buffer - under the assumed (not current) rules.")

# 4-5. what this means / what to do
nt = R.notices(tr, cfg)
aan = int(nt.loc[nt["adverse_action_notice"].astype(bool), "actions"].sum())
c1, c2 = st.columns(2)
Y.means([
    (f"The value survives customers reacting {g['multiplier']:g}x more strongly"
     + (", thanks to lower expected losses." if g["card_profit_change"] < 0 else ".")) if g["go"] else
    f"The value turns negative if customers react {g['multiplier']:g}x more strongly.",
    (f"{fs['groups_failing']} of {fs['groups_tested']} testable metros fail the four-fifths fairness test."
     if fs["groups_tested"] else "Too few actions per metro to test fairness yet."),
    f"{aan:,} limit cuts need an adverse-action notice; inactivity actions need none.",
], where=c1)
Y.decide([
    (f"Fair-lending review of {', '.join(fs['failing_groups'])} before any pilot." if fs["groups_failing"]
     else "Fair-lending review before any pilot."),
    "Compliance to confirm the flagged notices (idle-line cuts, non-reissue, stopping increases).",
    "Treat capital and liquidity savings as dependent on the March 2026 proposal being adopted.",
], where=c2)

# 6. details
st.write("")
names = ["Notices by reason code", "Fairness by metro", "Parameters", "Current US rules comparison"]
tab = dict(zip(names, st.tabs(names)))
with tab["Notices by reason code"]:
    if S.analyst():
        show = pd.DataFrame({"Reason code": nt["code"], "Action": nt["action"],
                             "Actions": nt["actions"].map(lambda v: f"{v:,}"), "Notice": nt["notice"],
                             "Adverse-action notice": nt["adverse_action_notice"].map({True: "yes", False: "no"}),
                             "Compliance flag": nt["compliance_flag"]})
    else:
        show = pd.DataFrame({"Action": nt["action"], "Actions": nt["actions"].map(lambda v: f"{v:,}"),
                             "Adverse-action notice": nt["adverse_action_notice"].map({True: "required",
                                                                                       False: "not required"})})
    st.dataframe(show, width="stretch", hide_index=True)
    S.cap(f"{cfg['treatment']['fee_restriction_text']}. Never an inactivity fee. {G.COMPLIANCE_NOTE}")
with tab["Fairness by metro"]:
    for key, label in [(k, v) for k, v in [("module_decreases_and_closures", "Decreases and closures"),
                                           ("module_increases", "Increases")] if k in fa]:
        df = fa[key]
        st.markdown(f"**{label}**")
        if S.analyst():
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.dataframe(pd.DataFrame({"Metro": df["group"], "Accounts": df["n"].map(lambda v: f"{v:,}"),
                                       "Selected": df["selected"].map(lambda v: f"{v:,}"),
                                       "Result": df["status"]}), width="stretch", hide_index=True)
    S.cap(fa["proxy_method"] + f". Selection rates are compared with the population rate; a metro with fewer than "
          f"{fa['min_selected_per_group']} selected accounts (or under 30 accounts) shows 'insufficient sample'. "
          + fa["increases_note"])
with tab["Parameters"]:
    rows = [
        ("CCF on unused card lines", f"{cap['ccf_unused_card_lines']:.0%}", "regulatory", "No card line ever gets 0% (working assumption; current law 0%)"),
        ("Risk weight - transactor", f"{cap['risk_weight_transactor']:.0%}", "regulatory", "Paid in full (or nothing due) every cycle for 12 months, no plan / promotional balance"),
        ("Risk weight - non-transactor", f"{cap['risk_weight_non_transactor']:.0%}", "regulatory", "Any revolving, plan or promotional balance; under 12 months of history"),
        ("Risk weight - dormant zero-balance (B5)", f"{cap['risk_weight_dormant_zero_balance']:.0%}", "regulatory", "Provisional, pending the open decision"),
        ("Risk weight - non-qualifying retail", f"{cap['risk_weight_non_qualifying_retail']:.0%}", "regulatory", f"Aggregate retail exposure above ${cap['regulatory_retail_aggregate_limit_usd']:,.0f}"),
        ("Capital ratio", f"{cap['capital_ratio']:.1%}", "business", "Illustrative (B4)"),
        ("Cost of equity", f"{cap['cost_of_equity']:.0%}", "business", "Illustrative (B4)"),
        ("LCR outflow on unused card lines", f"{liq['lcr_outflow_unused_card_lines']:.0%}", "regulatory", "Conservative assumption: cancellable lines are not 'committed' under current law"),
        ("Negative carry on the HQLA buffer", f"{liq['negative_carry']:.2%}", "business", "Funding cost minus HQLA yield"),
        (S.term("drawdown"), "annual PD × LGD × LEQ × unused", "workbook", f"Annual PD (imputed from the segment if missing); LEQ source: {cfg['drawdown_risk']['leq_source']}"),
        ("Fixed cost basis", cfg["costs"]["fixed_cost_basis"], "business", "Engine allocation or the workbook's per segment (B5)"),
        ("Operational risk", "excluded", "regulatory", "Bank-level only: not in account or lever economics"),
        ("SLR", "not calculated", "regulatory", "Risk-based capital assumed to bind; shown in the comparison"),
    ]
    if S.analyst():
        S.md("<table><tr><th>Parameter</th><th>Value</th><th>Type</th><th>Note</th></tr>" + "".join(
            f"<tr><td>{a}</td><td><b>{b}</b></td><td>{Y.vt(c)}</td><td>{d}</td></tr>" for a, b, c, d in rows)
            + "</table>", unsafe_allow_html=True)
    else:
        st.dataframe(pd.DataFrame([(a, b) for a, b, _, _ in rows], columns=["Setting", "Value"]), width="stretch",
                     hide_index=True)
with tab["Current US rules comparison"]:
    f = S.frame()
    sc = f[f["screened"]]
    cur = X.current_rules(sc, cfg)
    comp = pd.DataFrame({
        "Working assumptions (March 2026 proposal adopted)": [sc["rwa"].sum(), sc["rwa_unused"].sum(),
                                                              sc["capital_cost"].sum(), sc["liquidity_cost"].sum(),
                                                              float("nan")],
        "Current US rules": [cur["rwa_current_rules"].sum(), 0.0, cur["capital_cost_current_rules"].sum(),
                             cur["liquidity_cost_current_rules"].sum(), cur["slr_capital_required"].sum()],
    }, index=["RWA", "RWA from unused lines", "Capital cost a year", "Liquidity cost a year",
              "SLR capital (10% CCF, 3%; Category I-III)"])
    st.dataframe(comp.map(S.usd), width="stretch")
    S.cap("Current law: 0% CCF on unconditionally cancellable lines, 100% on drawn balances, no LCR outflow on "
          "cancellable lines. The comparison shows how much of the value depends on the assumptions.")
S.caveat()
