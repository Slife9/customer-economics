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

Prints a PASS/FAIL table; exits 1 if any check FAILs.
"""
from __future__ import annotations
import argparse
import io
import json
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
    el = c["pd_12m"].fillna(0) * c["lgd"].fillna(cfg["workbook"]["portfolio"]["lgd"]) * c["leq"] * c["ucl"]
    record(f"{label}: drawdown loss = annual PD (Table8 PD 12 Month) x LGD x LEQ x unused line",
           bool(np.allclose(c["drawdown_el"], el)), f"{int(c['pd_missing'].sum())} accounts without a PD")
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
    record(f"{label}: 'current' basis uses the reporting-date line and balance",
           bool(np.allclose(now["ucl"], acc["ucl_current"].fillna(0)) and np.allclose(base["ucl"], acc["ucl_avg_12m"].fillna(0))))


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
    a = ap.parse_args()
    cfg, sha = A.load()
    print(f"assumptions sha256 {sha[:12]}")
    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="unused_line_module_audit_"))
    try:
        worked_examples(cfg)
        workbook(cfg)
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
            segment_checks(acc, meta, cfg, label)
        cross_check(Path(a.bundle_100k) if a.bundle_100k else None,
                    Path(a.frame_100k) if a.frame_100k else None, cfg)
        performance(Path(a.frame_100k) if a.frame_100k else None,
                    Path(a.frame_100k_json) if a.frame_100k_json else None)
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
