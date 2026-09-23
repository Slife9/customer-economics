from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C

st.set_page_config(page_title="Levers & Strategy", page_icon="🎯", layout="wide")
st.title("🎯 Levers & Strategy")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
sizes = result["sizes"]
worklists = result["worklists"]
levers = result["levers"]

LEVER_META = {
    "L1": {"name": "Rewards & Promo Economics", "icon": "🎁",
          "one_liner": "Which customers take out more in rewards than the "
                      "relationship puts in — and whether the fix is charging "
                      "for value already delivered.",
          "sequencing": "Permission-heavy", "notice": "45 days + right to reject (Reg Z)",
          "speed": "Slow — needs a fee-change notice and a pilot"},
    "L2": {"name": "Line Management by Value", "icon": "📈",
          "one_liner": "Limits move in both directions: trimmed where a line "
                      "sits idle, raised where a good customer would use more.",
          "sequencing": "Fast, decrease side; moderate, increase side",
          "notice": "Adverse action notice on any decrease (Reg B)",
          "speed": "Fast — no pilot needed, notice required on decreases only"},
    "L3": {"name": "Value-Based Pricing", "icon": "💲",
          "one_liner": "Price against full cost, not risk alone — the gap "
                      "opens because risk drifts after origination and the "
                      "rate does not.",
          "sequencing": "Slowest — highest permission",
          "notice": "CARD Act: no increase in year 1, new-transactions-only, "
                    "45 days notice, fair lending review",
          "speed": "Slow — champion/challenger required before rollout"},
    "L4": {"name": "Cost-to-Serve Migration", "icon": "⚙️",
          "one_liner": "Move servicing demand to cheaper channels. Usually the "
                      "largest pool and the fastest to prove.",
          "sequencing": "Fastest", "notice": "None",
          "speed": "Fast — no customer contact, no gate, deploy now"},
    "L5": {"name": "Retention Targeting", "icon": "🛟",
          "one_liner": "Spend the retention budget by worth, not balance or "
                      "tenure. Uplift itself must come from a pilot.",
          "sequencing": "Needs a pilot design first", "notice": "None to flag risk",
          "speed": "Pilot required — sizing is value at risk, not recoverable value"},
    "L6": {"name": "Channel Quality Review", "icon": "🧭",
          "one_liner": "Acquisition channels ranked by the customer value they "
                      "actually produced, net of cost to acquire.",
          "sequencing": "Fast — a sourcing decision, not a customer action",
          "notice": "None",
          "speed": "Fast — redirect acquisition spend, no customer contact"},
}

st.markdown("""
### Sequencing — run by how fast a lever pays and how much permission it needs, not by number
Levers with no customer contact and no notice period prove themselves in a
quarter and buy the credibility to attempt the slower, permission-heavy ones.
Running the slowest lever first is faster on paper and stalls in legal review.
""")

seq_order = ["L4", "L2", "L6", "L1", "L5", "L3"]
seq_cols = st.columns(6)
for col, code in zip(seq_cols, seq_order):
    meta = LEVER_META[code]
    with col:
        st.markdown(f"**{meta['icon']} {code}**")
        st.caption(meta["speed"])

st.divider()
st.subheader("Value by lever")
leakage_df = pd.DataFrame([{
    "lever": code, "priced_value_usd": s.priced_value_usd,
    "unpriced_context_usd": s.unpriced_context_usd, "basis": s.basis, "caveat": s.caveat,
} for code, s in sizes.items()])
st.plotly_chart(C.leakage_bar(leakage_df), width="stretch")

st.divider()
st.subheader("Portfolio opportunity range — if every lever were applied")
st.caption("A single 'total opportunity' number would blend four things that "
          "are not the same kind of number - a diagnostic capital figure, an "
          "opportunity ceiling, and value at risk cannot honestly be added "
          "together. This is a range, not a point estimate, and the pieces "
          "left out of it are called out explicitly below rather than folded in.")

priced_total = sum(s.priced_value_usd or 0 for s in sizes.values())
# The high end adds ONLY the two unpriced figures that are legitimately the
# same kind of thing as priced revenue - an opportunity ceiling assuming full,
# frictionless capture (L1, L3). L5's value-at-risk is a potential LOSS if we
# do nothing, not new revenue if we act, and L2's diagnostic capital figure is
# capital efficiency, not P&L revenue - neither belongs in a revenue range.
l1_ceiling = sizes["L1"].unpriced_context_usd or 0
l3_ceiling = sizes["L3"].unpriced_context_usd or 0
optimistic_ceiling = priced_total + l1_ceiling + l3_ceiling

r1, r2 = st.columns(2)
r1.metric("Low end — deployable now, no pilot needed", f"${priced_total:,.0f}/yr",
         help="Sum of L2 + L4 + L6's priced values. Calculated from what "
             "customers already did; does not depend on how anyone responds "
             "to a change we haven't made yet.")
r2.metric("High end — optimistic ceiling if L1 and L3 pilots succeed completely",
         f"${optimistic_ceiling:,.0f}/yr",
         help="Low end plus L1's and L3's opportunity ceilings, which both "
             "assume every customer accepts the change with zero pushback - "
             "a best case, not a forecast. Real value depends entirely on "
             "the champion/challenger pilot results.")
st.caption(f"**Realistically, expect something between these two numbers, "
          f"closer to the low end** until L1 and L3 have real pilot data. "
          f"Two more figures matter but are deliberately NOT part of this "
          f"range: **L5's ${sizes['L5'].unpriced_context_usd or 0:,.0f}** is "
          f"value **at risk** if nothing changes — a potential loss to avoid, "
          f"not revenue to add. **L2's ${sizes['L2'].unpriced_context_usd or 0:,.0f}** "
          f"is economic capital efficiency, a different kind of value than "
          f"P&L revenue, tracked separately by design (concept spec section 7: "
          f"never blend regulatory and economic capital into one figure).")

st.divider()
st.header("Strategy by lever")

for code in seq_order:
    meta = LEVER_META[code]
    lever = levers[code]
    size = sizes[code]
    wl = worklists[code]
    with st.expander(f"{meta['icon']}  **{code} — {meta['name']}**  "
                     f"({len(wl):,} customers in scope)", expanded=(code in ("L4", "L2"))):
        st.markdown(meta["one_liner"])
        colA, colB, colC = st.columns(3)
        colA.metric("Population", f"{len(wl):,} customers")
        if size.is_priced:
            colB.metric("Priced value", f"${size.priced_value_usd:,.0f}/yr")
        else:
            colB.metric("Priced value", "None — by design", help=size.basis)
        colC.metric("Speed to deploy", meta["speed"].split("—")[0].strip())

        if size.unpriced_context_usd is not None:
            st.info(f"**Unpriced context:** ${size.unpriced_context_usd:,.0f}/yr — {size.caveat}")

        st.markdown(f"**Compliance gate:** {meta['notice']}")
        if lever.gates:
            for g in lever.gates:
                st.markdown(f"- {g}")

        st.markdown("**Basis for sizing:**")
        st.caption(size.basis)

        st.markdown("**Sample worklist (top 10 by value at stake):**")
        if len(wl):
            sort_col = "trailing_12m_net_economic_profit" if \
                "trailing_12m_net_economic_profit" in wl.columns else wl.columns[-1]
            st.dataframe(wl.sort_values(sort_col).head(10) if sort_col in wl.columns
                        else wl.head(10), width="stretch")
        else:
            st.caption("No customers currently in scope for this lever.")

st.divider()
st.header("Customer drill-down")
st.caption("Pick a customer to see their full relationship economics and every "
          "lever action recommended for them.")

cust_options = cv["Masked Customer Number"].tolist()
picked = st.selectbox("Masked Customer Number", options=cust_options)

if picked:
    row = cv[cv["Masked Customer Number"] == picked].iloc[0]
    st.subheader(f"Customer {picked}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("CEV score", f"{row['cev_score']:.1f}", row["cev_band"])
    p2.metric("Trailing-12mo NEP", f"${row['trailing_12m_net_economic_profit']:,.0f}")
    p3.metric("Segment / Score", f"{row['Segment']} / {row['Credit Score Band']}")
    p4.metric("Products held", int(row["products_held"]))

    fig = go.Figure(go.Waterfall(
        orientation="v", measure=["relative", "relative", "relative", "total"],
        x=["Card", "Deposit", "Loan", "Total (trailing 12mo)"],
        y=[row["card_net"], row["deposit_net_12m"], row["loan_net_12m"],
          row["trailing_12m_net_economic_profit"]],
        decreasing={"marker": {"color": "#ef4444"}},
        increasing={"marker": {"color": "#2563eb"}},
        totals={"marker": {"color": "#16a34a" if row["trailing_12m_net_economic_profit"] >= 0 else "#dc2626"}},
        text=[f"${v:,.0f}" for v in [row["card_net"], row["deposit_net_12m"],
                                     row["loan_net_12m"],
                                     row["trailing_12m_net_economic_profit"]]],
        textposition="outside"))
    fig.update_layout(title="This customer's relationship economics", height=380,
                      showlegend=False, margin=dict(t=50, b=20))
    st.plotly_chart(fig, width="stretch")

    if bool(row["relationship_covers_card_loss"]):
        st.success("This customer loses money on their card alone, but the full "
                  "relationship is profitable — never recommend exit.")

    if row["Masked Customer Number"] in set(result["suppressed"].suppressed["Masked Customer Number"]):
        reason = result["suppressed"].suppressed.set_index(
            "Masked Customer Number").loc[picked, "suppression_reason"]
        st.warning(f"**Suppressed from every lever: {reason}.** No action is "
                  f"assigned to this customer regardless of their economics — "
                  f"high servicing cost driven by vulnerability is an "
                  f"obligation, not leakage.")
    else:
        matches = []
        for code, wl in worklists.items():
            if len(wl) and picked in set(wl["Masked Customer Number"]):
                r = wl[wl["Masked Customer Number"] == picked].iloc[0]
                matches.append((code, r))
        if matches:
            st.markdown("**Recommended actions for this customer:**")
            for code, r in matches:
                meta = LEVER_META[code]
                action = r.get("action", "—")
                reason = r.get("reason", "—")
                st.markdown(f"- {meta['icon']} **{code} · {action}** — {reason}")
                tactics = r.get("suggested_engagement_tactics", "")
                if isinstance(tactics, str) and tactics:
                    st.caption(f"　→ {tactics}")
        else:
            if bool(row["is_below_cost"]):
                st.info(f"Below cost, routed to **{row.get('routed_lever', 'STRUCTURAL')}** "
                       f"but did not clear that lever's population threshold. "
                       f"Reason: {row.get('routing_reason', 'n/a')}")
            else:
                st.caption("Profitable, and not flagged by any lever's opportunity criteria.")

    # ---------------- Full Economic Workup, for the admin reviewing a recommendation
    st.divider()
    with st.expander("📋 Full Economic Workup — for the admin deciding whether to act",
                     expanded=False):
        st.caption("Everything the recommendation above was based on: the "
                  "customer's own transactions, the month-by-month P&L that "
                  "produced their trailing-12mo number, and the underlying "
                  "ledger rows - so a decision is never taken on the "
                  "recommendation's word alone.")

        portfolio = result["portfolio"]
        accounts = portfolio["Table2_Card_Account.csv"]
        cust_accts = set(accounts.loc[
            accounts["Masked Customer Number"] == picked, "Masked Account Number"])
        led = result["ledger"]["card"]
        cust_ledger = led[led["Masked Customer Number"] == picked].sort_values("Cycle Month")
        tx_all = portfolio["Table5_Transaction.csv"]
        cust_tx = tx_all[tx_all["Masked Account Number"].isin(cust_accts)].sort_values(
            "Cycle Month")

        tab_pl, tab_tx, tab_ledger = st.tabs(
            ["Monthly P&L", "Transaction Detail", "Full Ledger"])

        with tab_pl:
            if len(cust_ledger):
                monthly = cust_ledger.groupby("Cycle Month").agg(
                    interest_revenue=("interest_revenue", "sum"),
                    interchange_revenue=("interchange_revenue", "sum"),
                    fee_revenue=("fee_revenue", "sum"),
                    reward_expense=("reward_expense", "sum"),
                    funding_cost=("funding_cost", "sum"),
                    credit_cost=("credit_cost", "sum"),
                    cost_to_serve=("cost_to_serve", "sum"),
                    cost_to_serve_marginal=("cost_to_serve_marginal", "sum"),
                    cost_to_serve_fixed_allocated=("cost_to_serve_fixed_allocated", "sum"),
                    capital_cost=("capital_cost", "sum"),
                    net_economic_profit=("net_economic_profit", "sum"),
                ).reset_index()
                monthly["total_revenue"] = (monthly["interest_revenue"]
                                           + monthly["interchange_revenue"]
                                           + monthly["fee_revenue"])
                monthly["total_cost"] = (monthly["reward_expense"] + monthly["funding_cost"]
                                        + monthly["credit_cost"] + monthly["cost_to_serve"]
                                        + monthly["capital_cost"])

                fig = go.Figure()
                fig.add_trace(go.Bar(x=monthly["Cycle Month"], y=monthly["total_revenue"],
                                     name="Revenue", marker_color="#2563eb"))
                fig.add_trace(go.Bar(x=monthly["Cycle Month"], y=-monthly["total_cost"],
                                     name="Cost (incl. risk cost of holding money)",
                                     marker_color="#ef4444"))
                fig.add_trace(go.Scatter(x=monthly["Cycle Month"], y=monthly["net_economic_profit"],
                                        name="Net", mode="lines+markers",
                                        line=dict(color="#16a34a", width=3)))
                fig.update_layout(title="Month-on-month revenue, cost, and net",
                                  barmode="relative", height=380,
                                  yaxis_title="USD/month", margin=dict(t=50, b=20))
                st.plotly_chart(fig, width="stretch")

                st.markdown("**Average per month, by line item:**")
                avg_row = monthly.drop(columns=["Cycle Month"]).mean()
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Interest + interchange + fees", f"${avg_row['total_revenue']:,.2f}")
                a2.metric("Rewards + funding + credit + servicing + capital",
                         f"-${avg_row['total_cost']:,.2f}")
                a3.metric("...of which risk cost of holding money (credit + capital)",
                         f"-${avg_row['credit_cost'] + avg_row['capital_cost']:,.2f}")
                a4.metric("Net economic profit / month", f"${avg_row['net_economic_profit']:,.2f}")

                st.markdown("**Cost to serve, split — this is what usually explains a "
                          "'dormant card still costs us money' finding:**")
                b1, b2 = st.columns(2)
                b1.metric("Caused by THIS customer's own activity",
                         f"${avg_row['cost_to_serve_marginal']:,.2f}/mo",
                         help="Calls, digital sessions, disputes this specific "
                             "account generated, at the true per-unit variable "
                             "cost. Zero for a genuinely unused card.")
                b2.metric("Allocated share of shared servicing overhead",
                         f"${avg_row['cost_to_serve_fixed_allocated']:,.2f}/mo",
                         help="An even split of the call center/digital "
                             "platform's fixed capacity cost across every "
                             "active account, whether or not they use it. "
                             "Real, but not caused by this customer, and not "
                             "something a per-customer action can change - "
                             "closing this account would not remove it, only "
                             "reallocate it across the accounts that remain.")
                if avg_row["cost_to_serve_marginal"] < 0.01:
                    st.caption("This customer generated essentially no service "
                              "requests of their own - the cost to serve shown "
                              "elsewhere is almost entirely the shared-overhead "
                              "allocation above, not anything they did.")

                st.markdown("**Full monthly breakdown:**")
                st.dataframe(monthly.style.format({c: "${:,.2f}" for c in monthly.columns
                                                  if c != "Cycle Month"}),
                            width="stretch", height=320)
                st.download_button("Download this customer's monthly P&L",
                                  monthly.to_csv(index=False),
                                  f"{picked}_monthly_pl.csv", "text/csv")
            else:
                st.caption("No card ledger rows for this customer in the trailing window.")

        with tab_tx:
            if len(cust_tx):
                cat_col = "Merchant Category" if "Merchant Category" in cust_tx.columns \
                    else "Merchant Category Description" if "Merchant Category Description" in cust_tx.columns \
                    else None
                if cat_col:
                    by_cat = cust_tx.groupby(cat_col)["Transaction Amount"].sum().sort_values(
                        ascending=False)
                    fig2 = go.Figure(go.Bar(x=by_cat.index, y=by_cat.to_numpy(),
                                           marker_color="#7c3aed",
                                           text=[f"${v:,.0f}" for v in by_cat.to_numpy()],
                                           textposition="outside"))
                    fig2.update_layout(title="Spend by merchant category (full history)",
                                      height=360, yaxis_title="USD", margin=dict(t=50, b=20))
                    st.plotly_chart(fig2, width="stretch")

                show_tx_cols = [c for c in [
                    "Cycle Month", "Transaction Date", "Merchant Category Description",
                    "Merchant Category Code (MCC)", "Transaction Amount",
                    "Interchange Earned", "Points Earned", "Cash Advance Indicator",
                    "Foreign Transaction Indicator", "Disputed Indicator"]
                    if c in cust_tx.columns]
                st.dataframe(cust_tx[show_tx_cols], width="stretch", height=380)
                st.download_button("Download this customer's transactions",
                                  cust_tx[show_tx_cols].to_csv(index=False),
                                  f"{picked}_transactions.csv", "text/csv")
            else:
                st.caption("No transactions for this customer in the uploaded window.")

        with tab_ledger:
            st.caption("Every account x cycle row this customer's numbers were "
                      "built from - the same rows the ledger reconciliation "
                      "check validates.")
            st.dataframe(cust_ledger, width="stretch", height=420)
            st.download_button("Download this customer's full ledger",
                              cust_ledger.to_csv(index=False),
                              f"{picked}_ledger.csv", "text/csv")
