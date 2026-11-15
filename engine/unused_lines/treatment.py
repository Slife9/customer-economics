"""Treatment designer, compliance checks, fairness and timing (Stage 6).

Per account in scope, from the Base scenario's selection (levers.run):
    recommended lever(s), a mandatory reason code, the notice it triggers,
    the 45-day fee / penalty-rate restriction after a decrease, the ML
    model's view and an agreement flag (second opinion only, never an input),
    "review together" flags for the system's L1 / L3 / L5 worklists, and a
    pilot cell (seeded, stratified holdout).
Compliance text is a summary for discussion; to be confirmed by compliance.
No lever ever proposes an inactivity fee.

The ML model and the worklists come from the existing engine
(engine.run.build_pipeline), read only; the fairness test is the existing
engine.governance.fairness.four_fifths_test, called with three selections:
module decreases and closures, ML adverse actions, ML increases.
"""
from __future__ import annotations
import hashlib

import numpy as np
import pandas as pd

from . import levers as L

LINE_DECREASE_LEVERS = ["line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"]
ML_ADVERSE = ["DECREASE_UNUSED_EXPOSURE", "FREEZE_NO_INCREASE"]
ML_NO_VIEW = ["INSUFFICIENT_HISTORY", "NOT_ELIGIBLE", "MANUAL_REVIEW"]
ML_ACTIONS = ["INSUFFICIENT_HISTORY", "NOT_ELIGIBLE", "FREEZE_NO_INCREASE", "MANUAL_REVIEW",
              "DECREASE_UNUSED_EXPOSURE", "INCREASE", "MAINTAIN"]


def ml_rules_text() -> list[str]:
    """The ML model's cut rules, read from its own policy and code."""
    from engine.ml import decisions as MLDEC
    p, _ = MLDEC.load_policy()
    return [f"At most {p['maximum_percentage_reduction']:.0%} cut per account",
            f"At most {p['maximum_reduction_share_per_review']:.0%} of accounts cut per review",
            f"Each cut at least {1 - MLDEC.REDUCTION_CUT_FLOOR:.0%} of the line and at least "
            f"${p['minimum_reduction_amount']:,.0f}",
            f"Seven actions: {', '.join(ML_ACTIONS)}"]


def _hash_rank(keys, seed) -> np.ndarray:
    return np.array([int(hashlib.sha256(f"{seed}:{k}".encode()).hexdigest()[:12], 16) for k in keys], dtype=float)


def pilot_cells(f: pd.DataFrame, mask: pd.Series, cfg: dict) -> pd.Series:
    """Seeded holdout, stratified by segment: within each segment the first
    holdout_share of accounts in a stable random order are the holdout."""
    pc = cfg["treatment"]["pilot"]
    out = pd.Series("", index=f.index)
    for seg, idx in f[mask].groupby(f.loc[mask, "rule_segment"]).groups.items():
        idx = list(idx)
        order = np.argsort(_hash_rank(idx, pc["seed"]))
        k = int(round(pc["holdout_share"] * len(idx)))
        cells = np.array(["treatment"] * len(idx), dtype=object)
        cells[order[:k]] = "holdout"
        out[idx] = cells
    return out


def agreement(module_line_action: pd.Series, ml_action: pd.Series) -> pd.Series:
    cut = module_line_action.isin(["decrease", "closure"])
    ml = ml_action.fillna("NO_SCORE")
    no_view = ml.isin(ML_NO_VIEW + ["NO_SCORE"])
    ml_cut = ml.isin(ML_ADVERSE)
    agree = (cut & ml_cut) | (~cut & ml.isin(["MAINTAIN", "FREEZE_NO_INCREASE"]))
    return pd.Series(np.where(no_view, "ML has no view", np.where(agree, "agree", "disagree")), index=module_line_action.index)


def design(f: pd.DataFrame, cfg: dict, res: dict, ml: pd.DataFrame | None = None,
           worklists: dict | None = None) -> pd.DataFrame:
    """One row per account in scope with a recommendation (or 'none')."""
    tc = cfg["treatment"]
    sel, scope = res["selection"], res["scope"]
    lever_of_seg = f["rule_segment"].map(cfg["levers"]["system_mode"]["lever_by_segment"])
    rec_tr = cfg["levers"]["system_mode"]["transactor_rightsizing_in_recommendations"]
    dec = sel["decrease"] & ~((lever_of_seg == "transactor_rightsizing") & (not rec_tr))
    clo = sel["closure"]
    camp = sel["campaign"]
    sup = res["per_lever"]["suppress_automatic_increases"]["eligible"]
    nre = res["per_lever"]["non_reissue_expired_dormant"]["eligible"]

    t = pd.DataFrame(index=f.index[scope])
    s = lambda x: x.reindex(t.index).fillna(False).astype(bool)  # noqa: E731
    dec, clo, camp, sup, nre = s(dec), s(clo), s(camp), s(sup), s(nre)
    lev = lever_of_seg.reindex(t.index)
    t["customer"] = f.loc[t.index, "customer"]
    t["segment"] = f.loc[t.index, "rule_segment"]
    t["line_action"] = np.where(clo, "closure", np.where(dec, "decrease", "none"))
    t["line_lever"] = np.where(clo, "dormant_closure", np.where(dec, lev, ""))
    levers = []
    for i in t.index:
        r = []
        if clo[i]:
            r.append("dormant_closure")
        if dec[i]:
            r.append(lev[i])
        if camp[i]:
            r.append("engagement_campaign")
        if sup[i]:
            r.append("suppress_automatic_increases")
        if nre[i]:
            r.append("non_reissue_expired_dormant")
        levers.append(r)
    t["recommended_levers"] = ["; ".join(r) if r else "none" for r in levers]
    t["pending_approval"] = [any(L.pending(cfg, x) for x in r) for r in levers]
    rb = tc["reason_by_lever"]
    primary = [r[0] if r else "" for r in levers]
    t["reason_code"] = [rb.get(p, "") for p in primary]
    t["all_reason_codes"] = ["; ".join(dict.fromkeys(rb[x] for x in r)) for r in levers]
    t["notice"] = t["reason_code"].map(tc["notices"]).fillna("")
    t["adverse_action_notice"] = t["line_action"].ne("none") & t["reason_code"].isin(
        ["CREDIT_DETERIORATION", "IDLE_LINE_RIGHTSIZING"])
    t["fcra_score_disclosure_check"] = t["adverse_action_notice"] & t["reason_code"].eq("CREDIT_DETERIORATION")
    t["fee_restriction_45_days"] = t["line_action"].eq("decrease")
    t["ability_to_pay_check"] = False                       # no increases in this module
    t["new_line"] = np.where(dec, sel.loc[t.index, "new_line"], np.where(clo, 0.0, f.loc[t.index, "limit_current"]))
    t["cut"] = np.where(dec, sel.loc[t.index, "cut"], 0.0)
    if ml is not None and len(ml):
        m = ml.set_index("Masked Customer Number")
        for c in ["ml_action", "ml_primary_reason", "ml_recommended_limit"]:
            t[c] = t["customer"].map(m[c]) if c in m else np.nan
    else:
        t["ml_action"] = t["ml_primary_reason"] = t["ml_recommended_limit"] = np.nan
    t["ml_agreement"] = agreement(t["line_action"], t["ml_action"])
    rt = []
    members = {k: set(v["Masked Customer Number"]) for k, v in (worklists or {}).items()
               if k in tc["review_together_levers"] and len(v)}
    for c in t["customer"]:
        rt.append("; ".join(tc["review_together_levers"][k] for k in sorted(members) if c in members[k]))
    t["review_together"] = rt
    acted = pd.Series(f.index.isin(t.index[t["recommended_levers"] != "none"]), index=f.index)
    t["pilot_cell"] = pilot_cells(f, acted, cfg).reindex(t.index)
    t.loc[t["recommended_levers"] == "none", "pilot_cell"] = "no action"
    return t


def fairness(f: pd.DataFrame, treat: pd.DataFrame, cv: pd.DataFrame | None) -> dict:
    """Four-fifths by metro, three selections, with the existing test."""
    from engine.governance import fairness as FAIR
    out = {"proxy_method": "geography-only (Metro Name), as in the system's fairness module; not BISG"}
    pop = f[f["open_at_reporting_date"] & ~f["charged_off"]].rename(columns={"metro": "Metro Name"})
    sel = pop.index.isin(treat.index[treat["line_action"].isin(["decrease", "closure"])])
    out["module_decreases_and_closures"] = FAIR.four_fifths_test(pop, pd.Series(sel, index=pop.index))
    if cv is not None and "ml_action" in cv:
        out["ml_adverse_actions"] = FAIR.four_fifths_test(cv, cv["ml_action"].isin(ML_ADVERSE))
        out["ml_increases"] = FAIR.four_fifths_test(cv, cv["ml_action"].eq("INCREASE"))
    out["summary"] = {k: {"groups_tested": int(len(v)), "groups_failing": int((~v["passes"]).sum()) if len(v) else 0,
                          "failing_groups": v.loc[~v["passes"], "group"].tolist() if len(v) else []}
                      for k, v in out.items() if isinstance(v, pd.DataFrame)}
    return out


def timing_table(lever_table: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Year-1 and full annual value per lever (year-1 share from config)."""
    tm = cfg["timing"]
    inv = {v: k for k, v in L.LEVER_LABELS.items()}
    t = lever_table[["headline_value", "card_profit_change", "status", "group"]].copy()
    keys = [inv[i] for i in t.index]
    t["year1_share"] = [tm[k]["year1_share"] for k in keys]
    t["starts"] = [tm[k]["starts"] for k in keys]
    t["full_value_when"] = [tm[k]["full_value"] for k in keys]
    t["full_annual_value"] = t["headline_value"].astype(float)
    t["year1_value"] = t["full_annual_value"] * t["year1_share"]
    return t
