import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import segments as SG, exposure as X, levers as L  # noqa: E402

S.header("🔎 Customer evidence")
cfg = S.cfg()
f = S.frame()
tr = S.treatment()


def examples(seg: str) -> dict:
    """Typical (nearest the segment's median card profit), borderline (card
    profit nearest $0), limit-cut and review-together accounts of a segment."""
    g = f[f["screened"] & (f["rule_segment"] == seg)]
    if not len(g):
        return {}
    out = {"typical": (g["card_profit"] - g["card_profit"].median()).abs().idxmin(),
           "borderline": g["card_profit"].abs().idxmin()}
    cut = tr[(tr["segment"] == seg) & tr["line_action"].eq("decrease")]
    if len(cut):
        out["limit cut"] = cut["cut"].idxmax()
    rt = tr[(tr["segment"] == seg) & (tr["review_together"] != "")]
    if len(rt):
        out["review together"] = rt.index[0]
    return out


def recommendation(a: pd.Series, t: pd.Series | None) -> tuple[str, bool]:
    """The recommendation in plain language, from the treatment row."""
    if a.get("protected", False):
        return (f"No action: protected customer ({a['suppression_reason']}). The system's suppression applies "
                "before anything else.", True)
    if t is None:
        return ("No action: outside scope - the card is not losing money with a large unused line.", True)
    levers = [] if t["recommended_levers"] == "none" else t["recommended_levers"].split("; ")
    if not levers:
        return ("No action this time: the account is in scope but not selected in the Base plan.", True)
    rb = cfg["treatment"]["reason_by_lever"]
    parts = []
    for lv in levers:
        code = rb[lv]
        rule = cfg["treatment"]["reason_codes"][code]
        notice = "required" if rule["adverse_action_notice"] else "not required"
        wait = " (awaiting your decision)" if L.pending(cfg, lv) else ""
        if lv in ("line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"):
            what = f"Reduce limit from {S.usd(a['limit_current'])} to {S.usd(t['new_line'])}"
        elif lv == "dormant_closure":
            what = "Close the card if the wake-up campaign gets no response"
        elif lv == "engagement_campaign":
            what = "Offer a wake-up (engagement) campaign"
        elif lv == "suppress_automatic_increases":
            what = "Stop automatic limit increases"
        else:
            what = "Do not reissue the card when it expires"
        parts.append(f"{what}{wait}. Reason: {G.REASON_PLAIN[code]}. Adverse-action notice: {notice}.")
    return " ".join(parts), False


# ---------------------------------------------------- choose
c1, c2, c3 = st.columns([2, 2, 3])
segs = [k for k in cfg["segments"]["order"] if (f["screened"] & (f["rule_segment"] == k)).any()]
seg = c1.selectbox("Group (accounts in scope)", segs + ["not screened"],
                   format_func=lambda k: "Not in scope" if k == "not screened" else S.seg_label(k))
ex = examples(seg) if seg != "not screened" else {}
pick = c2.radio("Example", list(ex) + ["choose an account"]) if ex else "choose an account"
pool = f.index[f["screened"] & (f["rule_segment"] == seg)] if seg != "not screened" else f.index[~f["screened"]]
if pick == "choose an account":
    acct = c3.selectbox("Account (masked)", list(pool[:2000]))
else:
    acct = ex[pick]
    c3.markdown(f"**Account:** `{acct}`  \n{pick}")
a = f.loc[acct]
t = tr.loc[acct] if acct in tr.index else None

# 1. the recommendation, in plain language
text, none = recommendation(a, t)
Y.headline(f"{S.seg_label(a['rule_segment'])}" + ("" if a["screened"] else " (rule group only - not in scope)")
           + f" · {a['customer_segment']} customer · {a['metro']}")
Y.recommendation(text, none)
st.write("")

# 2. three key facts
Y.cards([
    ("Unused amount", S.usd(a["ucl_current"]), f"of a {S.usd(a['limit_current'])} limit; balance "
     f"{S.usd(a['balance_current'])}", Y.BLUE, "The limit minus the balance at the reporting date."),
    ("Annual cost to the bank of the unused line", f"${a['total_unused_line_cost']:,.2f}",
     f"${a['carrying_cost']:,.2f} holding + ${a['drawdown_el']:,.2f} expected losses", Y.RED, S.define("unused_cost")),
    ("Drawdown risk", f"${a['drawdown_el']:,.2f} a year",
     f"{'imputed ' if a['pd_imputed'] else ''}PD {a['pd_used']:.2%} · {a['leq']:.0%} of the unused line drawn "
     "before default", Y.AMBER, S.define("drawdown")),
], dominant=None)
S.cap(f"Card profit under the assumed capital rules: {S.signed(a['card_profit'])} a year"
      + (f" · pilot cell: {t['pilot_cell']}" if t is not None else ""))

# review buttons -> review notes (not an approval record)
reviews = st.session_state.setdefault("reviews", {})
st.write("")
r1, r2 = st.columns([2, 3])
prev = reviews.get(acct, {})
opts = ["Agree", "Disagree", "Need more information"]
# Widget state lives under these keys; a review given earlier in the session
# is put back when the account is shown again.
for k, v in [(f"review_{acct}", prev.get("review")), (f"note_{acct}", prev.get("note", ""))]:
    if k not in st.session_state and v is not None:
        st.session_state[k] = v
choice = r1.radio("Your review of this recommendation", opts, horizontal=True, key=f"review_{acct}", index=None)
note = r2.text_input("Note (optional)", key=f"note_{acct}")
if choice:
    reviews[acct] = {"review": choice, "note": note, "recommendation": text}


def notes_for(acct_id: str, a: pd.Series, t: pd.Series | None) -> list[str]:
    rv = reviews.get(acct_id)
    rec, _ = recommendation(a, t)
    out = [f"## Account {acct_id}", "",
           f"- Group: {S.seg_label(a['rule_segment'])} (in scope: {bool(a['screened'])})",
           f"- Recommendation: {rec}",
           f"- Review: {rv['review'] if rv else 'not reviewed'}" + (f" - {rv['note']}" if rv and rv['note'] else ""),
           f"- Line {S.usd(a['limit_current'])}, balance {S.usd(a['balance_current'])}, unused {S.usd(a['ucl_current'])}",
           f"- Risk weight {a['rw']:.0%}: {X.RW_BASIS_LABELS.get(a['rw_basis'], a['rw_basis'])}",
           f"- Holding cost ${a['carrying_cost']:,.2f}; expected drawdown loss ${a['drawdown_el']:,.2f}; total "
           f"${a['total_unused_line_cost']:,.2f} a year",
           f"- Card profit under the assumed capital rules {S.signed(a['card_profit'])} a year"]
    if t is not None:
        out += [f"- Reason codes: {t['all_reason_codes'] or 'none'}; notice: {t['notice'] or 'none'}",
                f"- Compliance flags: {t['compliance_flags'] or 'none'}",
                f"- Other worklists: {t['review_together'] or 'none'}; pilot cell: {t['pilot_cell']}"]
    return out + [""]


head = ["# Review notes", "", "**Review notes, not an approval record.**", "", f"Dataset: {S.info()['label']}",
        f"Assumption label: {S.LABEL}", ""]
tail = [G.COMPLIANCE_NOTE, "Expected values under illustrative assumptions; pilot with a holdout before acting."]
d1, d2 = st.columns(2)
d1.download_button("Download review notes for this account (not an approval record)",
                   "\n".join(head + notes_for(acct, a, t) + tail).encode("utf-8"),
                   file_name=f"review_notes_{acct}.md", mime="text/markdown")
if reviews:
    body = []
    for k in reviews:
        if k in f.index:
            body += notes_for(k, f.loc[k], tr.loc[k] if k in tr.index else None)
    d2.download_button(f"Download review notes for all {len(reviews)} reviewed accounts (not an approval record)",
                       "\n".join(head + body + tail).encode("utf-8"), file_name="review_notes_session.md",
                       mime="text/markdown")

# ---------------------------------------------------- details
st.write("")
names = ["Calculation trace", "Transactor test, month by month", "Rules met / not met", "Other worklists"]
tab = dict(zip(names, st.tabs(names)))
cap, liq = cfg["capital"], cfg["liquidity"]
with tab["Calculation trace"]:
    pd_txt = f"{a['pd_used']:.2%}" + (" (imputed: segment average, no PD at the reporting date)" if a["pd_imputed"] else "")
    leq_m = "n/a" if pd.isna(a["leq_measured"]) else f"{a['leq_measured']:.3f}"
    lines = [
        ("Unused line (UCL)", "average of max(limit − balance, 0) over 12 cycles", S.usd(a["ucl"]), "measured"),
        ("Balance", "average ending balance over 12 cycles (after the month's payment)", S.usd(a["balance"]), "measured"),
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
        ("Cost of holding (carrying cost)", f"capital cost on the unused part ${a['capital_cost_unused']:,.2f} + liquidity "
         f"${a['liquidity_cost']:,.2f}", f"${a['carrying_cost']:,.2f}", "business"),
        ("PD (annual)", "Table8 PD 12 Month at the reporting date; segment average if missing (B1)", pd_txt, "measured"),
        ("LEQ - account (Behavioral CCF)", "Table9 at the reporting date", leq_m, "measured"),
        ("LEQ - workbook segment", "the reference workbook's LEQ for this segment", f"{a['leq_workbook']:.3f}", "workbook"),
        ("LEQ in use", a["leq_source"], f"{a['leq']:.3f}", "workbook"),
        ("Expected drawdown loss", f"PD {a['pd_used']:.2%} × LGD {a['lgd']:.0%} × LEQ {a['leq']:.2f} × {S.usd(a['ucl'])}",
         f"${a['drawdown_el']:,.2f}", "workbook"),
        ("Total unused-line cost", "carrying cost + drawdown loss", f"${a['total_unused_line_cost']:,.2f}", "derived"),
        ("Fixed cost", f"{cfg['costs']['fixed_cost_basis']} (engine allocation ${a['fixed_cost_engine']:,.2f})",
         f"${a['fixed_cost']:,.2f}", "measured"),
        ("Card profit under the assumed capital rules", f"card_net {S.signed(a['card_net'])} + old capital "
         f"{S.usd(a['old_capital_cost'])} − new capital ${a['capital_cost']:,.2f} − liquidity ${a['liquidity_cost']:,.2f}"
         + (f" − fixed cost difference ${a['fixed_cost'] - a['fixed_cost_engine']:,.2f}"
            if abs(a["fixed_cost"] - a["fixed_cost_engine"]) > 0.005 else ""),
         S.signed(a["card_profit"]), "derived"),
    ]
    if S.analyst():
        S.md("<table><tr><th>Item</th><th>Formula</th><th>Value</th><th>Type</th></tr>" + "".join(
            f"<tr><td>{i}</td><td>{fml}</td><td><b>{v}</b></td><td>{Y.vt(k)}</td></tr>" for i, fml, v, k in lines)
            + "</table>", unsafe_allow_html=True)
    else:
        st.dataframe(pd.DataFrame([(i.strip(), v) for i, _, v, _ in lines], columns=["Item", "Value"]),
                     width="stretch", hide_index=True)
with tab["Transactor test, month by month"]:
    m = S.monthly_for(S.dataset(), acct)
    if len(m):
        zero = m["Statement Balance"] <= 0.005
        paid = m["Paid In Full Indicator"].astype(bool) & ~zero
        promo = (m["Promotional Balance"] > 0) | (m["Plan Balance"] > 0)
        m["Result"] = np.where(promo, "fails - plan or promotional balance",
                               np.where(zero, "passes - nothing due ($0 statement)",
                                        np.where(paid, "passes - paid in full", "fails - not paid in full")))
        cols = ["Cycle Month", "Credit Limit", "Statement Balance", "Payment Made", "Paid In Full Indicator",
                "Promotional Balance", "Plan Balance", "Result"]
        st.dataframe(m[cols if S.analyst() else ["Cycle Month", "Statement Balance", "Payment Made", "Result"]],
                     width="stretch", hide_index=True)
    S.md(f"**Result:** {X.RW_BASIS_LABELS.get(a['rw_basis'], a['rw_basis'])} → **{a['rw']:.0%}** risk weight. "
         f"Separately, the group rule counts {int(a['cycles_paid_in_full_12m'] + a['cycles_zero_statement_12m'])} "
         f"of 12 cycles paid in full or nothing due (needs {cfg['segments']['rules']['transactors']['paid_in_full_months_min']}).")
with tab["Rules met / not met"]:
    trace = SG.rule_trace(f.loc[[acct]], cfg)
    sc_rows = [(SG.SCREEN_LABELS[k].format(**cfg["screen"]), "✅" if bool(a[f"met:{k}"]) else "❌")
               for k in SG.SCREEN_LABELS]
    st.dataframe(pd.DataFrame(sc_rows, columns=["In-scope test", "Met"]), width="stretch", hide_index=True)
    rows = []
    for k, (val, thr, met) in trace.items():
        seg_key = k.split(".")[0]
        v = val.iloc[0]
        rows.append({"Group": S.seg_label(seg_key),
                     "Rule": SG.RULE_LABELS[k].format(**cfg["segments"]["rules"][seg_key]),
                     "This account": v if isinstance(v, str) else ("n/a" if pd.isna(v) else f"{float(v):,.4g}"),
                     "Threshold": "" if (isinstance(thr, float) and np.isnan(thr)) else f"{thr:,.4g}",
                     "Met": "✅" if bool(met.iloc[0]) else "❌"})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if a["rule_segment"] == "dormant":
        S.cap("Unused-card confirmation signals (informational): card not activated "
              f"{'yes' if a['confirm_card_not_activated'] else 'no'} · card due for reissue within 12 months "
              f"{'yes' if a['confirm_card_due_for_reissue'] else 'no'} · no digital sessions "
              f"{'yes' if a['confirm_no_digital_sessions'] else 'no'}")
with tab["Other worklists"]:
    if t is None:
        st.write("Outside the module's scope.")
    else:
        st.write(t["review_together"] or "None of L1, L3 or L5 - no review-together flag.")
        if t["fee_restriction_45_days"]:
            S.cap(cfg["treatment"]["fee_restriction_text"])
        if t["fcra_score_disclosure_check"]:
            S.cap(cfg["treatment"]["fcra_flag_text"])
S.caveat()
