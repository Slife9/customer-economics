"""Treatment designer, compliance checks, fairness and timing (Stage 6).

Per account in scope, from the Base scenario's selection (levers.run):
    recommended lever(s), a mandatory reason code (one per lever, each with
    its notice rule and compliance flag in config treatment.reason_codes;
    OTHER only for an action no code covers), the notice it triggers,
    the 45-day fee / penalty-rate restriction after a decrease, "review
    together" flags for the system's L1 / L3 / L5 worklists, and a pilot cell
    (seeded, stratified holdout).
Compliance text is a summary for discussion; to be confirmed by compliance.
No lever ever proposes an inactivity fee.

The ML credit-limit model plays no part in this module (decision B8). The
worklists come from the existing engine (engine.run.build_pipeline), read
only. Fairness covers the module's own actions only: the existing
engine.governance.fairness.four_fifths_test on decreases and closures, and on
increases if the module ever produces any; a metro with fewer selected
accounts than `treatment.fairness.min_selected_per_group` is reported as
"insufficient sample" rather than pass or fail.
"""
from __future__ import annotations
import hashlib

import numpy as np
import pandas as pd

from . import levers as L

LINE_DECREASE_LEVERS = ["line_decrease", "risk_based_decrease", "dormant_rightsizing", "transactor_rightsizing"]

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


def design(f: pd.DataFrame, cfg: dict, res: dict, worklists: dict | None = None) -> pd.DataFrame:
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
    rule = lambda key: {k: v[key] for k, v in tc["reason_codes"].items()}  # noqa: E731
    t["notice"] = t["reason_code"].map(rule("notice")).fillna("")
    t["adverse_action_notice"] = t["line_action"].ne("none") & t["reason_code"].map(
        rule("adverse_action_notice")).fillna(False).astype(bool)
    t["fcra_score_disclosure_check"] = t["adverse_action_notice"] & t["reason_code"].map(
        rule("fcra_check")).fillna(False).astype(bool)
    flags = rule("compliance_flag")
    t["compliance_flags"] = ["; ".join(x for x in dict.fromkeys(flags.get(c, "") for c in codes.split("; ")) if x)
                             for codes in t["all_reason_codes"]]
    t["fee_restriction_45_days"] = t["line_action"].eq("decrease")
    t["ability_to_pay_check"] = False                       # no increases in this module
    t["new_line"] = np.where(dec, sel.loc[t.index, "new_line"], np.where(clo, 0.0, f.loc[t.index, "limit_current"]))
    t["cut"] = np.where(dec, sel.loc[t.index, "cut"], 0.0)
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


FAIRNESS_TESTS = {"module_decreases_and_closures": "Decreases and closures", "module_increases": "Increases"}


def _four_fifths(pop: pd.DataFrame, selected: pd.Series, min_selected: int) -> pd.DataFrame:
    """The existing test, plus every metro it leaves out, with a status:
    pass / fail, or insufficient sample (fewer than `min_selected` selected
    accounts, or under the test's own minimum group size)."""
    from engine.governance import fairness as FAIR
    res = FAIR.four_fifths_test(pop, selected).set_index("group")
    g = pd.DataFrame({"n": pop.groupby("Metro Name").size(),
                      "selected": selected.groupby(pop["Metro Name"]).sum().astype(int)})
    g["selection_rate"] = g["selected"] / g["n"]
    g["ratio_to_population"] = res["ratio_to_population"].reindex(g.index)
    ok = g.index.isin(res.index) & (g["selected"] >= min_selected)
    g["status"] = np.where(~ok, "insufficient sample",
                           np.where(res["passes"].reindex(g.index).fillna(False).astype(bool), "pass", "fail"))
    return g.rename_axis("group").reset_index().sort_values(["status", "ratio_to_population"])


def fairness(f: pd.DataFrame, treat: pd.DataFrame, cfg: dict) -> dict:
    """Four-fifths by metro on the module's own actions only: decreases and
    closures, and increases if the module ever produces any."""
    k = cfg["treatment"]["fairness"]["min_selected_per_group"]
    out = {"proxy_method": "geography-only (Metro Name), as in the system's fairness module; not BISG",
           "min_selected_per_group": k}
    pop = f[f["open_at_reporting_date"] & ~f["charged_off"]].rename(columns={"metro": "Metro Name"})
    cut = pd.Series(pop.index.isin(treat.index[treat["line_action"].isin(["decrease", "closure"])]), index=pop.index)
    out["module_decreases_and_closures"] = _four_fifths(pop, cut, k)
    up = pd.Series(pop.index.isin(treat.index[treat["line_action"].eq("increase")]), index=pop.index)
    if up.any():
        out["module_increases"] = _four_fifths(pop, up, k)
    out["summary"] = {key: {"groups": int(len(v)), "groups_tested": int((v["status"] != "insufficient sample").sum()),
                            "groups_failing": int((v["status"] == "fail").sum()),
                            "groups_insufficient": int((v["status"] == "insufficient sample").sum()),
                            "failing_groups": v.loc[v["status"] == "fail", "group"].tolist(),
                            "selected": int(v["selected"].sum())}
                      for key, v in out.items() if isinstance(v, pd.DataFrame)}
    out["increases_note"] = ("The module produces no line increases, so there is no increase test."
                             if not up.any() else "")
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
