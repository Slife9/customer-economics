import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import segments as SG, exposure as X  # noqa: E402

S.header("🔎 Customer drill-down")
cfg = S.cfg()
f = S.frame()
tr = S.treatment()


def examples(seg: str) -> dict:
    """Typical (nearest the segment's median card profit), borderline (card
    profit nearest $0) and review-together accounts of a segment."""
    g = f[f["screened"] & (f["rule_segment"] == seg)]
    if not len(g):
        return {}
    out = {"typical": (g["card_profit"] - g["card_profit"].median()).abs().idxmin(),
           "borderline": g["card_profit"].abs().idxmin()}
    rt = tr[(tr["segment"] == seg) & (tr["review_together"] != "")]
    if len(rt):
        out["review together"] = rt.index[0]
    return out


# ---------------------------------------------------- choose
c1, c2, c3 = st.columns([2, 2, 3])
segs = [k for k in cfg["segments"]["order"] if (f["screened"] & (f["rule_segment"] == k)).any()]
seg = c1.selectbox("Segment (screened accounts)", segs + ["not screened"],
                   format_func=lambda k: "Not screened" if k == "not screened" else S.seg_label(k))
ex = examples(seg) if seg != "not screened" else {}
pick = c2.radio("Example", list(ex) + ["choose an account"], horizontal=False) if ex else "choose an account"
pool = f.index[f["screened"] & (f["rule_segment"] == seg)] if seg != "not screened" else f.index[~f["screened"]]
if pick == "choose an account":
    acct = c3.selectbox("Account (masked)", list(pool[:2000]))
else:
    acct = ex[pick]
    c3.markdown(f"**Account:** `{acct}`  \n{pick}")
a = f.loc[acct]
t = tr.loc[acct] if acct in tr.index else None

# ---------------------------------------------------- profile
Y.band("Profile")
Y.cards([
    ("Segment", S.seg_label(a["rule_segment"]) + ("" if a["screened"] else " (rule only - not screened)"),
     f"customer {a['customer']} · {a['customer_segment']} · {a['metro']}", Y.SEGMENT_COLORS.get(a["rule_segment"], Y.GREY)),
    ("Credit line", S.usd(a["limit_current"]), f"balance {S.usd(a['balance_current'])} · unused {S.usd(a['ucl_current'])}", Y.BLUE),
    ("Card profit (module)", S.signed(a["card_profit"]),
     f"engine card_net {S.signed(a['card_net'])}; drawdown loss beside: {S.usd(a['drawdown_el'])}", Y.RED if a["card_profit"] < 0 else Y.GREEN),
    ("Activity, last 12 months", f"{int(a['active_months_12m'])} active months",
     f"spend {S.usd(a['spend_12m'])} · {int(a['account_age_months'])} months open · score {a['credit_score']}", Y.GREY),
])
if a.get("protected", False):
    st.markdown(f'<div class="flag"><b>Protected customer ({a["suppression_reason"]}):</b> suppressed by the system '
                "before anything else - no unused-line action.</div>", unsafe_allow_html=True)

# ---------------------------------------------------- exposure trace
st.divider()
Y.band("Exposure and RWA trace - every number with its formula (12-month averages, per year)")
cap, liq = cfg["capital"], cfg["liquidity"]
rate = cap["capital_ratio"] * cap["cost_of_equity"]
lines = [
    ("Unused line (UCL)", f"average of max(limit − balance, 0) over 12 cycles", S.usd(a["ucl"]), "measured"),
    ("Balance", "average ending balance over 12 cycles", S.usd(a["balance"]), "measured"),
    ("Risk weight", X.RW_BASIS_LABELS.get(a["rw_basis"], a["rw_basis"]), f"{a['rw']:.0%}", "regulatory"),
    ("Exposure", f"{S.usd(a['balance'])} + {cap['ccf_unused_card_lines']:.0%} × {S.usd(a['ucl'])}", S.usd(a["exposure"]), "regulatory"),
    ("RWA", f"{S.usd(a['exposure'])} × {a['rw']:.0%}", S.usd(a["rwa"]), "regulatory"),
    ("  of which on the unused line", f"{cap['ccf_unused_card_lines']:.0%} × {S.usd(a['ucl'])} × {a['rw']:.0%}",
     S.usd(a["rwa_unused"]), "regulatory"),
    ("Capital (one-time stock)", f"{S.usd(a['rwa'])} × {cap['capital_ratio']:.1%}", f"${a['capital_required']:,.2f}", "business"),
    ("Capital cost", f"{S.usd(a['rwa'])} × {cap['capital_ratio']:.1%} × {cap['cost_of_equity']:.0%}",
     f"${a['capital_cost']:,.2f}", "business"),
    ("HQLA", f"{S.usd(a['ucl'])} × {liq['lcr_outflow_unused_card_lines'] if a['hqla'] else 0:.0%}", S.usd(a["hqla"]), "regulatory"),
    ("Liquidity cost", f"{S.usd(a['hqla'])} × {liq['negative_carry']:.2%}", f"${a['liquidity_cost']:,.2f}", "business"),
    ("Carrying cost", f"capital cost on the unused part ${a['capital_cost_unused']:,.2f} + liquidity ${a['liquidity_cost']:,.2f}",
     f"${a['carrying_cost']:,.2f}", "business"),
    ("Expected drawdown loss", f"PD {a['pd_12m']:.2%} × LGD {a['lgd']:.0%} × LEQ {a['leq']:.2f} ({a['leq_source']}) × {S.usd(a['ucl'])}"
     if pd.notna(a["pd_12m"]) else "no PD at the reporting date", f"${a['drawdown_el']:,.2f}", "workbook"),
    ("Total unused-line cost", "carrying cost + drawdown loss", f"${a['total_unused_line_cost']:,.2f}", "derived"),
    ("Card profit (module)", f"card_net {S.signed(a['card_net'])} + old capital {S.usd(a['old_capital_cost'])} − new capital "
     f"${a['capital_cost']:,.2f} − liquidity ${a['liquidity_cost']:,.2f}", S.signed(a["card_profit"]), "derived"),
]
st.markdown("<table><tr><th>Item</th><th>Formula</th><th>Value</th><th>Type</th></tr>" + "".join(
    f"<tr><td>{i}</td><td>{fml}</td><td><b>{v}</b></td><td>{Y.vt(k)}</td></tr>" for i, fml, v, k in lines)
    + "</table>", unsafe_allow_html=True)

# ---------------------------------------------------- transactor test
st.divider()
Y.band("Regulatory transactor test (12 of 12) - month by month")
m = S.monthly_for(S.dataset(), acct)
if len(m):
    zero = m["Statement Balance"] <= 0.005
    paid = m["Paid In Full Indicator"].astype(bool) & ~zero
    promo = (m["Promotional Balance"] > 0) | (m["Plan Balance"] > 0)
    m["Result"] = np.where(promo, "fails - plan or promotional balance",
                           np.where(zero, "passes - nothing due ($0 statement)",
                                    np.where(paid, "passes - paid in full", "fails - not paid in full")))
    show = m[["Cycle Month", "Credit Limit", "Statement Balance", "Payment Made", "Paid In Full Indicator",
              "Promotional Balance", "Plan Balance", "Result"]]
    st.dataframe(show, width="stretch", hide_index=True)
st.markdown(f"**Result:** {X.RW_BASIS_LABELS.get(a['rw_basis'], a['rw_basis'])} → **{a['rw']:.0%}**. "
            f"Separately, the segmentation rule counts {int(a['cycles_paid_in_full_12m'] + a['cycles_zero_statement_12m'])} "
            f"of 12 cycles paid in full or nothing due (needs {cfg['segments']['rules']['transactors']['paid_in_full_months_min']}).")

# ---------------------------------------------------- rules
st.divider()
Y.band("Screen and segment rules - met / not met, with this account's value and the threshold")
trace = SG.rule_trace(f.loc[[acct]], cfg)
sc_rows = [(SG.SCREEN_LABELS[k].format(**cfg["screen"]), "✅" if bool(a[f"met:{k}"]) else "❌")
           for k in SG.SCREEN_LABELS]
st.dataframe(pd.DataFrame(sc_rows, columns=["Screen criterion", "Met"]), width="stretch", hide_index=True)
rows = []
for k, (val, thr, met) in trace.items():
    seg_key = k.split(".")[0]
    v = val.iloc[0]
    rows.append({"Segment": S.seg_label(seg_key), "Rule": SG.RULE_LABELS[k].format(**cfg["segments"]["rules"][seg_key]),
                 "This account": v if isinstance(v, str) else ("n/a" if pd.isna(v) else f"{float(v):,.4g}"),
                 "Threshold": "" if (isinstance(thr, float) and np.isnan(thr)) else f"{thr:,.4g}",
                 "Met": "✅" if bool(met.iloc[0]) else "❌"})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
if a["rule_segment"] == "dormant":
    st.caption("Dormant confirmation signals (informational): card not activated "
               f"{'yes' if a['confirm_card_not_activated'] else 'no'} · card due for reissue within 12 months "
               f"{'yes' if a['confirm_card_due_for_reissue'] else 'no'} · no digital sessions "
               f"{'yes' if a['confirm_no_digital_sessions'] else 'no'}")

# ---------------------------------------------------- recommendation
st.divider()
Y.band("Recommended action, reason code and notices")
if t is None:
    st.write("No recommendation: the account is outside the module's scope "
             + ("(protected customer)." if a.get("protected", False) else "(not screened)."))
else:
    st.markdown(
        f"- **Recommended:** {t['recommended_levers'].replace('_', ' ')}"
        + (" - **pending approval (B6)**" if t["pending_approval"] else "") + "\n"
        f"- **Line action:** {t['line_action']}" + (f" - new line {S.usd(t['new_line'])} (cut {S.usd(t['cut'])})"
                                                   if t["line_action"] == "decrease" else "") + "\n"
        f"- **Reason code:** {t['reason_code'] or 'none'} ({t['all_reason_codes'] or 'none'})\n"
        f"- **Notice:** {t['notice'] or 'none'}\n"
        + (f"- {cfg['treatment']['fee_restriction_text']}\n" if t["fee_restriction_45_days"] else "")
        + (f"- {cfg['treatment']['fcra_flag_text']}\n" if t["fcra_score_disclosure_check"] else "")
        + f"- **Pilot cell:** {t['pilot_cell']}")
    Y.band("ML credit-limit model - second opinion only")
    st.markdown(f"- **ML action:** {t['ml_action'] if pd.notna(t['ml_action']) else 'no score'}"
                + (f" ({t['ml_primary_reason']})" if pd.notna(t.get('ml_primary_reason')) else "") + "\n"
                f"- **Agreement with the module:** **{t['ml_agreement']}**\n"
                "- Never a decision input. Its treatment fairness test fails the four-fifths rule in several metros "
                "(see Regulatory settings).")
    Y.band("Other worklists this customer is in")
    st.write(t["review_together"] or "None of L1, L3 or L5 - no review-together flag.")

# ---------------------------------------------------- review notes
notes = [f"# Review notes - account {acct}", "", "**Review notes, not an approval record.**", "",
         f"Dataset: {S.info()['label']}", f"Assumption label: {S.LABEL}", "",
         f"- Segment: {S.seg_label(a['rule_segment'])} (screened: {bool(a['screened'])})",
         f"- Line {S.usd(a['limit_current'])}, balance {S.usd(a['balance_current'])}, unused {S.usd(a['ucl_current'])}",
         f"- Risk weight {a['rw']:.0%}: {X.RW_BASIS_LABELS.get(a['rw_basis'], a['rw_basis'])}",
         f"- Carrying cost ${a['carrying_cost']:,.2f}; drawdown loss ${a['drawdown_el']:,.2f}; total ${a['total_unused_line_cost']:,.2f} a year",
         f"- Card profit (module) {S.signed(a['card_profit'])} a year"]
if t is not None:
    notes += [f"- Recommended: {t['recommended_levers']}" + (" (pending approval)" if t["pending_approval"] else ""),
              f"- Reason code: {t['reason_code']}; notice: {t['notice']}",
              f"- ML: {t['ml_action']} ({t['ml_agreement']}); other worklists: {t['review_together'] or 'none'}",
              f"- Pilot cell: {t['pilot_cell']}"]
notes += ["", G.COMPLIANCE_NOTE, "Expected values under illustrative assumptions; pilot with a holdout before acting."]
st.download_button("Download review notes (not an approval record)", "\n".join(notes).encode("utf-8"),
                   file_name=f"review_notes_{acct}.md", mime="text/markdown")
