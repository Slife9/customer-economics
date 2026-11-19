"""Acceptance audit for the Unused Credit Line Management module
(specs/unused_line_management, brief section 7). Run as a script, like every
other file in this directory. Later stages add their checks here.

    python audit/audit_unused_line_module.py
    python audit/audit_unused_line_module.py --bundle-100k <v2 bundle zip> \
        --frame-100k <per-account parquet built from the 100k portfolio> \
        [--frame-100k-json <timing JSON from building it>]

Stage 3 (regulatory settings and the account exposure and cost layer):
1. Worked examples (brief s.7.1), to the cent.
2. Workbook reproduction: at its original 85% / 55% weights the module's
   workbook mode reproduces the Dashboard baseline within +/-1%; the corrected
   figures under s.2 are reported (about $117.9M RWA, $1.49M capital cost,
   $0.49M liquidity).
3. Invariants on generated portfolios (demo 5k and the unused_line_stress
   book, generated in a temp directory): no 0% CCF, the transactor test,
   plan / promotional balances at 75%, the three cost columns kept apart,
   annual PD only, the old capital charge replaced and never added.
4. Toggles change only what they should.
5. Portfolio cross-check (s.2.7) on the 100k bundle and the module's own
   per-account file of the same portfolio, +/-5%, differences explained.
6. Performance: the per-account file on 100k, and loading it with the cost
   layer in a fresh process (what the app does), with peak memory.

Stage 4 (screen and segments), on the same portfolios:
7. Rules agree with the calibration report's independent reading; first
   match wins; screened exactly when every criterion is met; the system screen
   does not deduct drawdown loss and its sensitivity toggle only adds accounts;
   summaries add up with carrying cost and drawdown loss apart; thresholds
   from config; segmentation and regulatory transactor rules apart.

Stage 5 (levers, response, scenarios, stress):
8. Workbook-reproduction scenarios within +/-1% of the Dashboard; corrected
   weights reported (Relationship at 45% and at 75%).
9. System mode on each portfolio: low <= base <= high; capital released never
   in an annual value; value types reconcile; cut rules; closures and B6;
   the 45% -> 75% flip; fixed cost stays; extra levers apart; scope mode;
   stress test and the go/no-go rule.

Stage 6 (treatment designer, compliance, fairness, timing):
10. Reason codes on every action; notices by reason (inactivity: none;
    credit: adverse action + FCRA check); the 45-day fee restriction; no
    inactivity fee; transactor right-sizing never recommended; the ML model
    not used anywhere in the module (B8); seeded stratified pilot; review-
    together flags; the four-fifths test on the module's own actions with
    "insufficient sample" below the configured count; year-1 timing.

Revision B (calculation corrections), on the same portfolios:
13. B1 missing PD -> segment average PD (never zero), flagged; B2 LEQ source
    switch (account Behavioral CCF / workbook segment) changes drawdown loss
    only; B3 a specific reason code and notice rule per lever, OTHER below 1%
    of actions; B4 reconciliation from the main engine's card profit, to the
    cent; B5 fixed-cost basis switch changes fixed cost and card profit only,
    variable contribution unchanged; B6 the robustness statement states its
    basis.

Stage 8 runs everything above as one suite, plus:
12. Guardrails: no change since main to the code the module must not touch;
    generator/run.py additions only; with --regression, the byte-identity
    and engine-regression audit (audit_unused_line_data_additions.py).

    python audit/audit_unused_line_module.py --regression         --bundle-100k <rebuilt 100k v2 bundle> --frame-100k <its per-account parquet>         --frame-100k-json <build timing>

Revision E (alignment with the project report and slides):
14. Balance basis: the midpoint balance, the statement-date 30% test (only
    removes cards that use 30%+ at statement date), lever values on today's
    unused line; pay-in-full right-sizing out of the approved value and the
    recommendations, by policy.
15. On the committed samples: with every revision-E setting at its old value
    the Stage 0 figures reproduce exactly.
16. The four strategies: values add up to their components, capital freed
    never in an annual value, the campaign split exactly between Strategy 2
    and the Invite, the 90-day warning (no responses = the planned action; the
    letter cost; a fee refused), every action in a strategy.
Worked examples include the report's ACC-EXAMPLE ($186.48).

Stage 7 (app; revision C, rebuilt in revision E):
11. The committed samples, every page in both views (executive, analyst) on
    both datasets (AppTest), no value-type badge, technical label or
    analyst-only page in the executive view, and the app's peak memory in
    one process.

Prints a PASS/FAIL table; exits 1 if any check FAILs.
"""
from __future__ import annotations
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.unused_lines import assumptions as A, data as D, exposure as X, segments as SG  # noqa: E402
from engine.unused_lines import levers as L, workbook as W, treatment as T, strategies as ST  # noqa: E402

PROFILES = ["demo", "unused_line_stress"]
BRIEF_27 = {"ucl": 2.69e9, "rwa_unused": 165.8e6, "capital_cost_unused": 2.09e6, "hqla": 134.5e6,
            "liquidity_cost": 1.01e6, "carrying_cost": 3.10e6}
BRIEF_27_GROUPS = {"Dormant": (1.16e6, -0.81e6), "Idle": (0.47e6, -4.03e6),
                   "Healthy": (0.90e6, 9.52e6), "Stretched": (0.10e6, 8.39e6)}
L2_GROUP = {"DEEPEN_RELATIONSHIP_NO_LIMIT_CHANGE": "Healthy", "REACTIVATION_CAMPAIGN": "Dormant",
            "DECREASE_LIMIT": "Idle", "INCREASE_LIMIT": "Stretched"}
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)
    return ok


def near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(abs(b), 1e-9)


# ------------------------------------------------------------- 1, 2
def worked_examples(cfg: dict) -> None:
    print("\n1. Worked examples (brief s.7.1)", flush=True)
    cases = [
        ("dormant $10,000 card", 10000, 0, cfg["capital"]["risk_weight_dormant_zero_balance"],
         {"exposure_unused": 1000, "rwa_unused": 750, "capital_required_unused": 78.75,
          "capital_cost_unused": 9.45, "hqla": 500, "liquidity_cost": 3.75, "carrying_cost": 13.20}),
        ("$10,000 line, $2,000 balance (non-transactor)", 10000, 2000,
         cfg["capital"]["risk_weight_non_transactor"],
         {"rwa_unused": 600, "capital_cost_unused": 7.56, "liquidity_cost": 3.00, "carrying_cost": 10.56}),
        ("$10,000 line, $2,000 balance (transactor)", 10000, 2000, cfg["capital"]["risk_weight_transactor"],
         {"rwa_unused": 360, "capital_cost_unused": 4.54, "liquidity_cost": 3.00, "carrying_cost": 7.54}),
    ]
    for name, limit, bal, rw, want in cases:
        got = X.worked_example(limit, bal, rw, cfg)
        bad = {k: (round(got[k], 2), v) for k, v in want.items() if abs(round(got[k], 2) - v) > 0.005}
        record(f"worked example: {name}", not bad,
               ", ".join(f"{k} {round(got[k], 2):,}" for k in want) if not bad else f"mismatch {bad}")
    # Revision E: the project report's ACC-EXAMPLE (config presentation.worked_example)
    ex = cfg["presentation"]["worked_example"]
    rw = cfg["capital"][f"risk_weight_{ex['risk_weight_basis']}"]
    leq = cfg["drawdown_risk"]["leq_by_segment"][ex["segment"]]
    got = X.worked_example(ex["limit_usd"], ex["average_balance_usd"], rw, cfg, ex["chance_of_default"],
                           ex["loss_if_default"], leq)
    got45 = X.worked_example(ex["limit_usd"], ex["average_balance_usd"], cfg["capital"]["risk_weight_transactor"], cfg)
    want = {"capital_cost_unused": 13.23, "liquidity_cost": 5.25, "carrying_cost": 18.48, "drawdown_el": 168.00,
            "total_unused_line_cost": 186.48}
    bad = {k: (round(got[k], 2), v) for k, v in want.items() if abs(round(got[k], 2) - v) > 0.005}
    record(f"worked example: {ex['account_id']} (project report; $186.48 a year, $7.94 capital at 45%)",
           not bad and abs(round(got45["capital_cost_unused"], 2) - 7.94) < 0.005,
           ", ".join(f"{k} {round(got[k], 2):,}" for k in want) + f"; capital at 45% {round(got45['capital_cost_unused'], 2)}"
           if not bad else f"mismatch {bad}")


def workbook(cfg: dict) -> None:
    print("\n2. Workbook reproduction", flush=True)
    ref = cfg["workbook"]["dashboard_reference"]["baseline"]
    wb = X.workbook_baseline(cfg).loc["total"]
    items = ["accounts", "credit_line", "undrawn", "rwa", "capital_charge", "liquidity_cost",
             "expected_credit_loss", "revenue", "contribution", "fully_loaded_profit",
             "relationship_adjusted_profit"]
    worst = max(abs(wb[k] - ref[k]) / max(abs(ref[k]), 1e-9) for k in items)
    record("baseline at the workbook's 85% / 55% weights within +/-1% of its Dashboard",
           worst <= 0.01, f"{len(items)} items; largest difference {worst:.4%}; "
           f"RWA ${wb['rwa']:,.0f}, fully loaded ${wb['fully_loaded_profit']:,.0f}")
    by_seg = cfg["workbook"]["dashboard_reference"]["base_by_segment"]
    seg_worst = max(abs(X.workbook_baseline(cfg).loc[s, "fully_loaded_profit"] - v["baseline_profit"])
                    / abs(v["baseline_profit"]) for s, v in by_seg.items())
    record("baseline fully loaded profit by segment within +/-1%", seg_worst <= 0.01,
           f"largest difference {seg_worst:.4%}")
    rt = cfg["workbook"]["dashboard_reference"]["regime_table"]["basel_endgame_2023"]
    wbt = X.workbook_baseline(cfg).loc["total"]
    record("RWA from undrawn lines (Dashboard regime table) within +/-1%",
           near(wbt["rwa_undrawn"], rt["undrawn_rwa"], 0.01), f"${wbt['rwa_undrawn']:,.0f} vs ${rt['undrawn_rwa']:,.0f}")
    cor = X.workbook_baseline(cfg, cfg["workbook_reproduction"]["corrected_risk_weights"],
                              {s: cfg["capital"]["ccf_unused_card_lines"] for s in A.WORKBOOK_SEGMENTS}).loc["total"]
    ok = near(cor["rwa"], 117.9e6, 0.01) and near(cor["capital_charge"], 1.49e6, 0.01) \
        and near(cor["liquidity_cost"], 0.49e6, 0.01)
    record("corrected baseline (75% / 45%, segment-level) matches the brief's expectation",
           ok, f"RWA ${cor['rwa']:,.0f}, capital cost ${cor['capital_charge']:,.0f}, "
               f"liquidity ${cor['liquidity_cost']:,.0f}, fully loaded ${cor['fully_loaded_profit']:,.0f}")


# ------------------------------------------------------------- 3, 4
def invariants(costs: pd.DataFrame, cfg: dict, label: str) -> None:
    print(f"\n3. Invariants - {label}", flush=True)
    c = costs
    record(f"{label}: no card at a 0% CCF", bool((c["ccf"] > 0).all()), f"CCF {c['ccf'].unique().tolist()}")
    try:
        A.with_overrides(cfg, {"capital": {"ccf_unused_card_lines": 0.0}})
        rejected = False
    except A.AssumptionsError:
        rejected = True
    record(f"{label}: a 0% CCF configuration is refused", rejected)

    tr = c["rw_basis"] == "transactor"
    tr_ok = bool((c.loc[tr, "cycles_not_paid_12m"] == 0).all()
                 and (c.loc[tr, "cycles_observed_12m"] >= 12).all()
                 and (c.loc[tr, "account_age_months"] >= 12).all()
                 and ~(c.loc[tr, "installment_plan_12m"] | c.loc[tr, "promotional_balance_12m"]).any()
                 and (c.loc[tr, "cycles_zero_statement_12m"] < c.loc[tr, "cycles_observed_12m"]).all()
                 and (c.loc[tr, "rw"] == cfg["capital"]["risk_weight_transactor"]).all())
    record(f"{label}: every 45% account passes the transactor test (12 cycles, all paid or $0, not all $0, "
           f"no plan / promo)", tr_ok, c["rw_basis"].value_counts().to_dict().__repr__())
    plan = c["installment_plan_12m"] | c["promotional_balance_12m"]
    record(f"{label}: installment, promotional or BT balance -> 75% (or 100% above the retail limit)",
           bool((c.loc[plan, "rw"] >= cfg["capital"]["risk_weight_non_transactor"]).all()),
           f"{int(plan.sum()):,} accounts with a plan or promotional balance")
    flip = c[tr].head(50).copy()
    flip["installment_plan_12m"] = True
    rw2, _ = X.risk_weights(flip, cfg)
    record(f"{label}: adding a plan balance flips a transactor from 45% to 75%",
           bool(len(flip) and (rw2 == cfg["capital"]["risk_weight_non_transactor"]).all()), f"{len(flip)} accounts flipped")

    sep = (np.allclose(c["carrying_cost"], c["capital_cost_unused"] + c["liquidity_cost"])
           and np.allclose(c["total_unused_line_cost"], c["carrying_cost"] + c["drawdown_el"]))
    record(f"{label}: carrying cost = capital (unused part) + liquidity; drawdown loss separate; total = both",
           bool(sep))
    el = c["pd_used"] * c["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"]) * c["leq"] * c["ucl"]
    measured = c["pd_12m"].notna()
    record(f"{label}: drawdown loss = annual PD (Table8 PD 12 Month; imputed where missing) x LGD x LEQ x unused line",
           bool(np.allclose(c["drawdown_el"], el) and np.allclose(c.loc[measured, "pd_used"], c.loc[measured, "pd_12m"])),
           f"{int(c['pd_imputed'].sum())} accounts without a PD (imputed)")
    swap = np.allclose(c["card_profit"] - c["card_net"], c["old_capital_cost"] - c["capital_cost"] - c["liquidity_cost"])
    record(f"{label}: card profit = card_net with the old capital charge replaced and liquidity subtracted",
           bool(swap), f"old capital ${c['old_capital_cost'].sum():,.0f} replaced by ${c['capital_cost'].sum():,.0f}")


def toggles(acc: pd.DataFrame, cfg: dict, leq: float, label: str) -> None:
    print(f"\n4. Toggles - {label}", flush=True)
    base = X.account_costs(acc, cfg, leq_unassigned=leq)
    out_of_scope = A.with_overrides(cfg, {"bank_profile": {"bank_category": "category_IV_or_other"}})
    o = X.account_costs(acc, out_of_scope, leq_unassigned=leq)
    record(f"{label}: bank outside Categories I-III -> no liquidity cost, capital unchanged",
           bool((o["liquidity_cost"] == 0).all() and np.allclose(o["capital_cost"], base["capital_cost"])),
           f"liquidity ${base['liquidity_cost'].sum():,.0f} -> ${o['liquidity_cost'].sum():,.0f}")
    allb = A.with_overrides(out_of_scope, {"bank_profile": {"apply_to": "all_banks"}})
    a = X.account_costs(acc, allb, leq_unassigned=leq)
    record(f"{label}: apply_to = all_banks restores liquidity for that bank; capital unchanged",
           bool(np.allclose(a["liquidity_cost"], base["liquidity_cost"]) and np.allclose(a["capital_cost"], base["capital_cost"])))
    d45 = A.with_overrides(cfg, {"capital": {"risk_weight_dormant_zero_balance": 0.45}})
    d = X.account_costs(acc, d45, leq_unassigned=leq)
    dorm = base["rw_basis"] == "dormant_zero_balance"
    changed = ~np.isclose(d["rwa"], base["rwa"])
    record(f"{label}: dormant risk weight (B5) changes only dormant zero-balance accounts",
           bool(changed[~dorm].sum() == 0 and changed[dorm].sum() == (base.loc[dorm, "rwa"] > 0).sum()),
           f"{int(dorm.sum()):,} dormant accounts; RWA ${base.loc[dorm, 'rwa'].sum():,.0f} -> ${d.loc[dorm, 'rwa'].sum():,.0f}")
    cur = X.current_rules(base, cfg)
    record(f"{label}: current-rules view: 0% CCF, 100% on drawn balances, no liquidity; main view untouched",
           bool(np.allclose(cur["rwa_current_rules"], base["balance"]) and (cur["liquidity_cost_current_rules"] == 0).all()
                and np.allclose(X.account_costs(acc, cfg, leq_unassigned=leq)["rwa"], base["rwa"])),
           f"RWA ${base['rwa'].sum():,.0f} (s.2) vs ${cur['rwa_current_rules'].sum():,.0f} (current); "
           f"SLR capital ${cur['slr_capital_required'].sum():,.0f} vs risk-based ${base['capital_required'].sum():,.0f}")
    now = X.account_costs(acc, cfg, basis="current", leq_unassigned=leq)
    cur_col = X.BALANCE_COLUMNS[(cfg["balance_basis"]["cost"], "current")][1]
    avg_col = X.BALANCE_COLUMNS[(cfg["balance_basis"]["cost"], "average")][1]
    record(f"{label}: 'current' basis uses the reporting-date line and balance (cost basis "
           f"{cfg['balance_basis']['cost']})",
           bool(np.allclose(now["ucl"], acc[cur_col].fillna(0)) and np.allclose(base["ucl"], acc[avg_col].fillna(0))))


# ------------------------------------------------------------- Stage 4
def segment_checks(acc: pd.DataFrame, meta: dict, cfg: dict, label: str) -> pd.DataFrame:
    print(f"\n7. Screen and segments - {label}", flush=True)
    sys.path.insert(0, str(ROOT / "audit"))
    import unused_line_calibration_report as CAL  # the independent reading of the rules
    f = SG.build(acc, meta, cfg)
    indep = pd.Series(CAL.rule_segment(f, cfg), index=f.index)
    record(f"{label}: module segment rules agree with the calibration report's independent reading",
           bool((indep == f["rule_segment"]).all()), f"{(indep == f['rule_segment']).mean():.2%} of {len(f):,} accounts")
    order = cfg["segments"]["order"]
    first = pd.Series("unassigned", index=f.index)
    groups = {"deteriorating": ["deteriorating.pd", "deteriorating.score_drop"],
              "relationship": ["relationship.noncard_profit", "relationship.deposits", "relationship.premium"]}
    hit = {"deteriorating": f["met:deteriorating.pd"] | f["met:deteriorating.score_drop"],
           "relationship": f[[f"met:{k}" for k in groups["relationship"]]].any(axis=1),
           "dormant": f["met:dormant.inactive"] & f["met:dormant.zero_balance"],
           "sock_drawer": f["met:sock_drawer.active"] & f["met:sock_drawer.spend"],
           "transactors": f["met:transactors.paid"] & f["met:transactors.peak"] & f["met:transactors.spend"]}
    for seg in reversed(order[:5]):
        first = first.where(~hit[seg], seg)
    record(f"{label}: first match wins, in the workbook's priority order", bool((first == f["rule_segment"]).all()))
    crit = [c for c in f.columns if c.startswith("met:screen.")]
    allmet = f[crit].all(axis=1)
    record(f"{label}: screened exactly when every screen criterion is met; segment only when screened",
           bool((allmet == f["screened"]).all() and (f.loc[~f["screened"], "segment"] == "").all()
                and (f.loc[f["screened"], "segment"] == f.loc[f["screened"], "rule_segment"]).all()),
           f"{int(f['screened'].sum()):,} screened; failing: " + ", ".join(
               f"{c[10:]} {int((~f[c]).sum()):,}" for c in crit))
    ok_default = bool((f.loc[f["screened"], "card_profit"] < 0).all())
    sens = SG.drawdown_sensitivity(f)
    extra = f["screened_drawdown_sensitivity"] & ~f["screened"]
    ok_toggle = bool((f.loc[extra, "card_profit"] >= 0).all()
                     and (f.loc[extra, "card_profit"] - f.loc[extra, "drawdown_el"] < 0).all()
                     and not (f["screened"] & ~f["screened_drawdown_sensitivity"]).any())
    record(f"{label}: system screen does not deduct drawdown loss; the sensitivity toggle only adds accounts "
           f"made unprofitable by it", ok_default and ok_toggle,
           f"toggle on: +{sens['extra_accounts']:,} accounts, extra loss after drawdown "
           f"${-sens['extra_loss_after_drawdown']:,.0f}")
    s = SG.summary(f, cfg)
    body = s.drop(index="Total")
    record(f"{label}: segment summary adds up; carrying cost and drawdown loss in separate columns",
           bool(np.allclose(body[SG.SUMMARY_COLS].sum(), s.loc["Total", SG.SUMMARY_COLS])
                and np.isclose(s.loc["Total", "carrying_cost"],
                               f.loc[f["screened"], ["capital_cost_unused", "liquidity_cost"]].sum().sum())
                and np.isclose(s.loc["Total", "total_unused_line_cost"],
                               s.loc["Total", "carrying_cost"] + s.loc["Total", "drawdown_el"])),
           "; ".join(f"{i} {int(r.accounts):,}" for i, r in body.iterrows()))
    raised = A.with_overrides(cfg, {"segments": {"rules": {"deteriorating": {"pd_annual_min": 0.02}}}})
    f2 = SG.build(acc, meta, raised)
    record(f"{label}: thresholds come from config (PD threshold 4% -> 2% moves accounts into Credit-Deteriorating)",
           bool((f2["rule_segment"] == "deteriorating").sum() > (f["rule_segment"] == "deteriorating").sum()),
           f"{int((f['rule_segment'] == 'deteriorating').sum()):,} -> {int((f2['rule_segment'] == 'deteriorating').sum()):,}")
    tr = f[f["segment"] == "transactors"]
    record(f"{label}: segmentation transactor rule (>= 10/12) kept apart from the regulatory test (12/12)",
           bool(tr["met:transactors.paid"].all() and "rw_basis" in f),
           f"{len(tr):,} in the Transactors segment, {(tr['rw_basis'] == 'transactor').mean():.0%} of them at 45%")
    un = s.loc[cfg["segments"]["labels"]["unassigned"]]
    record(f"{label}: Unassigned shows its economics", bool(un["accounts"] == 0 or un["card_profit"] != 0),
           f"{int(un['accounts']):,} accounts, card profit ${un['card_profit']:,.0f}")
    return f


# ------------------------------------------------------------- Revision B
def correction_checks(acc: pd.DataFrame, meta: dict, f: pd.DataFrame, cfg: dict, label: str) -> None:
    print(f"\n13. Calculation corrections (revision B) - {label}", flush=True)
    miss = f["pd_12m"].isna()
    seg_avg = f.loc[~miss].groupby("rule_segment")["pd_12m"].mean()
    want = f.loc[miss, "rule_segment"].map(seg_avg).fillna(f["pd_12m"].mean())
    record(f"{label}: B1 a missing PD takes its segment's average PD (accounts with a PD), never zero; flagged",
           bool(np.allclose(f.loc[miss, "pd_used"], want) and (f.loc[miss, "pd_used"] > 0).all()
                and (f["pd_imputed"] == miss).all() and np.allclose(f.loc[~miss, "pd_used"], f.loc[~miss, "pd_12m"])),
           f"{int(miss.sum()):,} imputed ({int((miss & f['screened']).sum()):,} screened); "
           f"{f.loc[miss].assign(o=f['open_at_reporting_date'] & ~f['charged_off'])['o'].sum():,} of them open")
    fa = SG.build(acc, meta, A.with_overrides(cfg, {"drawdown_risk": {"leq_source": "measured_account"}}))
    fw = SG.build(acc, meta, A.with_overrides(cfg, {"drawdown_risk": {"leq_source": "workbook_segment"}}))
    has = f["behavioural_ccf"].notna()
    seg_leq = f["rule_segment"].map(cfg["drawdown_risk"]["leq_by_segment"]).fillna(meta["leq_unassigned_measured"])
    default = fw if cfg["drawdown_risk"]["leq_source"] == "workbook_segment" else fa
    ok = (np.allclose(fa.loc[has, "leq"], fa.loc[has, "behavioural_ccf"]) and np.allclose(fa.loc[~has, "leq"], seg_leq[~has])
          and np.allclose(fw["leq"], seg_leq) and (fw["screened"] == fa["screened"]).all()
          and np.allclose(fw["card_profit"], fa["card_profit"]) and np.allclose(fw["carrying_cost"], fa["carrying_cost"])
          and np.allclose(f["drawdown_el"], default["drawdown_el"]))
    sc = f["screened"]
    record(f"{label}: B2 LEQ switch: workbook segment LEQ, or the account's Behavioral CCF (workbook LEQ when "
           f"missing); it changes drawdown loss only (default: {cfg['drawdown_risk']['leq_source']})", bool(ok),
           f"screened drawdown loss ${fw.loc[sc, 'drawdown_el'].sum():,.0f} (workbook segment) vs "
           f"${fa.loc[sc, 'drawdown_el'].sum():,.0f} (account); {int((~has).sum()):,} accounts on the fallback")
    rec = X.reconciliation(f, sc)
    record(f"{label}: B4 main engine card profit + old capital - new capital - liquidity = module card profit, to the cent",
           abs(float(rec["usd"].iloc[-1])) < 0.005,
           f"card_net ${rec['usd'].iloc[0]:,.0f} -> module ${rec['usd'].iloc[-2]:,.0f} on {int(sc.sum()):,} screened accounts")
    wfc = A.with_overrides(cfg, {"costs": {"fixed_cost_basis": "workbook_segment"}})
    ff = SG.build(acc, meta, wfc)
    var_same = np.allclose(ff["card_profit"] + ff["fixed_cost"], f["card_profit"] + f["fixed_cost"])
    wb_fc = {k: v["fixed_cost"] for k, v in cfg["workbook"]["segments"].items()}
    seg_ok = all(np.allclose(ff.loc[ff["rule_segment"] == k, "fixed_cost"], v) for k, v in wb_fc.items())
    rec2 = X.reconciliation(ff, ff["screened"])
    record(f"{label}: B5 fixed-cost basis switch changes fixed cost and card profit only (variable contribution "
           "unchanged); reconciles", bool(var_same and seg_ok and np.allclose(ff["drawdown_el"], f["drawdown_el"])
                                         and abs(float(rec2["usd"].iloc[-1])) < 0.005),
           f"engine fixed cost ${f.loc[sc, 'fixed_cost'].mean():,.2f} per screened account; workbook basis screens "
           f"{int(ff['screened'].sum()):,} accounts (default {int(sc.sum()):,})")


# ------------------------------------------------------------- Revision E
OLD_SETTINGS = {"balance_basis": {"screen": "after_payment", "cost": "after_payment", "lever_values": "average_12m"},
                "levers": {"system_mode": {"transactor_rightsizing_in_approved_value": True}},
                "warning": {"enabled": False}}


def balance_basis_checks(acc: pd.DataFrame, meta: dict, f: pd.DataFrame, cfg: dict, label: str) -> None:
    print(f"\n14. Balance basis and pay-in-full policy (revision E, Stage 1) - {label}", flush=True)
    mid_ok = np.allclose(acc["balance_midpoint_avg_12m"],
                         (acc["statement_balance_avg_12m"] + acc["balance_avg_12m"]) / 2, equal_nan=True)
    stmt_ok = bool((acc["statement_balance_avg_12m"] >= acc["balance_avg_12m"] - 1e-6).all())
    record(f"{label}: 1b the midpoint balance is (statement + after-payment) / 2 in every cycle; statement >= after "
           "payment", bool(mid_ok and stmt_ok),
           f"12-month average balance: after payment ${acc['balance_avg_12m'].mean():,.0f}, midpoint "
           f"${acc['balance_midpoint_avg_12m'].mean():,.0f}, statement ${acc['statement_balance_avg_12m'].mean():,.0f}")
    after = A.with_overrides(cfg, {"balance_basis": {"screen": "after_payment"}})
    fa = SG.build(acc, meta, after)
    left = fa["screened"] & ~f["screened"]
    joined = f["screened"] & ~fa["screened"]
    record(f"{label}: 1b the statement-date screen only removes cards that use 30%+ of the limit at statement date",
           bool(not joined.any() and (acc.loc[left, "statement_utilisation_avg_12m"]
                                      >= cfg["screen"]["max_utilisation"]).all()),
           f"{int(left.sum()):,} cards leave the selection ({int(fa['screened'].sum()):,} -> {int(f['screened'].sum()):,})")
    fw = L.forward_frame(f, cfg)
    col = X.BALANCE_COLUMNS[(cfg["balance_basis"]["cost"], "current")][1]
    record(f"{label}: 1b lever values use today's unused line; past profit keeps the 12-month average",
           bool(np.allclose(fw["ucl"], acc[col].reindex(f.index).fillna(0))
                and np.allclose(f["ucl"], acc[X.BALANCE_COLUMNS[(cfg['balance_basis']['cost'], 'average')][1]]
                                .reindex(f.index).fillna(0))),
           f"selected cards: today ${fw.loc[f['screened'], 'ucl'].sum() / 1e6:,.1f}M vs 12-month "
           f"${f.loc[f['screened'], 'ucl'].sum() / 1e6:,.1f}M unused")
    res = L.run(f, cfg, "base")
    lt = L.lever_table(res, cfg, f)
    tr_lab = L.LEVER_LABELS["transactor_rightsizing"]
    sel, g = res["selection"], res["frame"]
    s3 = sel["decrease"] & (f["rule_segment"] == "transactors")
    keep = sel["decrease"] & ~f["rule_segment"].isin(["transactors", "dormant"])
    without = L.value(g, cfg, sel.assign(decrease=keep, closure=False), res["params"], {"decrease": True, "campaign": True})
    t = T.design(f, cfg, res)
    record(f"{label}: 1c pay-in-full right-sizing is valued for analysts but outside the approved value and the "
           "recommendations, by policy", bool(lt.loc[tr_lab, "status"] == "excluded by policy"
                                               and np.allclose(without["headline_value"], res["combined"]["headline_value"])
                                               and not t["recommended_levers"].str.contains("transactor_rightsizing").any()
                                               and "loses money" not in tr_lab),
           f"stand-alone value {float(lt.loc[tr_lab, 'headline_value']):+,.0f} (Base); {int(s3.sum()):,} cards it would "
           f"cut; approved value {res['combined'][res['scope']]['headline_value'].sum():+,.0f} without them")


def strategy_checks(f: pd.DataFrame, cfg: dict, label: str) -> None:
    print(f"\n16. Four strategies and the 90-day warning (revision E, Stage 2) - {label}", flush=True)
    res = L.run(f, cfg, "base")
    sr = ST.run(res, cfg)
    s = ST.summary(sr, cfg)
    tb = s["table"]
    adds = all(np.isclose(v["headline_value"], sum(v["components"].values())) for v in s["strategies"].values())
    ident = all(np.allclose(v["effect"]["headline_value"], v["effect"]["card_profit_change"] - v["effect"]["drawdown_change"])
                for v in sr["steps"].values())
    record(f"{label}: each strategy's value is the sum of its components; every value = change in card profit + "
           "reduction in drawdown loss", bool(adds and ident),
           "; ".join(f"{v['number']}: {v['headline_value']:+,.0f}" for v in s["strategies"].values()))
    record(f"{label}: capital freed is one-time, never inside an annual value; total potential = approved + "
           "proposed + awaiting decision", bool(
               "capital_released" not in ST.ANNUAL and np.isclose(
                   s["total_potential"], s["approved_combined"]["headline_value"] + s["proposed"] + s["awaiting_decision"])),
           f"approved {s['approved_combined']['headline_value']:+,.0f} + proposed {s['proposed']:+,.0f} + awaiting "
           f"{s['awaiting_decision']:+,.0f} = {s['total_potential']:+,.0f}; capital freed "
           f"${s['approved_combined']['capital_released']:,.0f} (one-time)")
    lv = res["combined"][res["scope"]]["headline_value"].sum()
    camp = res["per_lever"]["engagement_campaign"][res["scope"]]["headline_value"].sum()
    split = tb.loc[tb["step"].isin(["campaign", "invite"]), "headline_value"].sum()
    record(f"{label}: 2a the campaign splits exactly into Strategy 2 and Strategy 3's Invite; the combined approved "
           "value equals the levers' combined headline", bool(np.isclose(split, camp)
                                                              and np.isclose(s["approved_combined"]["headline_value"], lv)),
           f"campaign {camp:+,.0f} = Strategy 2 {tb.loc[tb['step'] == 'campaign', 'headline_value'].sum():+,.0f} + Invite "
           f"{tb.loc[tb['step'] == 'invite', 'headline_value'].sum():+,.0f}")
    zero = A.with_overrides(cfg, {"warning": {"response_shares": {"resume_use": 0, "accept_lower_limit": 0,
                                                                  "close_voluntarily": 0}, "letter_cost_usd": 0}})
    sz = ST.run(res, zero)
    g, P, sel = res["frame"], res["params"], res["selection"]
    reach = 1 - P["response"].where(sel["campaign"] & (g["rule_segment"] == "dormant"), 0.0)
    same = all(np.allclose(sz["steps"][("use_it_or_lose_it", k)]["effect"]["headline_value"],
                           res["per_lever"][lv_]["headline_value"].where(sz["steps"][("use_it_or_lose_it", k)]["targeted"], 0)
                           * reach)
               for k, lv_ in [("rightsize", "dormant_rightsizing"), ("close", "dormant_closure"),
                              ("non_reissue", "non_reissue_expired_dormant")])
    letters = tb["letters"].sum()
    no_cost = ST.summary(ST.run(res, A.with_overrides(cfg, {"warning": {"letter_cost_usd": 0}})), cfg)
    cost_ok = np.isclose(no_cost["awaiting_decision"] - s["awaiting_decision"], letters * cfg["warning"]["letter_cost_usd"])
    try:
        A.validate({**cfg, "warning": {**cfg["warning"], "inactivity_fee_usd": 5}})
        fee_refused = False
    except A.AssumptionsError:
        fee_refused = True
    record(f"{label}: 2b the warning: with no responses it equals the planned action for every card not won back by "
           "the Invite; each letter costs its configured amount; a fee in the warning settings is refused",
           bool(same and cost_ok and fee_refused),
           f"{letters:,.0f} letters; shares {cfg['warning']['response_shares']}; Strategy 3 actions "
           f"{s['awaiting_decision']:+,.0f} with the warning")
    t = T.design(f, cfg, res)
    acted = t[t["recommended_levers"] != "none"]
    s3 = acted["recommended_levers"].str.contains("|".join(T.WARNING_LEVERS))
    record(f"{label}: every recommended action belongs to a strategy; every Strategy 3 action needs the 90-day warning",
           bool((acted["strategy"] > 0).all() and acted.loc[s3, "warning_required"].all()
                and not acted.loc[~s3, "warning_required"].any()),
           f"by primary strategy {acted['strategy'].value_counts().sort_index().to_dict()}; "
           f"{int(acted['warning_required'].sum()):,} need the warning")


def sample_checks(cfg: dict) -> None:
    """On the committed app samples: the old settings reproduce the figures
    before revision E exactly (figures/D_workbook_leq_default.json)."""
    print("\n15. Committed samples: settings switched back reproduce the earlier figures", flush=True)
    sys.path.insert(0, str(ROOT / "audit"))
    import unused_line_headline_figures as H
    ref = json.loads((ROOT / "specs/unused_line_management/figures/D_workbook_leq_default.json").read_text())
    old = A.with_overrides(cfg, OLD_SETTINGS)
    for ds in ["stress", "demo"]:
        got = H.figures(ds, old)
        diff = {k: (v, got[k]) for k, v in ref[ds].items() if got[k] != v}
        record(f"{ds}: every revision-E setting at its old value reproduces the Stage 0 figures exactly",
               not diff, f"{len(ref[ds])} figures compared; base {got['base_annual_value']:+,.2f}; "
                         f"screened {got['screened_accounts']:,}" + (f"; differ: {diff}" if diff else ""))


# ------------------------------------------------------------- Stage 5
def workbook_scenarios(cfg: dict) -> None:
    print("\n8. Workbook-reproduction scenarios", flush=True)
    ref = cfg["workbook"]["dashboard_reference"]
    worst, rows = 0.0, []
    for scn in A.SCENARIOS:
        g = W.dashboard(cfg)[scn]
        for k in ["change_in_fully_loaded_profit", "accounts_lost", "capital_released"]:
            worst = max(worst, abs(g[k] - ref[scn][k]) / abs(ref[scn][k]))
        rows.append(f"{scn} {g['change_in_fully_loaded_profit']:+,.0f} / {g['accounts_lost']:,.0f} lost / "
                    f"${g['capital_released']:,.0f} released")
    record("Conservative / Base / Aggressive (85% / 55%): profit change, accounts lost, capital released "
           "within +/-1%", worst <= 0.01, "; ".join(rows) + f"; largest difference {worst:.4%}")
    base = W.scenario(cfg, "base")
    seg_ref = ref["base_by_segment"]
    ws = max(abs(base.loc[s, "change_in_fully_loaded_profit"] - v["change_in_profit"]) / abs(v["change_in_profit"])
             for s, v in seg_ref.items())
    record("Base by segment within +/-1%", ws <= 0.01, f"largest difference {ws:.4%}")
    ccf = {s: cfg["capital"]["ccf_unused_card_lines"] for s in A.WORKBOOK_SEGMENTS}
    cor = W.scenario(cfg, "base", risk_weights=cfg["workbook_reproduction"]["corrected_risk_weights"], ccf=ccf).loc["total"]
    rel75 = dict(cfg["workbook_reproduction"]["corrected_risk_weights"], relationship=cfg["capital"]["risk_weight_non_transactor"])
    cor75 = W.scenario(cfg, "base", risk_weights=rel75, ccf=ccf).loc["total"]
    record("corrected weights reported (Relationship at 45%, and at 75% as the per-account test suggests)", True,
           f"45%: baseline RWA ${cor['baseline_rwa']:,.0f}, Base {cor['change_in_fully_loaded_profit']:+,.0f}, "
           f"capital released ${cor['capital_released']:,.0f}; Relationship 75%: baseline RWA "
           f"${cor75['baseline_rwa']:,.0f}, Base {cor75['change_in_fully_loaded_profit']:+,.0f}")


def lever_checks(f: pd.DataFrame, cfg: dict, label: str) -> None:
    print(f"\n9. Levers, response, scenarios, stress - {label}", flush=True)
    res = {s: L.run(f, cfg, s) for s in A.SCENARIOS}
    summ = {s: L.summary(res[s], cfg, f) for s in A.SCENARIOS}
    hv = [summ[s]["workbook_levers_headline"]["headline_value"] for s in A.SCENARIOS]
    record(f"{label}: low <= base <= high (headline annual value)", hv[0] <= hv[1] <= hv[2],
           " <= ".join(f"{v:+,.0f}" for v in hv))
    b = res["base"]
    comb = b["combined"]
    ident = np.allclose(comb["headline_value"], comb["card_profit_change"] - comb["drawdown_change"])
    keys = set(summ["base"]["workbook_levers_headline"])
    record(f"{label}: capital released never inside an annual value", bool(ident and "capital_released" not in keys),
           f"Base: annual {summ['base']['workbook_levers_headline']['headline_value']:+,.0f}; "
           f"capital released ${summ['base']['capital_released_one_time']:,.0f} (one-time, separate)")
    vt = np.allclose(comb["card_profit_change"], comb["cost_saving"] + comb["revenue"] + comb["lost_profit"]
                     + comb["avoided_loss"] + comb["drawdown_change"])
    record(f"{label}: value types reconcile to the change in card profit", bool(vt),
           ", ".join(f"{k} {summ['base']['workbook_levers_headline'][k]:+,.0f}" for k in L.VALUE_TYPES))
    sel = b["selection"]
    d = sel[sel["decrease"]]
    lim = f.loc[d.index, "limit_current"]
    floor = np.maximum(cfg["levers"]["system_mode"]["floor_minimum_line_usd"],
                       f.loc[d.index, "balance_current"].clip(lower=0) * cfg["levers"]["system_mode"]["floor_balance_multiple"])
    cut_ok = bool((d["cut"] <= lim * cfg["levers"]["max_reduction_per_review"] + 1e-6).all()
                  and (d["cut"] >= lim * cfg["levers"]["system_mode"]["min_cut_share"] - 1e-6).all()
                  and (d["cut"] >= cfg["levers"]["system_mode"]["min_cut_usd"]).all()
                  and (d["new_line"] >= floor - 1e-6).all())
    record(f"{label}: every cut <= 25% of the line, >= 15% and >= $500, new line >= max($500, balance x 1.2)",
           cut_ok, f"{len(d):,} accounts cut (Base)")
    cl = sel["closure"]
    record(f"{label}: closures only on dormant accounts inactive >= 24 months; closure and dormant right-sizing "
           "out of the headline while B6 is off", bool(
               (f.loc[cl, "rule_segment"] == "dormant").all()
               and (f.loc[cl, "months_since_last_transaction"] >= cfg["levers"]["system_mode"]["closure_min_inactive_months"]).all()
               and np.isclose(summ["base"]["pending_approval"]["headline_value"],
                              sum(L.lever_table(b, cfg, f).query("status == 'pending approval'")["headline_value"]))
               and not (b["combined"].loc[cl, "accounts_leaving"] > 0).any()),
           f"{int(cl.sum()):,} closures selected; pending approval {summ['base']['pending_approval']['headline_value']:+,.0f}")
    on = A.with_overrides(cfg, {"levers": {"dormant_closure_enabled": True, "dormant_rightsizing_enabled": True}})
    s_on = L.summary(L.run(f, on, "base"), on, f)
    record(f"{label}: switching B6 on moves those levers into the headline (config change only)",
           bool(s_on["workbook_levers_headline"]["accounts_leaving"] > summ["base"]["workbook_levers_headline"]["accounts_leaving"]
                and s_on["pending_approval"]["headline_value"] == 0),
           f"headline {summ['base']['workbook_levers_headline']['headline_value']:+,.0f} -> "
           f"{s_on['workbook_levers_headline']['headline_value']:+,.0f}")
    tr = f["rw"] == cfg["capital"]["risk_weight_transactor"]
    P = b["params"]
    st = L._state(f[tr], cfg, 0.0, P.loc[tr, "incr_rev"].where(P.loc[tr, "incr_rev"] > 0, 100.0), 1.0, 0.0)
    flip = bool(len(st["rwa"]) == 0 or (st["rwa"] > 0).all()) and bool(
        (L._state(f[tr], cfg, 0.0, 100.0, 1.0, 0.0)["rwa"]
         >= (f.loc[tr, "balance"] + 100 + cfg["capital"]["ccf_unused_card_lines"] * (f.loc[tr, "ucl"] - 100).clip(lower=0))
         * cfg["capital"]["risk_weight_non_transactor"] - 1e-6).all())
    record(f"{label}: a campaign / installment balance moves a transactor from 45% to 75%", flip,
           f"{int(tr.sum()):,} accounts at 45%")
    cl_only = b["per_lever"]["dormant_closure"]
    fw = L.forward_frame(f, cfg)
    stay = np.allclose(cl_only.loc[cl, "card_profit_change"],
                       -cl_only.loc[cl, "accounts_leaving"] * (fw.loc[cl, "card_profit"] + fw.loc[cl, "fixed_cost"]))
    record(f"{label}: leavers lose variable contribution; fixed cost stays", bool(stay))
    ex = summ["base"]["extra_levers"]["headline_value"]
    lt = L.lever_table(b, cfg, f)
    extra_sum = lt.loc[(lt["group"] != "workbook") & (lt["status"] == "headline"), "headline_value"].sum()
    wb_only = b["combined"][b["scope"]]["headline_value"].sum()
    record(f"{label}: extra levers reported apart from the workbook levers",
           bool(np.isclose(summ["base"]["workbook_levers_headline"]["headline_value"], wb_only)
                and np.isclose(ex, extra_sum)),
           f"workbook levers {wb_only:+,.0f}; extra {ex:+,.0f} (assumption-based; not in the reference workbook)")
    full = A.with_overrides(cfg, {"levers": {"scope_mode": "full_line_management"}})
    rf = L.run(f, full, "base")
    record(f"{label}: scope mode (B7) changes only the population", bool(
        rf["scope"].sum() >= b["scope"].sum() and (rf["scope"] | ~b["scope"]).all()),
           f"workbook scope {int(b['scope'].sum()):,} accounts; full line management {int(rf['scope'].sum()):,}")
    stv = L.stress(f, cfg)
    g = stv.attrs["go_no_go"]
    record(f"{label}: stress test 1x-2x; go/no-go (Base improves at {g['multiplier']}x)", g["go"],
           "; ".join(f"{m}x {v:+,.0f}" for m, v in stv["wb_headline_value"].items())
           + f"; at {g['multiplier']}x card profit alone {g['card_profit_change']:+,.0f}")
    neg = stv.index[stv["wb_card_profit_change"] < 0]
    want = ("stays positive" if not len(neg) else f"{float(neg.min()):g}x")
    record(f"{label}: B6 the robustness statement states its basis and where card profit alone turns negative",
           "including reduced risk" in g["statement"] and want in g["statement"], g["statement"])


# ------------------------------------------------------------- Stage 6
def treatment_checks(f: pd.DataFrame, cfg: dict, data_dir: Path, label: str) -> None:
    print(f"\n10. Treatment designer, compliance, fairness, timing - {label}", flush=True)
    from engine import run as ER
    pipe = ER.build_pipeline(data_dir)
    sup = set(pipe["suppressed"].suppressed["Masked Customer Number"])
    f = f.assign(protected=f["customer"].isin(sup))
    res = L.run(f, cfg, cfg["treatment"]["scenario_for_recommendations"])
    t = T.design(f, cfg, res, pipe["worklists"])
    prot_screened = f["screened"] & f["protected"]
    record(f"{label}: protected (suppressed) customers receive no action, before anything else",
           bool(not t.index.isin(f.index[f["protected"]]).any() and not res["selection"].loc[f["protected"], ["decrease", "campaign", "closure"]].any().any()),
           f"{int(prot_screened.sum()):,} screened accounts protected by the system's suppression")
    acted = t[t["recommended_levers"] != "none"]
    rcfg = cfg["treatment"]["reason_codes"]
    codes = set(rcfg)
    all_codes = acted["all_reason_codes"].str.split("; ").explode()
    record(f"{label}: every recommended action carries a reason code from the list",
           bool(acted["reason_code"].isin(codes).all() and all_codes.isin(codes).all()),
           f"{len(acted):,} accounts with an action; {acted['reason_code'].value_counts().to_dict()}")
    line = acted[acted["line_action"] != "none"]
    inact = line["reason_code"].eq("INACTIVITY")
    credit = line["reason_code"].eq("CREDIT_DETERIORATION")
    record(f"{label}: inactivity actions carry no adverse-action notice; credit actions do (with the FCRA check)",
           bool((~line.loc[inact, "adverse_action_notice"]).all() and line.loc[credit, "adverse_action_notice"].all()
                and line.loc[credit, "fcra_score_disclosure_check"].all()),
           f"{int(inact.sum()):,} inactivity, {int(credit.sum()):,} credit, "
           f"{int(line['reason_code'].eq('IDLE_LINE_RIGHTSIZING').sum()):,} idle-line right-sizing (notice: adverse action)")
    other = (all_codes == "OTHER").mean() if len(all_codes) else 0.0
    by_code = acted["reason_code"].value_counts()
    rule_ok = all(rcfg[c]["notice"] and (rcfg[c]["adverse_action_notice"] == (c in ("IDLE_LINE_RIGHTSIZING", "CREDIT_DETERIORATION")))
                  for c in ["IDLE_LINE_RIGHTSIZING", "CREDIT_DETERIORATION", "INACTIVITY", "INACTIVITY_NON_REISSUE",
                            "ENGAGEMENT_CAMPAIGN", "SUPPRESS_AUTO_INCREASE"])
    flags_ok = all(bool(rcfg[c]["compliance_flag"]) for c in ["IDLE_LINE_RIGHTSIZING", "INACTIVITY_NON_REISSUE",
                                                             "SUPPRESS_AUTO_INCREASE"])
    flagged = acted["all_reason_codes"].str.contains("IDLE_LINE_RIGHTSIZING|INACTIVITY_NON_REISSUE|SUPPRESS_AUTO_INCREASE")
    record(f"{label}: B3 one specific reason code per lever with its notice rule; OTHER below "
           f"{cfg['treatment']['other_max_share_of_actions']:.0%} of actions; compliance flags set",
           bool(other < cfg["treatment"]["other_max_share_of_actions"] and rule_ok and flags_ok
                and (acted.loc[flagged, "compliance_flags"] != "").all()
                and (acted["notice"] != "").all()),
           f"OTHER {other:.2%} of {len(all_codes):,} codes; primary: {by_code.to_dict()}")
    dec = acted["line_action"].eq("decrease")
    record(f"{label}: every decrease carries the 45-day over-limit fee / penalty-rate restriction",
           bool(acted.loc[dec, "fee_restriction_45_days"].all() and not acted.loc[~dec, "fee_restriction_45_days"].any()),
           f"{int(dec.sum()):,} decreases")
    names = list(L.LEVER_LABELS) + list(acted["recommended_levers"].str.split("; ").explode().unique())
    record(f"{label}: no lever proposes an inactivity fee", not any("fee" in n.lower() for n in names))
    trs = t["recommended_levers"].str.contains("transactor_rightsizing")
    record(f"{label}: transactor right-sizing is never recommended (config)", not bool(trs.any()))
    ml_cols = [c for c in t.columns if c.startswith("ml_")]
    record(f"{label}: the ML credit-limit model plays no part (B8): no ML column in the recommendations",
           not ml_cols, f"columns: {len(t.columns)}; ML columns: {ml_cols or 'none'}")
    pc = acted.groupby("segment")["pilot_cell"].apply(lambda s: (s == "holdout").sum() - round(
        cfg["treatment"]["pilot"]["holdout_share"] * len(s)))
    again = T.design(f, cfg, res, pipe["worklists"])["pilot_cell"]
    record(f"{label}: pilot holdout {cfg['treatment']['pilot']['holdout_share']:.0%} per segment, seeded "
           f"(same cells on a rerun)", bool((pc.abs() <= 0).all() and (again == t["pilot_cell"]).all()),
           acted["pilot_cell"].value_counts().to_dict().__repr__())
    rt = (t["review_together"] != "").sum()
    record(f"{label}: review-together flags against the L1 / L3 / L5 worklists", True,
           f"{int(rt):,} accounts flagged")
    fa = T.fairness(f, t, cfg)
    k = cfg["treatment"]["fairness"]["min_selected_per_group"]
    fd = fa["module_decreases_and_closures"]
    small = fd["selected"] < k
    record(f"{label}: four-fifths by metro on the module's own actions only; fewer than {k} selected in a metro "
           "-> 'insufficient sample', never pass / fail",
           bool(set(fa["summary"]) <= set(T.FAIRNESS_TESTS) and (fd.loc[small, "status"] == "insufficient sample").all()
                and fd["status"].isin(["pass", "fail", "insufficient sample"]).all()),
           "; ".join(f"{key}: {v['groups_failing']} fail, {v['groups_tested'] - v['groups_failing']} pass, "
                     f"{v['groups_insufficient']} insufficient sample of {v['groups']} metros ({v['selected']:,} selected)"
                     for key, v in fa["summary"].items()) + ". " + fa["increases_note"])
    tt = T.timing_table(L.lever_table(res, cfg, f), cfg)
    record(f"{label}: year-1 value = full annual value x the lever's year-1 share (every lever has timing)",
           bool(np.allclose(tt["year1_value"], tt["full_annual_value"] * tt["year1_share"]) and tt["year1_share"].notna().all()),
           f"headline levers year 1 ${tt.loc[tt['status'] == 'headline', 'year1_value'].sum():,.0f} "
           f"vs full ${tt.loc[tt['status'] == 'headline', 'full_annual_value'].sum():,.0f}")


# ------------------------------------------------------------- 5, 6
def cross_check(bundle: Path | None, frame: Path | None, cfg: dict) -> None:
    print("\n5. Portfolio cross-check (s.2.7)", flush=True)
    if bundle:
        z = zipfile.ZipFile(bundle)
        cv = pd.read_parquet(io.BytesIO(z.read("tables/customer_view.parquet")))
        wl = pd.read_parquet(io.BytesIO(z.read("tables/worklist_L2.parquet")))
        card = cv[cv["holds_card"]].copy()
        tr = (card["months_transactor_12m"] >= 12) & (card["months_inactive_12m"] < 12)
        rw = np.where(tr, cfg["capital"]["risk_weight_transactor"], cfg["capital"]["risk_weight_non_transactor"])
        ucl = card["avg_undrawn_12m"].clip(lower=0)
        rate = A.annual_capital_cost_rate(cfg)
        got = {"ucl": ucl.sum(), "rwa_unused": (cfg["capital"]["ccf_unused_card_lines"] * ucl * rw).sum()}
        got["capital_cost_unused"] = got["rwa_unused"] * rate
        got["hqla"] = ucl.sum() * cfg["liquidity"]["lcr_outflow_unused_card_lines"]
        got["liquidity_cost"] = got["hqla"] * cfg["liquidity"]["negative_carry"]
        got["carrying_cost"] = got["capital_cost_unused"] + got["liquidity_cost"]
        worst = max(abs(got[k] * 5 - v) / v for k, v in BRIEF_27.items())
        record("s.2.7 reproduced from the 100k bundle by the brief's method (x5), +/-5%", worst <= 0.05,
               "; ".join(f"{k} ${got[k] * 5 / 1e6:,.2f}M" for k in BRIEF_27) + f"; largest difference {worst:.2%}; "
               f"transactor share {tr.mean():.1%} (brief 27%)")
        card["carry"] = (cfg["capital"]["ccf_unused_card_lines"] * ucl * rw * rate
                         + ucl * cfg["liquidity"]["lcr_outflow_unused_card_lines"] * cfg["liquidity"]["negative_carry"])
        card["group"] = card["Masked Customer Number"].map(wl.set_index("Masked Customer Number")["action"].map(L2_GROUP))
        g = card.groupby("group").agg(carry=("carry", "sum"), card_net=("card_net", "sum"))
        g["after"] = g["card_net"] - g["carry"]
        worst_g = max(max(abs(g.loc[k, "carry"] * 5 - c0) / abs(c0), abs(g.loc[k, "after"] * 5 - p0) / abs(p0))
                      for k, (c0, p0) in BRIEF_27_GROUPS.items())
        record("s.2.7 by L2 group (carrying cost; card profit after it) from the 100k bundle, +/-5%",
               worst_g <= 0.05, "; ".join(f"{k} ${g.loc[k, 'carry'] * 5 / 1e6:.3f}M / ${g.loc[k, 'after'] * 5 / 1e6:.2f}M"
                                          for k in BRIEF_27_GROUPS) + f"; largest difference {worst_g:.2%}")
    if frame:
        # Same population as s.2.7: every card account with a ledger row in
        # the trailing 12 cycles (closed and charged-off ones included).
        acc, meta = D.load_account_frame(frame)
        leq = meta["leq_unassigned_measured"]
        # s.2.7 measured the unused line after the month's payment: compare like with like
        cfg = A.with_overrides(cfg, {"balance_basis": {"cost": "after_payment"}})
        c = X.account_costs(acc, cfg, leq_unassigned=leq)
        t = X.totals(c)
        diffs = {k: t[k] * 5 / v - 1 for k, v in BRIEF_27.items()}
        worst = max(abs(v) for v in diffs.values())
        detail = ("; ".join(f"{k} ${t[k] * 5 / 1e6:,.2f}M ({diffs[k]:+.1%})" for k in BRIEF_27)
                  + f"; transactor share {t['transactor_share']:.1%} (s.2.7: 26-27%); "
                  f"RW basis {c['rw_basis'].value_counts(normalize=True).round(3).to_dict()}")
        if worst <= 0.05:
            record("s.2.7 from the module's own per-account file (x5), +/-5%", True, detail)
        else:
            # The expected difference is the transactor test (answer 5): s.2.7
            # used the account-type label, which ignores plan and promotional
            # balances. Test that explanation rather than assert it.
            loose = A.with_overrides(cfg, {"transactor_test": {"plan_promotional_or_bt_balance_disqualifies": False}})
            t2 = X.totals(X.account_costs(acc, loose, leq_unassigned=leq))
            worst2 = max(abs(t2[k] * 5 / v - 1) for k, v in BRIEF_27.items())
            record("s.2.7 from the module's own per-account file (x5): outside +/-5%, explained by the "
                   "transactor test (with the plan / promotional rule off it is within +/-5%)",
                   worst2 <= 0.05, detail + f"; plan / promo rule off: transactor share "
                   f"{t2['transactor_share']:.1%}, largest difference {worst2:.1%}")


_LOAD_STEP = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
import psutil
from engine.unused_lines import assumptions as A, data as D, exposure as X
t0 = time.time()
cfg, _ = A.load()
acc, meta = D.load_account_frame(sys.argv[2])
c = X.account_costs(acc, cfg, leq_unassigned=meta["leq_unassigned_measured"])
X.current_rules(c, cfg); X.totals(c)
mi = psutil.Process().memory_info()
print(json.dumps({"accounts": len(c), "seconds": round(time.time() - t0, 1),
                  "peak_gb": round((getattr(mi, "peak_wset", None) or mi.rss) / 1e9, 3)}))
"""


_APP_STEP = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
import psutil
from pathlib import Path
from streamlit.testing.v1 import AppTest
pages = sorted((Path(sys.argv[1]) / "unused_lines_app" / "pages").glob("*.py"))
out = []
for ds in ["stress", "demo"]:
    for view in ["executive", "analyst"]:
        for p in pages:
            t0 = time.time()
            at = AppTest.from_file(str(p), default_timeout=300)
            at.session_state["dataset"] = ds
            at.session_state["view"] = view
            at.run()
            text = [m.value for m in at.markdown] + [c.value for c in at.caption]
            out.append({"dataset": ds, "view": view, "page": p.name, "seconds": round(time.time() - t0, 2),
                        "exceptions": [str(e.value)[:200] for e in at.exception], "titles": len(at.title),
                        "text": text, "infos": [i.value for i in at.info]})
mi = psutil.Process().memory_info()
print(json.dumps({"pages": out, "peak_gb": round((getattr(mi, "peak_wset", None) or mi.rss) / 1e9, 3)}))
"""
# Revision E: the nine pages that tell the project report's story, in its order.
DECISION_PAGES = ["01_Summary.py", "02_Problem.py", "03_Cost.py", "04_Groups.py", "05_Strategies.py", "06_Value.py",
                  "07_Implementation.py", "08_Protection.py", "09_Evidence.py"]
TECHNICAL_LABELS = ["Screened accounts", "Headline value", "Go/no-go", "Pending approval (B6)", "Capital released"]
JARGON = r"\b(PD|LGD|LEQ|RWA|LCR)\b"   # never in the executive view (the report's terms instead)


# Code the module must never change (brief s.8; read and called only).
PROTECTED_PATHS = ["engine/core", "engine/levers", "engine/ml", "engine/governance", "engine/run.py",
                   "engine/config", "engine/export_bundle.py", "app", "generator/synth", "generator/validate",
                   "generator/config"]
ALLOWED_NEW = {"generator/synth/unused_line_stress.py"}
BASE_COMMIT = "b660bb8"


def guardrails() -> None:
    print("\n12. Guardrails and regression", flush=True)
    r = subprocess.run(["git", "diff", "--name-status", BASE_COMMIT, "HEAD", "--", *PROTECTED_PATHS],
                       cwd=ROOT, capture_output=True, text=True)
    changed = [ln.split("\t")[-1] for ln in r.stdout.splitlines() if ln.strip()]
    bad = [p for p in changed if p not in ALLOWED_NEW]
    record("no change to L1-L6, L2, the ML model, NEP / CEV, suppression, routing, fairness, the six-lever app or "
           f"existing generator modules since main {BASE_COMMIT}", r.returncode == 0 and not bad,
           f"changed under protected paths: {changed or 'none'} (allowed: new {sorted(ALLOWED_NEW)})")
    r = subprocess.run(["git", "diff", BASE_COMMIT, "HEAD", "--", "generator/run.py"], cwd=ROOT,
                       capture_output=True, text=True)
    removed = [ln for ln in r.stdout.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    record("generator/run.py: additions only, apart from the cherry-picked negative_control fix (966988a)",
           len(removed) <= 1, f"{len(removed)} line(s) removed: {removed}")
    src = [p for d in ["engine/unused_lines", "unused_lines_app"] for p in (ROOT / d).rglob("*.py")]
    uses = [str(p.relative_to(ROOT)) for p in src
            if any(x in p.read_text(encoding="utf-8") for x in ("engine.ml", "engine import ml", "ml_action"))]
    record("B8: the module and its app never read the ML credit-limit model (engine/ml untouched)", not uses,
           f"{len(src)} source files scanned; reading ML: {uses or 'none'}")


def regression() -> None:
    """The byte-identity and engine-regression audit, run from this suite."""
    t0 = time.time()
    r = subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "audit" / "audit_unused_line_data_additions.py")],
                       cwd=ROOT, capture_output=True, text=True)
    lines = r.stdout.splitlines()
    total = next((ln for ln in reversed(lines) if "PASSED" in ln), "no summary")
    ident = next((ln.strip() for ln in lines if "every pre-existing file byte-identical" in ln), "")
    eng = next((ln.strip() for ln in lines if "run_summary.json equals the engine baseline" in ln), "")
    record("byte-identity of every existing generator profile (incl. negative_control) and the engine regression "
           "(audit_unused_line_data_additions.py)", r.returncode == 0,
           f"{total}; {ident[:160]}; {eng[:120]} ({time.time() - t0:.0f}s)")


def app_checks() -> None:
    print("\n11. App on the committed samples", flush=True)
    samples = ROOT / "samples" / "unused_lines"
    info = {d.name: json.loads((d / "meta.json").read_text()) for d in samples.iterdir() if (d / "meta.json").exists()}
    record("committed samples present (stress book, 5k demo), small files only",
           set(info) >= {"stress", "demo"} and all(sum(i["files_mb"].values()) < 60 for i in info.values()),
           "; ".join(f"{k}: {i['card_accounts']:,} accounts, {sum(i['files_mb'].values()):.1f} MB, built in "
                     f"{i['build_seconds']}s at peak {i['build_peak_memory_gb']} GB" for k, i in info.items()))
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", _APP_STEP, str(ROOT)], capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode:
        record("every app page runs on both datasets", False, r.stderr[-300:])
        return
    s = json.loads(r.stdout.strip().splitlines()[-1])
    bad = [f"{p['dataset']}/{p['view']}/{p['page']}" for p in s["pages"] if p["exceptions"] or not p["titles"]]
    record("every app page runs in both views on both datasets without an exception", not bad,
           f"{len(s['pages'])} page runs; slowest {max(p['seconds'] for p in s['pages'])}s" + (f"; failing {bad}" if bad else ""))
    exe = [p for p in s["pages"] if p["view"] == "executive"]
    badges = [f"{p['dataset']}/{p['page']}" for p in exe if any('class="vt"' in t for t in p["text"])]
    tags = sorted({p["page"] for p in exe if any('class="tag"' in t for t in p["text"])})
    tech =sorted({f"{p['page']}: {lab}" for p in exe if p["page"] in DECISION_PAGES
                   for lab in TECHNICAL_LABELS for t in p["text"] if lab in t}
                  | {f"{p['page']}: {m}" for p in exe if p["page"] in DECISION_PAGES
                     for t in p["text"] for m in re.findall(JARGON, t)})
    gated = [f"{p['dataset']}/{p['page']}" for p in exe if p["page"] not in DECISION_PAGES
             and not any("Analyst view" in i for i in p["infos"])]
    record("executive view: no PD / LGD / LEQ / RWA / LCR or technical labels on the nine report pages; value-type "
           "tags only in the worked example; analyst-only pages gated",
           not badges and not tech and not gated and tags == ["03_Cost.py"],
           f"jargon or technical labels {tech or 'none'}; badges {badges or 'none'}; value-type tags on {tags}; "
           f"ungated {gated or 'none'}")
    story = [p for p in exe if p["page"] in DECISION_PAGES]
    heads = {p["page"]: sum('class="headline"' in t for t in p["text"]) for p in story}
    kpis = {p["page"]: sum(t.count('class="kpi') for t in p["text"]) for p in story}
    order = [p["page"] for p in story if p["dataset"] == "stress"]
    record("page rules: one headline sentence per page, at most four figure cards, the nine pages in the report's order",
           all(v == 1 for v in heads.values()) and all(v <= 4 for v in kpis.values()) and order == DECISION_PAGES,
           f"headlines {sorted(set(heads.values()))}; most cards on a page {max(kpis.values())}")
    ana = [p for p in s["pages"] if p["view"] == "analyst"]
    record("analyst view: every page shows its full content (no analyst-only gate)",
           not any(p["infos"] and any("Analyst view" in i for i in p["infos"]) for p in ana))
    record("app runtime on the committed samples under 2 GB (all pages, both views, both datasets, one process)",
           s["peak_gb"] < 2.0, f"peak {s['peak_gb']} GB")


def performance(frame: Path | None, frame_json: Path | None) -> None:
    print("\n6. Performance", flush=True)
    if frame_json:
        s = json.loads(Path(frame_json).read_text())
        record("100k per-account file built from the raw portfolio (offline step)", True,
               f"{s['accounts']:,} accounts; {s['seconds']}s; peak {s['peak_gb']} GB; file {s['file_mb']} MB")
    if frame:
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", _LOAD_STEP, str(ROOT), str(frame)],
                           capture_output=True, text=True)
        if r.returncode:
            record("100k per-account file loads with the cost layer", False, r.stderr[-300:])
            return
        s = json.loads(r.stdout.strip().splitlines()[-1])
        record("100k per-account file loads with the cost layer in a fresh process under 2 GB",
               s["peak_gb"] < 2.0, f"{s['accounts']:,} accounts; {s['seconds']}s; peak {s['peak_gb']} GB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=None, help="where to generate (default: a temp dir, removed after)")
    ap.add_argument("--data", nargs="*", default=None, help="existing portfolios instead of generating")
    ap.add_argument("--bundle-100k", default=None)
    ap.add_argument("--frame-100k", default=None)
    ap.add_argument("--frame-100k-json", default=None)
    ap.add_argument("--regression", action="store_true",
                    help="also run the byte-identity and engine-regression audit (about 5 minutes)")
    a = ap.parse_args()
    cfg, sha = A.load()
    print(f"assumptions sha256 {sha[:12]}")
    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="unused_line_module_audit_"))
    try:
        worked_examples(cfg)
        workbook(cfg)
        workbook_scenarios(cfg)
        dirs = [Path(d) for d in a.data] if a.data else []
        if not dirs:
            for p in PROFILES:
                subprocess.run([sys.executable, "-W", "ignore", "-m", "generator.run", "--profile", p,
                                "--out", str(work / p)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
                dirs.append(work / p)
        for d in dirs:
            t0 = time.time()
            acc, meta = D.account_frame(d)
            leq = meta["leq_unassigned_measured"]
            costs = X.account_costs(acc, cfg, leq_unassigned=leq)
            label = d.name
            print(f"\n   {label}: {len(acc):,} accounts, per-account file {time.time() - t0:.0f}s, "
                  f"Unassigned LEQ (mean Behavioral CCF) {leq:.3f}")
            invariants(costs, cfg, label)
            toggles(acc, cfg, leq, label)
            f = segment_checks(acc, meta, cfg, label)
            correction_checks(acc, meta, f, cfg, label)
            balance_basis_checks(acc, meta, f, cfg, label)
            lever_checks(f, cfg, label)
            strategy_checks(f, cfg, label)
            treatment_checks(f, cfg, d, label)
        cross_check(Path(a.bundle_100k) if a.bundle_100k else None,
                    Path(a.frame_100k) if a.frame_100k else None, cfg)
        performance(Path(a.frame_100k) if a.frame_100k else None,
                    Path(a.frame_100k_json) if a.frame_100k_json else None)
        sample_checks(cfg)
        app_checks()
        guardrails()
        if a.regression:
            regression()
    finally:
        if not a.workdir:
            shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 100)
    for name, verdict, _ in RESULTS:
        print(f"{verdict:<5} {name}")
    n_fail = sum(v == "FAIL" for _, v, _ in RESULTS)
    print("=" * 100)
    print(f"{len(RESULTS) - n_fail}/{len(RESULTS)} PASSED" + (f", {n_fail} FAILED" if n_fail else ""))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
