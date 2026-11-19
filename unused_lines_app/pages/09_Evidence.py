import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unused_lines_app.lib import state as S, style as Y, guide as G  # noqa: E402
from engine.unused_lines import segments as SG, exposure as X, levers as L, strategies as ST  # noqa: E402

S.header("🔎 Customer evidence")
cfg = S.cfg()
f = S.frame()
tr = S.treatment()
defs = cfg["strategies"]["definitions"]
num_name = {d["number"]: d["name"] for d in defs.values()}
DECREASES = ("line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing")


def examples(seg: str) -> dict:
    """Typical (nearest the group's median card profit), borderline (card
    profit nearest $0), limit-cut and warning examples of a group."""
    g = f[f["screened"] & (f["rule_segment"] == seg)]
    if not len(g):
        return {}
    out = {"typical": (g["card_profit"] - g["card_profit"].median()).abs().idxmin(),
           "borderline": g["card_profit"].abs().idxmin()}
    cut = tr[(tr["segment"] == seg) & tr["line_action"].eq("decrease")]
    if len(cut):
        out["limit cut"] = cut["cut"].idxmax()
    w = tr[(tr["segment"] == seg) & tr["warning_required"]]
    if len(w):
        out["90-day warning"] = w.index[0]
    return out


def recommendation(a: pd.Series, t: pd.Series | None) -> list[tuple[str, str]] | str:
    """The recommendation as (field, value) rows, or a sentence when there is no action."""
    if a.get("protected", False):
        return (f"No action: protected customer ({a['suppression_reason']}). Protected customers are excluded from "
                "every action.")
    if t is None:
        return "No action: outside scope - the card does not lose money with a large unused line."
    levers = [] if t["recommended_levers"] == "none" else t["recommended_levers"].split("; ")
    if not levers:
        return "No action this time: the card is in scope but not selected in the Base plan."
    rb, rc = cfg["treatment"]["reason_by_lever"], cfg["treatment"]["reason_codes"]
    strat = [int(x) for x in t["strategies"].split("; ") if x]
    rows = [("Strategy", "; ".join(f"{n}. {num_name[n]}" for n in strat))]
    for lv in levers:
        key = ST.strategy_of(cfg, lv, a["rule_segment"])
        status = (ST.STATUS_LABELS[ST.step_status(cfg, defs[key[0]], next(s for s in defs[key[0]]["steps"]
                                                                              if s["key"] == key[1]))]
                  if key else "")
        if lv in DECREASES:
            what = f"Reduce the limit from {S.usd(a['limit_current'])} to {S.usd(t['new_line'])}"
        elif lv == "dormant_closure":
            what = "Close the card if it stays unused after the invite and the warning"
        elif lv == "engagement_campaign":
            what = "Invite: reactivation offer" if a["rule_segment"] == "dormant" else "Engagement offer"
        elif lv == "suppress_automatic_increases":
            what = "Stop automatic limit increases"
        else:
            what = "Do not reissue the card when it expires"
        code = rb[lv]
        rows.append(("Action", f"{what} ({status.lower()})" if status else what))
        rows.append(("  Reason code", f"{code} ({G.REASON_PLAIN[code]})"))
        rows.append(("  Notice required", "adverse-action notice within 30 days" if rc[code]["adverse_action_notice"]
                     else "no adverse-action notice"))
    if t["warning_required"]:
        rows.append(("90-day warning", f"required before any change: {cfg['warning']['notice_days']} days' notice with "
                                       "a choice (keep using the card, keep a lower limit, or close it); never a fee. "
                                       "Not yet sent."))
    if t["fee_restriction_45_days"]:
        rows.append(("After the cut", cfg["treatment"]["fee_restriction_text"]))
    return rows


# ---------------------------------------------------- choose
c1, c2, c3 = st.columns([2, 2, 3])
segs = [k for k in cfg["segments"]["order"] if (f["screened"] & (f["rule_segment"] == k)).any()]
seg = c1.selectbox("Group (cards in scope)", segs + ["not screened"],
                   format_func=lambda k: "Not in scope" if k == "not screened" else S.seg_label(k))
ex = examples(seg) if seg != "not screened" else {}
pick = c2.radio("Example", list(ex) + ["choose an account"]) if ex else "choose an account"
pool = f.index[f["screened"] & (f["rule_segment"] == seg)] if seg != "not screened" else f.index[~f["screened"]]
if pick == "choose an account":
    acct = c3.selectbox("Account (masked ID)", list(pool[:2000]))
else:
    acct = ex[pick]
    c3.markdown(f"**Account:** `{acct}`  \n{pick}")
a = f.loc[acct]
t = tr.loc[acct] if acct in tr.index else None

# 1. the recommendation card, first
Y.headline(f"Account {acct}: {S.seg_label(a['rule_segment'])}" + ("" if a["screened"] else " (rule group only - not in scope)"))
rec = recommendation(a, t)
if isinstance(rec, str):
    Y.recommendation(rec, none=True)
else:
    Y.recommendation(" · ".join(v for k, v in rec if k in ("Strategy",)) or "Recommendation")
    st.dataframe(pd.DataFrame([(k.strip(), v) for k, v in rec[1:]], columns=["", "Recommendation"]), width="stretch",
                 hide_index=True, column_config={"Recommendation": st.column_config.TextColumn(width="large")})
st.write("")

# 2. three key facts
Y.cards([
    ("Unused credit today", S.usd(a["now_ucl"]), f"of a {S.usd(a['limit_current'])} limit", Y.BLUE,
     "Today's limit minus the balance outstanding during the month."),
    ("Annual cost of the unused line", f"${a['total_unused_line_cost']:,.2f}",
     f"${a['carrying_cost']:,.2f} to hold + ${a['drawdown_el']:,.2f} expected drawdown loss (12-month average)", Y.RED,
     S.define("unused_cost")),
    ("Card profit", S.signed(a["card_profit"]), "a year, after all costs under the assumed rules", Y.AMBER,
     S.define("card_profit")),
])

# ---------------------------------------------------- the full calculation trace
cap, liq = cfg["capital"], cfg["liquidity"]
basis = {"midpoint": "average of the statement and after-payment balance", "after_payment": "after the month's payment"}[
    cfg["balance_basis"]["cost"]]
lines = [  # (analyst label, executive label, formula, value, value type)
    ("Unused line (UCL)", "Unused credit (12-month average)", f"limit − balance ({basis})", S.usd(a["ucl"]), "measured"),
    ("Balance", "Balance outstanding (12-month average)", basis, S.usd(a["balance"]), "measured"),
    ("Risk weight", "Risk weight", X.RW_BASIS_LABELS.get(a["rw_basis"], a["rw_basis"]), f"{a['rw']:.0%}", "regulatory"),
    ("RWA on the unused line", "Risk-weighted assets on the unused credit",
     f"{cap['ccf_unused_card_lines']:.0%} × {S.usd(a['ucl'])} × {a['rw']:.0%}", S.usd(a["rwa_unused"]), "regulatory"),
    ("Capital cost (unused part)", "Capital cost", f"× {cap['capital_ratio']:.1%} capital × {cap['cost_of_equity']:.0%} "
     "cost of equity", f"${a['capital_cost_unused']:,.2f}", "business"),
    ("Liquidity cost", "Liquidity cost", f"{S.usd(a['ucl'])} × {liq['lcr_outflow_unused_card_lines'] if a['hqla'] else 0:.0%} "
     f"× {liq['negative_carry']:.2%}", f"${a['liquidity_cost']:,.2f}", "business"),
    ("Carrying cost", "Cost to hold", "capital cost + liquidity cost", f"${a['carrying_cost']:,.2f}", "business"),
    ("PD (annual)", "Chance of default in a year", "the account's own" + (" (its group's average: none on file)"
                                                                          if a["pd_imputed"] else ""),
     f"{a['pd_used']:.2%}", "measured"),
    ("LGD", "Loss if default", "the account's own (portfolio average if missing)",
     f"{(a['lgd'] if pd.notna(a['lgd']) else cfg['workbook']['portfolio']['lgd']):.0%}", "measured"),
    ("LEQ in use", "Share of the line drawn before default", a["leq_source"] if S.analyst() else (
        "the reference model's estimate for the group" if "workbook" in a["leq_source"]
        else "the account's measured behaviour"), f"{a['leq']:.0%}", "workbook"),
    ("Expected drawdown loss", "Expected drawdown loss", "chance of default × loss if default × share drawn × unused",
     f"${a['drawdown_el']:,.2f}", "workbook"),
    ("Card profit under the assumed capital rules", "Card profit", f"engine card profit {S.signed(a['card_net'])} + old "
     f"capital {S.usd(a['old_capital_cost'])} − new capital ${a['capital_cost']:,.2f} − liquidity ${a['liquidity_cost']:,.2f}",
     S.signed(a["card_profit"]), "derived"),
    ("Today's unused line (actions)", "Unused credit today (actions are valued on it)", "today's limit − balance",
     S.usd(a["now_ucl"]), "measured"),
]
with st.expander("Full calculation trace", expanded=True):
    if S.analyst():
        S.md("<table><tr><th>Item</th><th>Formula</th><th>Value</th><th>Type</th></tr>" + "".join(
            f"<tr><td>{i}</td><td>{fml}</td><td><b>{v}</b></td><td>{Y.vt(k)}</td></tr>" for i, _, fml, v, k in lines)
            + "</table>", unsafe_allow_html=True)
    else:
        st.dataframe(pd.DataFrame([(p, fml, v) for _, p, fml, v, _ in lines], columns=["Item", "How", "Value"]),
                     width="stretch", hide_index=True)
with st.expander("Selection tests and group rules, met or not"):
    sc_rows = [(text, "✅" if bool(a[f"met:{k}"]) else "❌") for k, text in G.selection_tests(cfg)]
    st.dataframe(pd.DataFrame(sc_rows, columns=["Selection test", "Met"]), width="stretch", hide_index=True)
    trace = SG.rule_trace(f.loc[[acct]], cfg)
    rows = []
    for k, (val, thr, met) in trace.items():
        seg_key = k.split(".")[0]
        v = val.iloc[0]
        rows.append({"Group": S.seg_label(seg_key), "This account": v if isinstance(v, str) else (
            "n/a" if pd.isna(v) else f"{float(v):,.4g}"), "Threshold": "" if (isinstance(thr, float) and np.isnan(thr))
            else f"{thr:,.4g}", "Met": "✅" if bool(met.iloc[0]) else "❌"}
                    | ({"Rule": SG.RULE_LABELS[k].format(**cfg["segments"]["rules"][seg_key])} if S.analyst() else {}))
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    S.cap(f"Group rule: {G.group_rule(a['rule_segment'], cfg)}. A card joins the first group whose rule it meets.")
with st.expander("Risk weight: the payment record, month by month"):
    m = S.monthly_for(S.dataset(), acct)
    if len(m):
        zero = m["Statement Balance"] <= 0.005
        paid = m["Paid In Full Indicator"].astype(bool) & ~zero
        promo = (m["Promotional Balance"] > 0) | (m["Plan Balance"] > 0)
        m["Result"] = np.where(promo, "not paid in full: plan or promotional balance",
                               np.where(zero, "nothing due", np.where(paid, "paid in full", "not paid in full")))
        st.dataframe(m[["Cycle Month", "Credit Limit", "Statement Balance", "Payment Made", "Ending Balance", "Result"]],
                     width="stretch", hide_index=True)
    S.md(f"**Result:** {X.RW_BASIS_LABELS.get(a['rw_basis'], a['rw_basis'])} → **{a['rw']:.0%}** risk weight.")

if S.analyst():
    # review notes (not an approval record) and the other worklists
    reviews = st.session_state.setdefault("reviews", {})
    with st.expander("Analyst: review notes, other worklists, downloads", expanded=False):
        r1, r2 = st.columns([2, 3])
        prev = reviews.get(acct, {})
        for k, v in [(f"review_{acct}", prev.get("review")), (f"note_{acct}", prev.get("note", ""))]:
            if k not in st.session_state and v is not None:
                st.session_state[k] = v
        choice = r1.radio("Your review of this recommendation", ["Agree", "Disagree", "Need more information"],
                          horizontal=True, key=f"review_{acct}", index=None)
        note = r2.text_input("Note (optional)", key=f"note_{acct}")
        if choice:
            reviews[acct] = {"review": choice, "note": note}
        if t is not None:
            S.md(f"- Other worklists: {t['review_together'] or 'none of L1, L3, L5'}\n- Pilot cell: {t['pilot_cell']}\n"
                 f"- Compliance flags: {t['compliance_flags'] or 'none'}\n- Levers: {t['recommended_levers']}")
        text = "\n".join([f"# Review notes (not an approval record)", "", f"Account {acct}", ""]
                         + [f"- {k.strip()}: {v}" for k, v in (rec if not isinstance(rec, str) else [("Recommendation", rec)])]
                         + [f"- Review: {reviews.get(acct, {}).get('review', 'not reviewed')}", "", S.LABEL])
        st.download_button("Download review notes for this account", text.encode("utf-8"),
                           file_name=f"review_notes_{acct}.md", mime="text/markdown")
S.caveat()
