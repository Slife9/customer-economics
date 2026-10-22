from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib import charts as C
from engine.levers import summary as LSUMMARY
from app.lib import customer_workup as CW
from app.lib import lever_ui as UI
from app.lib import nav


st.set_page_config(page_title="Strategy Overview", page_icon="🎯", layout="wide")
st.title("🎯 Strategy Overview")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
sizes = result["sizes"]
worklists = result["worklists"]
levers = result["levers"]

LEVER_META = {  # one-liners, notices and sizing now live on each lever page
    "L1": {"name": "Rewards & Promo Economics", "icon": "🎁",
          "one_liner": "Which customers take out more in rewards than the "
                      "relationship puts in — and whether the fix is charging "
                      "for value already delivered.",
          "sequencing": "Permission-heavy", "notice": "45 days + right to reject (Reg Z)",
          "speed": "Slow — needs a fee-change notice and a pilot"},
    "L2": {"name": "Credit Lines & Unused-Line Cost", "icon": "📈",
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
st.subheader("Portfolio opportunity: base scenario, with the low-high range")
summary = LSUMMARY.portfolio_summary(sizes)
if not summary["levers_in_total"]:
    st.warning("These results come from a **pre-rebuild valuation** (an older results "
               "bundle), so no low/base/high scenarios are available. Re-export the "
               "bundle with the current engine to see the corrected lever values.")
else:
    t = {sc: summary["scenarios"][sc]["total_usd"] for sc in ("low", "base", "high")}
    r1, r2, r3 = st.columns(3)
    r1.metric("Base total, year 1", f"${t['base']:,.0f}/yr",
              help="L1 + L2 + L3 (year 1) + L4 (year 1) + L6 (year 1), base scenario. "
                   "L5 is never part of this total.")
    r2.metric("Low - high range", f"${t['low']:,.0f} - ${t['high']:,.0f}")
    by_basis = summary["scenarios"]["base"]["by_basis"]
    r3.metric("Of the base, assumption-based", f"${by_basis.get('assumption', 0):,.0f}",
              help="Components that depend on a customer response not yet observed - "
                   "these need a pilot before anyone relies on them.")
    rows = []
    for code in ("L1", "L2", "L3", "L4", "L6"):
        sz = sizes[code]
        if not sz.has_scenarios:
            rows.append({"Lever": code, "Base": None, "Low": None, "High": None,
                         "Value types": "", "Evidence": sz.basis})
            continue
        comps = sz.scenarios["base"]["components"].values()
        rows.append({
            "Lever": code,
            "Base": sz.scenarios["base"]["total_usd"],
            "Low": sz.scenarios["low"]["total_usd"],
            "High": sz.scenarios["high"]["total_usd"],
            "Value types": ", ".join(sorted({c["value_type"] for c in comps})),
            "Evidence": ("assumption-based, pilot required"
                         if any(c["basis"] == "assumption" for c in comps) else "measured"),
        })
    st.dataframe(pd.DataFrame(rows).style.format(
        {c: "${:,.0f}" for c in ("Base", "Low", "High")}, na_rep="-"),
        width="stretch", hide_index=True)
    l5 = summary.get("L5_separately")
    if l5:
        be = l5["breakeven_keep_rate_base"]
        cond = l5["conditional_net_usd"]
        st.info(f"**L5 Retention is not in the total.** Value at risk: "
                f"**${l5['value_at_risk_usd']:,.0f}** (trailing-12-month profit of at-risk "
                f"customers). A retention programme's conditional net is "
                f"${cond['low']:,.0f} / ${cond['base']:,.0f} / ${cond['high']:,.0f} "
                f"(low / base / high) and breaks even only if it keeps at least "
                f"**{'n/a' if be is None else f'{be:.0%}'}** of would-be leavers.")

st.divider()
st.header("All six levers at a glance")
st.caption("Each lever has its own page with the method, assumptions, a what-if explorer, "
           "the regulation and a customer drill-down. L5 is value at risk, never in the total.")
glance_rows = []
for code in ["L1", "L2", "L3", "L4", "L5", "L6"]:
    meta, sz, wl = LEVER_META[code], sizes[code], worklists[code]
    acts = ", ".join(f"{a} {n:,}" for a, n in wl["action"].value_counts().items())
    row = {"Lever": f"{meta['icon']} {code} {meta['name']}", "Customers": len(wl),
           "Recommended actions": acts, "Readiness": meta["speed"]}
    if sz.has_scenarios:
        comps = sz.scenarios["base"]["components"].values()
        lo, ba, hi = (sz.scenarios[x]["total_usd"] for x in ("low", "base", "high"))
        if code == "L5":
            row["Base value"] = f"Value at risk ${sz.unpriced_context_usd:,.0f} (not in total)"
            row["Low - high"] = f"conditional ${lo:,.0f} – ${hi:,.0f}"
        else:
            row["Base value"] = f"${ba:,.0f}"
            row["Low - high"] = f"${lo:,.0f} – ${hi:,.0f}"
        row["Value types"] = ", ".join(sorted({c["value_type"] for c in comps}))
        row["Evidence"] = ("assumption-based, pilot required"
                           if any(c["basis"] == "assumption" for c in comps) else "measured")
    else:
        row["Base value"] = "pre-rebuild valuation"
        row["Low - high"] = row["Value types"] = row["Evidence"] = ""
    glance_rows.append(row)
st.dataframe(pd.DataFrame(glance_rows)[["Lever", "Customers", "Recommended actions", "Base value",
                                        "Low - high", "Value types", "Evidence", "Readiness"]],
             hide_index=True, width="stretch")
link_cols = st.columns(6)
for col, code in zip(link_cols, ["L1", "L2", "L3", "L4", "L5", "L6"]):
    path = nav.lever_page(code)
    with col:
        if path:
            UI.page_link(path, label=f"{code} page", icon=LEVER_META[code]["icon"])

st.divider()
st.header("Customer lookup, across every lever")
st.caption("Pick a customer to see their full relationship economics and every lever "
           "action recommended for them. For why a customer is in a lever and how their "
           "value is calculated, use that lever page's drill-down.")

cust_options = cv["Masked Customer Number"].tolist()
picked = st.selectbox("Masked Customer Number", options=cust_options)

if picked:
    st.subheader(f"Customer {picked}")
    CW.render_relationship(result, picked)
    CW.render_actions_across_levers(result, picked)
    CW.render_full_workup(result, picked)
