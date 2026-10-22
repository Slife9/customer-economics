"""Standard layout for every lever page (B2) and the customer drill-down (B3).

Each lever page declares a LeverSpec; this module renders the same eight
sections for all six levers:

  1 What this lever does         5 What-if explorer (session only)
  2 Who is in scope              6 How it's calculated
  3 What it could be worth       7 Regulation & safeguards
  4 Assumptions (read-only)      8 Customer drill-down + admin review notes

Every number comes from the engine: SizeResult (scenarios, inputs,
assumptions) and the lever module's own functions - value_scenarios(),
calculation_steps(), customer_contributions(), customer_trace() and
selection_rules(). Nothing here re-implements a lever formula, so the page
can never disagree with the engine (audit_lever_estimates.py checks that
contributions sum to the components and steps equal them).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd
import streamlit as st

from app.lib import customer_workup as CW
from app.lib import lever_ui as UI
from app.lib import nav
from engine.levers import assumptions as ASSUME

K = "Masked Customer Number"
REVIEW_KEY = "review_notes"
DECISIONS = ("Agree", "Disagree", "Needs more information")

# Combinations an admin should look at together. A flag only - no
# prioritisation rule is implied or applied.
JOINT_REVIEW = [
    (("L2", "INCREASE_LIMIT"), ("L3", None),
     "Limit increase and a reprice at the same time - the customer would see both changes."),
    (("L1", "PILOT_ALIGNED_ANNUAL_FEE"), ("L5", None),
     "A new annual fee for a high-value customer already showing a leave signal."),
    (("L2", "DECREASE_LIMIT"), ("L5", None),
     "Cutting the line of a high-value customer already showing a leave signal."),
    (("L3", None), ("L5", None),
     "Repricing a high-value customer already showing a leave signal."),
]


@dataclass
class Slider:
    key: str
    label: str
    min: float = 0.0
    max: float = 1.0
    step: float = 0.01
    kind: str = "float"   # float | int | bool


@dataclass
class LeverSpec:
    code: str
    module: Any
    what_it_does: str
    scope_rules: list
    regulation: list                       # [(requirement, citation)]
    sliders: list = field(default_factory=list)
    key_metric: tuple | None = None        # (column, label) for sorting / display
    signal_col: str | None = None          # comma-separated signals column, for a filter
    per_customer: bool = True              # False: valued at channel/portfolio level (L6)
    extras: Callable | None = None         # (size, result) -> None
    change: Callable | None = None         # (row, size, assumptions) -> None
    customer_extra: Callable | None = None  # (row, result) -> None, e.g. L2's ML comparison
    rules: Callable | None = None          # (row, result) -> rules; default module.selection_rules(row)
    unpriced: bool = False                 # L5
    notices: list = field(default_factory=list)


# ---------------------------------------------------------------- data access

def _memo(result: dict) -> dict:
    memo = st.session_state.get("_lever_memo")
    if memo is None or memo.get("_rid") != id(result):
        memo = {"_rid": id(result)}
        st.session_state["_lever_memo"] = memo
    return memo


def drill_rows(spec: LeverSpec, result: dict) -> pd.DataFrame:
    """The lever's worklist merged with the customer view (left join on the
    masked id; worklist columns win on name clashes)."""
    memo = _memo(result)
    key = ("rows", spec.code)
    if key not in memo:
        wl = result["worklists"][spec.code]
        cv = result["customer_view"]
        cv_cols = [c for c in cv.columns if c == K or c not in wl.columns]
        memo[key] = wl.merge(cv[cv_cols], on=K, how="left").reset_index(drop=True)
    return memo[key]


def contributions(spec: LeverSpec, result: dict, size) -> pd.DataFrame | None:
    if not spec.per_customer or not size.has_scenarios:
        return None
    memo = _memo(result)
    key = ("contrib", spec.code)
    if key not in memo:
        try:
            memo[key] = spec.module.customer_contributions(
                drill_rows(spec, result), size.inputs, size.assumptions_used, "base")
        except KeyError as e:
            # A results bundle exported before this field existed - say so
            # rather than show a silently wrong per-customer figure.
            memo[key] = None
            memo[("missing", spec.code)] = str(e)
    if memo.get(("missing", spec.code)):
        st.info(f"Per-customer figures need a field this results bundle does not carry "
                f"({memo[('missing', spec.code)]}). Re-export the bundle with the current "
                f"engine to see them; the lever totals above are unaffected.")
    return memo[key]


# ---------------------------------------------------------------- sections 1-7

def render_header(spec: LeverSpec, result: dict) -> None:
    st.markdown(f"**What this lever does.** {spec.what_it_does}")
    UI.page_link(nav.PLAYBOOK, label=f"{spec.code} in the Lever Playbook", icon="📖")


def render_scope(spec: LeverSpec, result: dict) -> None:
    st.subheader("Who is in scope")
    wl = result["worklists"][spec.code]
    counts = wl["action"].value_counts().rename_axis("Recommended action").reset_index(name="Customers")
    c1, c2 = st.columns([2, 3])
    c1.metric("Customers in scope", f"{len(wl):,}")
    c1.dataframe(counts, hide_index=True, width="stretch")
    with c2:
        st.markdown("**Selection rules, in plain English**")
        for r in spec.scope_rules:
            st.markdown(f"- {r}")


def render_value(spec: LeverSpec, result: dict, size) -> None:
    st.subheader("What it could be worth")
    UI.value_summary(size, unpriced=spec.unpriced)
    if size.has_scenarios:
        if any(c["basis"] == "assumption" for c in size.scenarios["base"]["components"].values()):
            st.caption(f"🧪 Components tagged **{UI.PILOT_TAG}** depend on a customer response "
                       f"not yet observed. Treat them as a hypothesis for a pilot, not a forecast.")
        if spec.extras:
            spec.extras(size, result)


def _flatten_assumptions(a: dict) -> pd.DataFrame:
    rows = []
    for k, v in a.items():
        if isinstance(v, dict) and any(s in v for s in ASSUME.SCENARIOS):
            rows.append({"Assumption": k, "Low": v["low"], "Base": v["base"], "High": v["high"]})
        elif isinstance(v, dict):
            for kk, vv in v.items():
                rows.append({"Assumption": f"{k}.{kk}", "Low": None, "Base": vv, "High": None})
        else:
            rows.append({"Assumption": k, "Low": None, "Base": v, "High": None})
    return pd.DataFrame(rows)


def render_assumptions(spec: LeverSpec, result: dict, size) -> None:
    st.subheader("Assumptions (read-only)")
    if not size.assumptions_used:
        st.caption("No assumptions recorded for this result (pre-rebuild valuation).")
        return
    st.dataframe(_flatten_assumptions(size.assumptions_used).astype(str).replace({"None": "", "nan": ""}),
                 hide_index=True, width="stretch")
    sha = result.get("lever_assumptions_sha256")
    st.caption(f"From `engine/config/lever_assumptions.json`"
               + (f" (SHA-256 `{str(sha)[:16]}…`)" if sha else "")
               + ". Business assumptions to be replaced by the bank's own policy or pilot evidence.")


def render_whatif(spec: LeverSpec, result: dict, size) -> None:
    st.subheader("What-if explorer")
    st.caption("⚠️ **Exploration only; does not change the configured assumptions.** Moves "
               "recompute this lever with the engine's own valuation function, in this session only.")
    if not size.has_scenarios or not spec.sliders:
        st.caption("Not available for this result.")
        return
    a = size.assumptions_used
    overrides = {}
    cols = st.columns(min(3, len(spec.sliders)))
    for n, sl in enumerate(spec.sliders):
        base = ASSUME.pick(a[sl.key], "base")
        with cols[n % len(cols)]:
            wkey = f"whatif_{spec.code}_{sl.key}"
            if sl.kind == "bool":
                overrides[sl.key] = st.checkbox(sl.label, value=bool(base), key=wkey)
            elif sl.kind == "int":
                overrides[sl.key] = st.slider(sl.label, int(sl.min), int(sl.max), int(base),
                                              int(sl.step), key=wkey)
            else:
                overrides[sl.key] = st.slider(sl.label, float(sl.min), float(sl.max), float(base),
                                              float(sl.step), key=wkey)
    a2 = ASSUME.with_overrides(a, overrides)
    what = spec.module.value_scenarios(size.inputs, a2)["base"]
    conf = size.scenarios["base"]
    delta = what["total_usd"] - conf["total_usd"]
    m1, m2 = st.columns(2)
    m1.metric("Configured base", f"${conf['total_usd']:,.0f}")
    m2.metric("What-if", f"${what['total_usd']:,.0f}", f"{delta:+,.0f}")
    comp = pd.DataFrame([{"Component": k.replace("_", " "),
                          "Configured base": conf["components"][k]["value_usd"],
                          "What-if": v["value_usd"]} for k, v in what["components"].items()
                         if k in conf["components"]])
    st.dataframe(comp.style.format({"Configured base": "${:,.0f}", "What-if": "${:,.0f}"}),
                 hide_index=True, width="stretch")


def render_calculation(spec: LeverSpec, result: dict, size) -> None:
    with st.expander("How it's calculated - every formula with this portfolio's numbers"):
        if not size.has_scenarios:
            st.caption("Not available for this result (pre-rebuild valuation).")
            return
        steps = spec.module.calculation_steps(size.inputs, size.assumptions_used, "base")
        if not steps:
            st.caption("Not computable for this portfolio - see the value section for why.")
            return
        st.dataframe(pd.DataFrame(steps).rename(columns={
            "component": "Component", "formula": "Formula", "substituted": "With this portfolio's numbers",
            "value": "Value (base)"}).style.format({"Value (base)": "${:,.2f}"}),
            hide_index=True, width="stretch")
        st.caption(f"Base total = sum of components = **${size.scenarios['base']['total_usd']:,.2f}**. "
                   f"Each row is computed by the engine; `audit/audit_lever_estimates.py` checks that "
                   f"these steps equal the engine's components.")


def render_regulation(spec: LeverSpec) -> None:
    st.subheader("Regulation & safeguards")
    st.caption("⚖️ **To be confirmed by compliance.** Citations follow "
               "`docs/LEVER_METHODOLOGY.md` and `governance/REGULATORY_RULEBOOK.md`.")
    st.dataframe(pd.DataFrame(spec.regulation, columns=["Requirement", "Citation"]),
                 hide_index=True, width="stretch")


def render_overview(spec: LeverSpec, result: dict) -> None:
    size = result["sizes"][spec.code]
    render_header(spec, result)
    st.divider()
    render_scope(spec, result)
    st.divider()
    render_value(spec, result, size)
    st.divider()
    render_assumptions(spec, result, size)
    st.divider()
    render_whatif(spec, result, size)
    render_calculation(spec, result, size)
    st.divider()
    render_regulation(spec)


# ---------------------------------------------------------------- section 8

def _other_levers(result: dict, cid: str) -> list:
    hits = []
    for code, wl in result["worklists"].items():
        m = wl[wl[K] == cid]
        if len(m):
            hits.append((code, str(m.iloc[0]["action"])))
    return hits


def _joint_flags(hits: list) -> list:
    have = {c: a for c, a in hits}
    flags = []
    for (c1, a1), (c2, a2), why in JOINT_REVIEW:
        if c1 in have and c2 in have and (a1 is None or have[c1] == a1) and (a2 is None or have[c2] == a2):
            flags.append(f"**{c1} + {c2}: review together.** {why}")
    return flags


def _rules_table(sr) -> None:
    if isinstance(sr, dict) and "rule_sets" in sr:
        st.markdown(f"**Matched group:** `{sr['matched'] or 'none'}`")
        for name, rules in sr["rule_sets"].items():
            if name != sr["matched"]:
                continue
            st.dataframe(pd.DataFrame(rules).assign(met=lambda d: d["met"].map({True: "✅ met", False: "❌ not met"}))
                         .rename(columns={"rule": "Rule", "threshold": "Threshold",
                                          "actual": "This customer", "met": "Result"}),
                         hide_index=True, width="stretch")
        st.caption(sr.get("precedence", ""))
        with st.expander("All rule sets for this lever, against this customer"):
            for name, rules in sr["rule_sets"].items():
                st.markdown(f"*{name}*")
                st.dataframe(pd.DataFrame(rules).assign(met=lambda d: d["met"].map({True: "✅", False: "❌"})),
                             hide_index=True, width="stretch")
    else:
        st.dataframe(pd.DataFrame(sr).assign(met=lambda d: d["met"].map({True: "✅ met", False: "❌ not met"}))
                     .rename(columns={"rule": "Rule", "threshold": "Threshold",
                                      "actual": "This customer", "met": "Result"}),
                     hide_index=True, width="stretch")


def _protections(spec: LeverSpec, result: dict, row) -> None:
    st.markdown("**Protections and gates**")
    items = ["✅ Not suppressed: no hardship, accommodation plan or SCRA flag (suppressed "
             "customers never reach a lever)."]
    tenure_m = row.get("Customer Tenure Years", float("nan")) * 12
    if pd.notna(tenure_m) and tenure_m < 12:
        items.append(f"🛑 In the first year ({tenure_m:.0f} months): CARD Act blocks a rate "
                     f"increase (L3 excludes the account).")
    for n in spec.notices:
        items.append(f"📨 {n}")
    lever = result["levers"].get(spec.code)
    for g in getattr(lever, "gates", []) or []:
        items.append(f"🔒 {g}")
    items.append("⚖️ Fair lending: the recommendation must be consistent with how similar "
                 "customers are treated; see Governance & Fairness for the four-fifths tests.")
    for i in items:
        st.markdown(f"- {i}")


def _limitations() -> None:
    meta = st.session_state.get("bundle_metadata")
    if meta is not None:
        st.info("**Data limitations (pre-computed bundle):** raw transactions, cost-driver "
                "and account tables are not in the bundle, so the Full Economic Workup's "
                "Transaction Detail and per-activity cost breakdown show a notice instead. "
                "Everything else is the same analysis the bundle was exported with"
                + (f" ({meta.valuation_label})." if getattr(meta, "valuation_label", "") else "."))
    else:
        st.caption("Data: live engine run - every table is available.")


def _review_notes(spec: LeverSpec, cid: str, recommendation: str) -> None:
    st.markdown("**Admin review notes** - *review notes, not an approval or audit record*")
    with st.form(f"review_{spec.code}_{cid}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        reviewer = c1.text_input("Reviewer name", key=f"rv_name_{spec.code}")
        decision = c2.radio("Decision", DECISIONS, horizontal=True, key=f"rv_decision_{spec.code}")
        reason = st.text_area("Reason", key=f"rv_reason_{spec.code}")
        if st.form_submit_button("Add note"):
            if not reviewer.strip() or not reason.strip():
                st.warning("Add a reviewer name and a reason.")
            else:
                st.session_state.setdefault(REVIEW_KEY, []).append({
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "reviewer": reviewer.strip(), "lever": spec.code,
                    "masked_customer_id": cid, "recommendation": recommendation,
                    "decision": decision, "reason": reason.strip()})
                st.success("Note added to this session's review log.")
    notes = pd.DataFrame(st.session_state.get(REVIEW_KEY, []))
    if len(notes):
        mine = notes[notes["lever"] == spec.code]
        st.dataframe(mine, hide_index=True, width="stretch")
        st.download_button("Download review log (all levers, this session) as CSV",
                           notes.to_csv(index=False), "review_notes.csv", "text/csv",
                           key=f"dl_notes_{spec.code}_{cid}")
        st.caption("Kept in this browser session only - not stored, shared or approved anywhere.")


def render_customer(spec: LeverSpec, result: dict, size, cid: str) -> None:
    supp = result["suppressed"].suppressed
    if cid in set(supp[K]):
        reason = supp.set_index(K).loc[cid, "suppression_reason"]
        st.warning(f"**{cid} is a protected customer: {reason}.** Suppressed before any lever "
                   f"runs - no recommendation, no action, regardless of their economics.")
        return
    rows = drill_rows(spec, result)
    hit = rows[rows[K] == cid]
    if not len(hit):
        st.info(f"{cid} is not in {spec.code}'s population. Levers this customer does appear in: "
                + (", ".join(f"{c} ({a})" for c, a in _other_levers(result, cid)) or "none") + ".")
        return
    row = hit.iloc[0]
    st.markdown(f"### {cid}")
    tenure = row.get("Customer Tenure Years")
    st.caption(f"Segment **{row.get('Segment')}** · score band **{row.get('Credit Score Band')}** · "
               f"CEV band **{row.get('cev_band')}** · products **{int(row.get('products_held', 0))}** · "
               f"tenure **{'n/a' if pd.isna(tenure) else f'{tenure:.1f} years'}**")
    CW.render_relationship(result, cid)

    st.markdown("**Why this customer is here**")
    _rules_table(spec.rules(row, result) if spec.rules else spec.module.selection_rules(row))

    st.markdown(f"**Recommended action:** `{row['action']}` - {row.get('reason', '')}")
    if spec.change:
        a = size.assumptions_used
        if not a:
            a = ASSUME.load()[0][spec.code]
            st.caption("This result predates the valuation rebuild, so the proposed change "
                       "below uses the currently configured assumptions.")
        try:
            spec.change(row, size, a)
        except KeyError as e:
            st.info(f"Details of the proposed change need a field this results bundle does "
                    f"not carry ({e}). Re-export the bundle with the current engine.")

    st.markdown("**Calculation trace** - expected value under the base assumptions, "
                "not a prediction about this customer")
    trace = None
    if size.has_scenarios:
        try:
            trace = spec.module.customer_trace(row, size.inputs, size.assumptions_used, "base")
        except KeyError as e:
            st.info(f"This customer's trace needs a field this results bundle does not carry "
                    f"({e}). Re-export the bundle with the current engine.")
    if trace is not None:
        st.dataframe(pd.DataFrame(trace).rename(columns={
            "component": "Step", "formula": "Formula", "substituted": "With this customer's inputs",
            "value": "Value"}).style.format({"Value": "${:,.2f}"}, na_rep=""),
            hide_index=True, width="stretch")
    elif not size.has_scenarios:
        UI.pre_rebuild_notice(size)

    hits = _other_levers(result, cid)
    st.markdown("**Other levers this customer appears in**")
    others = [(c, a) for c, a in hits if c != spec.code]
    st.markdown(", ".join(f"`{c}` {a}" for c, a in others) if others else "None.")
    for f in _joint_flags(hits):
        st.warning(f)

    _protections(spec, result, row)
    if spec.customer_extra:
        spec.customer_extra(row, result)
    _limitations()
    CW.render_full_workup(result, cid)
    st.divider()
    _review_notes(spec, cid, str(row["action"]))


def render_drilldown(spec: LeverSpec, result: dict) -> None:
    size = result["sizes"][spec.code]
    rows = drill_rows(spec, result)
    contrib = contributions(spec, result, size)
    table = pd.DataFrame({
        "Masked customer ID": rows[K],
        "Segment": rows.get("Segment"),
        "Score band": rows.get("Credit Score Band").astype(str) if "Credit Score Band" in rows else None,
        "CEV band": rows.get("cev_band").astype(str) if "cev_band" in rows else None,
        "Recommended action": rows["action"],
        "Reason": rows.get("reason"),
    })
    if contrib is not None:
        table["Expected contribution (base)"] = contrib["total"].to_numpy()
    if spec.key_metric and spec.key_metric[0] in rows.columns:
        table[spec.key_metric[1]] = rows[spec.key_metric[0]].to_numpy()

    st.subheader("Worklist")
    if not spec.per_customer:
        st.caption("This lever is valued at channel level - there is no per-customer "
                   "contribution figure; the selected customer's inputs are shown against "
                   "the channel averages instead.")
    f1, f2, f3 = st.columns(3)
    search = f1.text_input("Search masked ID", key=f"dd_search_{spec.code}")
    actions = f2.multiselect("Action", sorted(table["Recommended action"].dropna().unique()),
                             key=f"dd_action_{spec.code}")
    segs = f3.multiselect("Segment", sorted(table["Segment"].dropna().astype(str).unique()),
                          key=f"dd_seg_{spec.code}")
    f4, f5, f6 = st.columns(3)
    bands = f4.multiselect("Score band", sorted(table["Score band"].dropna().unique()),
                           key=f"dd_band_{spec.code}")
    cevs = f5.multiselect("CEV band", sorted(table["CEV band"].dropna().unique()),
                          key=f"dd_cev_{spec.code}")
    sig_vals = []
    if spec.signal_col and spec.signal_col in rows.columns:
        all_sigs = sorted({s.strip() for v in rows[spec.signal_col].dropna() for s in str(v).split(",") if s.strip()})
        sig_vals = f6.multiselect("Signal", all_sigs, key=f"dd_sig_{spec.code}")
    mask = pd.Series(True, index=table.index)
    if search:
        mask &= table["Masked customer ID"].astype(str).str.contains(search.strip(), case=False, regex=False)
    if actions:
        mask &= table["Recommended action"].isin(actions)
    if segs:
        mask &= table["Segment"].astype(str).isin(segs)
    if bands:
        mask &= table["Score band"].isin(bands)
    if cevs:
        mask &= table["CEV band"].isin(cevs)
    if sig_vals:
        mask &= rows[spec.signal_col].fillna("").apply(lambda v: any(s in str(v) for s in sig_vals))
    sort_opts = []
    if contrib is not None:
        sort_opts += ["Expected contribution (base), high to low", "Expected contribution (base), low to high"]
    if spec.key_metric and spec.key_metric[1] in table.columns:
        sort_opts += [f"{spec.key_metric[1]}, high to low", f"{spec.key_metric[1]}, low to high"]
    view = table[mask]
    if sort_opts:
        sort = st.selectbox("Sort by", sort_opts, key=f"dd_sort_{spec.code}")
        col = sort.rsplit(",", 1)[0]
        view = view.sort_values(col, ascending=sort.endswith("low to high"))
    st.caption(f"Showing **{len(view):,}** of {len(table):,} customers in {spec.code}'s worklist.")
    fmt = {c: "${:,.2f}" for c in ("Expected contribution (base)",) if c in view.columns}
    st.dataframe(view.style.format(fmt) if len(view) <= 5000 else view,
                 hide_index=True, width="stretch", height=360)
    if st.button("Prepare CSV of this filtered view", key=f"dd_csv_{spec.code}"):
        buf = io.StringIO()
        view.to_csv(buf, index=False)
        st.download_button("Download filtered worklist CSV", buf.getvalue(),
                           f"{spec.code}_worklist_filtered.csv", "text/csv",
                           key=f"dd_csvdl_{spec.code}")

    st.divider()
    st.subheader("Selected customer")
    c1, c2 = st.columns(2)
    picks = view["Masked customer ID"].astype(str).head(1000).tolist()
    picked = c1.selectbox("Pick from the filtered view (first 1,000)", [""] + picks,
                          key=f"dd_pick_{spec.code}")
    typed = c2.text_input("…or type any masked ID (protected customers included)",
                          key=f"dd_typed_{spec.code}")
    cid = typed.strip() or picked
    if cid:
        render_customer(spec, result, size, cid)
    else:
        st.caption("Pick or type a customer to see why they are here, what is recommended, "
                   "and how their contribution is calculated.")
