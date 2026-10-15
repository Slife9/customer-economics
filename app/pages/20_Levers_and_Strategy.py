"""Levers & Strategy - the business/action view of this quarter's run: what
each lever does, which customers are eligible, what to recommend, and what
has to happen before anyone acts. Dollar sizing lives elsewhere on purpose:
Portfolio Economics for the cost/profit breakdown, Downloads for the priced
leakage register, and the Lever Playbook for the full implementation manual
(data needed, teams, pilots, KPIs, regulatory detail) behind every lever
named here. This page is intentionally about the decision, not the ledger.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lib.lever_playbook_content import LEVERS as PLAYBOOK_LEVERS, SEQUENCE_ORDER

st.set_page_config(page_title="Levers & Strategy", page_icon="🎯", layout="wide")
st.title("🎯 Levers & Strategy")
st.caption("What to do about which customers, in what order, and what has to "
          "happen first. For dollar sizing, see **Portfolio Economics** and "
          "the **Downloads** leakage register; for the full how-to behind "
          "each lever, see the **Lever Playbook**.")

if "result" not in st.session_state:
    st.warning("Run an analysis from the **Home** page first.")
    st.stop()

result = st.session_state["result"]
cv = result["customer_view"]
worklists = result["worklists"]
levers = result["levers"]

LEVER_META = {
    "L1": {"name": "Rewards & Promo Economics", "icon": "🎁",
          "one_liner": "Which customers take out more in rewards than the "
                      "relationship puts in — and whether the fix is charging "
                      "for value already delivered.",
          "notice": "45 days + right to reject (Reg Z)",
          "speed": "Slow — needs a fee-change notice and a pilot"},
    "L2": {"name": "Line Management by Value", "icon": "📈",
          "one_liner": "Limits move in both directions: trimmed where a line "
                      "sits idle, raised where a good customer would use more.",
          "notice": "Adverse action notice on any decrease (Reg B)",
          "speed": "Fast — no pilot needed, notice required on decreases only"},
    "L3": {"name": "Value-Based Pricing", "icon": "💲",
          "one_liner": "Price against full cost, not risk alone — the gap "
                      "opens because risk drifts after origination and the "
                      "rate does not.",
          "notice": "CARD Act: no increase in year 1, new-transactions-only, "
                    "45 days notice, fair lending review",
          "speed": "Slow — champion/challenger required before rollout"},
    "L4": {"name": "Cost-to-Serve Migration", "icon": "⚙️",
          "one_liner": "Move servicing demand to cheaper channels. Usually the "
                      "largest pool and the fastest to prove.",
          "notice": "None",
          "speed": "Fast — no customer contact, no gate, deploy now"},
    "L5": {"name": "Retention Targeting", "icon": "🛟",
          "one_liner": "Spend the retention budget by worth, not balance or "
                      "tenure. Uplift itself must come from a pilot.",
          "notice": "None to flag risk",
          "speed": "Pilot required — a test, not an automatic offer"},
    "L6": {"name": "Channel Quality Review", "icon": "🧭",
          "one_liner": "Acquisition channels ranked by the customer value they "
                      "actually produced, net of cost to acquire.",
          "notice": "None",
          "speed": "Fast — redirect acquisition spend, no customer contact"},
}
PLAYBOOK_BY_CODE = {lv["code"]: lv for lv in PLAYBOOK_LEVERS}

# Non-monetary columns only - every worklist also carries at least one
# dollar/value column (current_limit, reward_expense, value_at_risk_usd,
# trailing_12m_net_economic_profit, ...) used for sizing elsewhere; this
# page shows eligibility and action, never the dollar figure behind it.
SAFE_COLS = {
    "L1": ["Masked Customer Number", "action", "reason",
          "notice_days_required", "customer_right_to_reject"],
    "L2": ["Masked Customer Number", "action", "reason", "avg_utilization_12m",
          "peak_utilization_12m", "spend_to_limit_ratio", "transactor_share_12m",
          "account_age_months", "adverse_action_notice_required",
          "suggested_engagement_tactics"],
    "L3": ["Masked Customer Number", "action", "reason", "current_apr",
          "target_apr", "applies_to_new_transactions_only",
          "notice_days_required", "first_year_protected"],
    "L4": ["Masked Customer Number", "action", "reason", "avoidable_calls",
          "paper_statements"],
    "L5": ["Masked Customer Number", "action", "reason", "cev_band"],
    "L6": ["Masked Customer Number", "action", "reason", "acquisition_channel"],
}
PCT_COLS = {"avg_utilization_12m", "peak_utilization_12m", "spend_to_limit_ratio",
           "transactor_share_12m"}


def safe_worklist(code: str) -> pd.DataFrame:
    wl = worklists[code]
    cols = [c for c in SAFE_COLS[code] if c in wl.columns]
    out = wl[cols].copy()
    for c in cols:
        if c in PCT_COLS:
            out[c] = out[c].map(lambda v: f"{v:.0%}" if pd.notna(v) else v)
    return out


eligible_counts = {code: len(worklists[code]) for code in SEQUENCE_ORDER}
total_flagged = len(set().union(*[
    set(worklists[c]["Masked Customer Number"]) for c in SEQUENCE_ORDER if len(worklists[c])
])) if any(eligible_counts.values()) else 0

# ============================================================ 1. OVERVIEW
st.divider()
st.header("Strategy overview")
st.markdown(
    "Six levers, each aimed at a different reason a customer relationship "
    "underperforms or carries unmanaged risk. Every customer reaches a lever "
    "only after **suppression** (hardship, accommodation plan, or SCRA "
    "customers are removed first, no exceptions) and, where relevant, the "
    "routing engine's own attribution of *why* they're below cost. A lever "
    "never acts alone on a hunch - see the gate for each one below.")
o1, o2, o3 = st.columns(3)
o1.metric("Customers flagged for at least one lever", f"{total_flagged:,}")
o2.metric("Levers deployable with no customer-facing gate", "3",
         help="L4, L6, and L2's decrease side need no notice or pilot.")
o3.metric("Levers requiring a pilot before scaling", "3",
         help="L1, L3, and L5 all depend on how a customer responds to a "
             "treatment never tried - see Lever Playbook for why.")

# ============================================================ 2. STRATEGY CARDS
st.divider()
st.header("The six levers")
card_rows = [SEQUENCE_ORDER[:3], SEQUENCE_ORDER[3:]]
for row in card_rows:
    cols = st.columns(3)
    for col, code in zip(cols, row):
        meta = LEVER_META[code]
        with col, st.container(border=True):
            st.markdown(f"#### {meta['icon']} {code}")
            st.markdown(f"**{meta['name']}**")
            st.caption(meta["one_liner"])
            st.markdown(f"👥 **{eligible_counts[code]:,}** customers in scope")
            st.markdown(f"🚦 {meta['speed'].split('—')[0].strip()}")
            st.markdown(f"🔒 {meta['notice']}")

# ============================================================ 3. COMPARISON TABLE
st.divider()
st.header("Lever comparison")
compare_df = pd.DataFrame([{
    "Lever": f"{LEVER_META[c]['icon']} {c}",
    "Name": LEVER_META[c]["name"],
    "What it does": LEVER_META[c]["one_liner"],
    "Customers in scope": eligible_counts[c],
    "Speed": LEVER_META[c]["speed"].split("—")[0].strip(),
    "Compliance gate": LEVER_META[c]["notice"],
} for c in SEQUENCE_ORDER])
st.dataframe(compare_df, width="stretch", hide_index=True)

# ============================================================ 4. LEVER DETAIL
st.divider()
st.header("Lever detail")
st.caption("Expand a lever for its eligibility logic, recommended actions, "
          "safeguards, and a sample of who's currently in scope. For the "
          "full data/teams/testing/KPI playbook behind each one, open "
          "**Lever Playbook**.")

for code in SEQUENCE_ORDER:
    meta = LEVER_META[code]
    pb = PLAYBOOK_BY_CODE[code]
    lever = levers[code]
    wl = worklists[code]
    with st.expander(f"{meta['icon']}  **{code} — {meta['name']}**  "
                     f"({len(wl):,} customers in scope)",
                     expanded=(code in ("L4", "L2"))):
        st.markdown(f"**Why this lever exists:** {pb['problem']}")
        st.markdown(f"**Who's eligible:** {pb['population']}")

        actions_present = sorted(wl["action"].dropna().unique()) if len(wl) and "action" in wl.columns else []
        if actions_present:
            st.markdown(f"**Recommended action(s) this run:** {', '.join(actions_present)}")

        st.markdown(f"**Compliance gate:** {meta['notice']}")
        if lever.gates:
            for g in lever.gates:
                st.markdown(f"- {g}")
        else:
            st.caption("No regulatory gate on this lever's own action.")

        st.markdown("**Sample of who's in scope (non-monetary detail only):**")
        if len(wl):
            st.dataframe(safe_worklist(code).head(10), width="stretch", hide_index=True)
        else:
            st.caption("No customers currently in scope for this lever.")

        try:
            st.page_link("pages/21_Lever_Playbook.py",
                        label=f"Open the full {code} implementation playbook →",
                        icon="📖")
        except Exception:
            st.caption("See **Lever Playbook** in the sidebar for the full "
                      f"{code} implementation manual.")

# ============================================================ 5. CONSOLIDATED WORKLIST
st.divider()
st.header("Consolidated customer worklist")
st.caption("Every customer flagged by any lever this run, one row per "
          "lever-action pair. Filter to find who needs what done.")

combined = pd.concat([
    worklists[c][["Masked Customer Number", "action", "reason"]].assign(Lever=c)
    for c in SEQUENCE_ORDER if len(worklists[c])
], ignore_index=True) if total_flagged else pd.DataFrame(
    columns=["Masked Customer Number", "action", "reason", "Lever"])

if len(combined):
    f1, f2 = st.columns(2)
    lever_opts = f1.multiselect("Lever", SEQUENCE_ORDER)
    action_opts = f2.multiselect("Action", sorted(combined["action"].dropna().unique()))
    filtered = combined
    if lever_opts:
        filtered = filtered[filtered["Lever"].isin(lever_opts)]
    if action_opts:
        filtered = filtered[filtered["action"].isin(action_opts)]
    st.caption(f"Showing {len(filtered):,} of {len(combined):,} lever-action rows")
    st.dataframe(
        filtered[["Masked Customer Number", "Lever", "action", "reason"]]
            .rename(columns={"Masked Customer Number": "Customer ID", "action": "Action", "reason": "Reason"}),
        width="stretch", height=420, hide_index=True)
else:
    st.caption("No customers are currently flagged by any lever.")

# ============================================================ 6. CUSTOMER STRATEGY EXPLORER
st.divider()
st.header("Customer Strategy Explorer")
st.caption("Pick a customer to see their profile and every lever action "
          "recommended for them. For their full dollar-value economics, "
          "see Portfolio Economics' customer drill-down.")

picked = st.selectbox("Masked Customer Number", options=cv["Masked Customer Number"].tolist())

if picked:
    row = cv[cv["Masked Customer Number"] == picked].iloc[0]
    st.subheader(f"Customer {picked}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Segment", row["Segment"])
    p2.metric("Credit Score Band", row["Credit Score Band"])
    p3.metric("Value tier", row["cev_band"])
    p4.metric("Products held", int(row["products_held"]))
    st.markdown(f"**Profitability:** {row['net_band']}")

    cac_status = row.get("cac_payback_status", "Unknown - no acquisition cost data")
    cac_labels = {
        "Recovered": "✅ Acquisition cost recovered",
        "Not yet recovered": "⏳ Acquisition cost not yet recovered",
        "Unknown - predates observation window": "ℹ️ Acquisition date predates the data window - payback can't be measured",
        "Unknown - no acquisition cost data": "ℹ️ No acquisition cost data in this upload",
    }
    st.caption(f"{cac_labels.get(cac_status, cac_status)} "
              f"(acquired via {row.get('acquisition_channel', 'unknown channel')}) "
              f"— see Acquisition Cost for the dollar detail.")

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
                flags = []
                if r.get("adverse_action_notice_required") or code == "L2" and action == "DECREASE_LIMIT":
                    flags.append("Reg B adverse-action notice required")
                if r.get("notice_days_required"):
                    flags.append(f"{int(r['notice_days_required'])}-day notice required")
                if r.get("first_year_protected"):
                    flags.append("CARD Act first-year protection applies - do not act yet")
                if flags:
                    st.caption("　⚠ " + "; ".join(flags))
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

# ============================================================ 7. IMPLEMENTATION ROADMAP
st.divider()
st.header("Implementation roadmap")
st.caption("Sequenced by how fast a lever can go into production and how "
          "much permission it needs, not by lever number - see the Lever "
          "Playbook's 'Fast, Slow, Pilot required' explainer for why this "
          "order builds credibility for the harder levers later.")

ROADMAP = [
    {"phase": "Phase 1 — Deploy now", "codes": ["L4", "L6"],
    "readiness": "No customer-facing gate on either lever. Ready as soon as "
                "operations and marketing/acquisition teams confirm capacity "
                "to act on the worklists above."},
    {"phase": "Phase 2 — Deploy with standard notice", "codes": ["L2"],
    "readiness": "Decreases need a Reg B adverse-action notice (routine, no "
                "pilot); increases need no notice but should track the held-"
                "back challenger group before scaling further."},
    {"phase": "Phase 3 — Pilot first, then scale", "codes": ["L1", "L5", "L3"],
    "readiness": "All three depend on how a customer responds to a "
                "treatment never tried. Do not commit budget or send any "
                "customer-facing notice until a champion/challenger pilot "
                "with a true control group is designed and signed off by "
                "Compliance - see each lever's Playbook entry for the pilot "
                "design and required reviews."},
]
for phase in ROADMAP:
    names = ", ".join(f"{LEVER_META[c]['icon']} {c}" for c in phase["codes"])
    st.markdown(f"**{phase['phase']}** — {names}")
    st.caption(phase["readiness"])

st.divider()
st.caption("This page shows what to do and why it's eligible. For the full "
          "data, teams, pilot design, KPIs, and regulatory detail behind "
          "any lever, open **Lever Playbook**. For dollar-value sizing, see "
          "**Portfolio Economics** and the **Downloads** leakage register.")
