"""Equivalence test for the pre-computed results bundle (engine/export_bundle.py
writer, app/lib/results_bundle.py loader). Run as a script, like every other
file in this directory - there is no pytest suite in this repo to join.

    python audit/audit_results_bundle.py

For the bundled demo portfolio plus its negative control: runs the pipeline
directly, exports a bundle from the SAME portfolios, loads the bundle back,
and asserts that every value a page displays is identical (exact for counts
and strings, tolerance for floats) between the live result and the
bundle-loaded result. A pass here is the claim that a hosted app showing a
bundle shows the same numbers a live engine run would have shown.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.run import build_pipeline  # noqa: E402
from engine.core import leverage_capital as LEV  # noqa: E402
from engine.export_bundle import export_bundle  # noqa: E402
from app.lib.results_bundle import load_bundle_from_bytes  # noqa: E402

DEMO_DIR = ROOT / "generator" / "out" / "demo"
CONTROL_DIR = ROOT / "generator" / "out" / "negative_control"
BUNDLE_OUT = ROOT / "audit" / "_scratch_bundle_equivalence.zip"
POLICY = LEV.DEFAULT_POLICY_NAME
TOL = 0.01  # dollars - the task's "explicit tolerance for floats"


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def close(a, b, tol=TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if (isinstance(a, float) and np.isnan(a)) or (isinstance(b, float) and np.isnan(b)):
        return (isinstance(a, float) and np.isnan(a)) and (isinstance(b, float) and np.isnan(b))
    return abs(float(a) - float(b)) <= tol


results = []  # (name, passed, detail)


def check(name: str, condition: bool, detail: str = ""):
    results.append((name, bool(condition), detail))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f" — {detail}" if detail and not condition else ""))


sec("Run the pipeline directly (demo + control) — this is the reference")
t0 = time.time()
live = build_pipeline(DEMO_DIR, POLICY)
live_control = build_pipeline(CONTROL_DIR, POLICY)
live_elapsed = time.time() - t0
print(f"  {len(live['customer_view']):,} customers, built in {live_elapsed:.1f}s")

sec("Export a bundle from the same two portfolios")
t0 = time.time()
manifest = export_bundle(DEMO_DIR, BUNDLE_OUT, compare_to=CONTROL_DIR,
                         leverage_policy_name=POLICY)
export_elapsed = time.time() - t0
bundle_bytes_count = BUNDLE_OUT.stat().st_size
print(f"  bundle: {bundle_bytes_count / 1e6:.2f} MB, exported in {export_elapsed:.1f}s")

sec("Load the bundle back through the app's own loader")
t0 = time.time()
bundled, meta, gate_report_bundled = load_bundle_from_bytes(
    BUNDLE_OUT.read_bytes(), BUNDLE_OUT.name)
load_elapsed = time.time() - t0
print(f"  loaded in {load_elapsed:.2f}s — schema v{meta.schema_version}, "
     f"{meta.customers_analysed:,} customers")

live_cv = live["customer_view"]
bundled_cv = bundled["customer_view"]

sec("KPIs — the Home page's headline numbers")
check("customer count", len(live_cv) == len(bundled_cv),
     f"{len(live_cv)} vs {len(bundled_cv)}")
check("portfolio NEP", close(live_cv["trailing_12m_net_economic_profit"].sum(),
                            bundled_cv["trailing_12m_net_economic_profit"].sum()))
live_below = int(live_cv["is_below_cost"].sum())
bundled_below = int(bundled_cv["is_below_cost"].sum())
check("below-cost count", live_below == bundled_below, f"{live_below} vs {bundled_below}")
live_loss = -live_cv.loc[live_cv["is_below_cost"], "trailing_12m_net_economic_profit"].sum()
bundled_loss = -bundled_cv.loc[bundled_cv["is_below_cost"], "trailing_12m_net_economic_profit"].sum()
check("total loss to route", close(live_loss, bundled_loss))
check("suppressed count", len(live["suppressed"].suppressed) == len(bundled["suppressed"].suppressed))

sec("CEV bands — distribution must match exactly")
live_bands = live_cv["cev_band"].astype(str).value_counts().sort_index()
bundled_bands = bundled_cv["cev_band"].astype(str).value_counts().sort_index()
check("cev_band distribution", live_bands.equals(bundled_bands),
     f"{live_bands.to_dict()} vs {bundled_bands.to_dict()}")

sec("Routing summary — index, order, counts and loss amounts")
live_rsum = live["routing_summary"]
bundled_rsum = bundled["routing_summary"]
check("routing_summary index order",
     list(live_rsum.index.fillna("__NAN__")) == list(bundled_rsum.index.fillna("__NAN__")),
     f"{list(live_rsum.index)} vs {list(bundled_rsum.index)}")
check("routing_summary customers column", live_rsum["customers"].tolist() == bundled_rsum["customers"].tolist())
loss_matches = all(close(a, b) for a, b in zip(live_rsum["total_loss"], bundled_rsum["total_loss"]))
check("routing_summary total_loss column", loss_matches)

sec("Lever sizes")
for code in ["L1", "L2", "L3", "L4", "L5", "L6"]:
    ls, bs = live["sizes"][code], bundled["sizes"][code]
    check(f"{code} priced_value_usd", close(ls.priced_value_usd, bs.priced_value_usd), code)
    check(f"{code} unpriced_context_usd", close(ls.unpriced_context_usd, bs.unpriced_context_usd), code)
    check(f"{code} is_priced property", ls.is_priced == bs.is_priced, code)
    check(f"{code} basis text", ls.basis == bs.basis, code)

sec("Lever gates (the only live-lever attribute any page reads)")
for code in ["L1", "L2", "L3", "L4", "L5", "L6"]:
    check(f"{code} gates", list(live["levers"][code].gates) == list(bundled["levers"][code].gates), code)

sec("Worklist counts and actions, per lever")
for code in ["L1", "L2", "L3", "L4", "L5", "L6"]:
    lwl, bwl = live["worklists"][code], bundled["worklists"][code]
    check(f"{code} worklist row count", len(lwl) == len(bwl), f"{len(lwl)} vs {len(bwl)}")
    if len(lwl) and "action" in lwl.columns:
        lactions = lwl["action"].value_counts().sort_index()
        bactions = bwl["action"].value_counts().sort_index()
        check(f"{code} action counts", lactions.equals(bactions))
    if len(lwl):
        l_ids = set(lwl["Masked Customer Number"])
        b_ids = set(bwl["Masked Customer Number"])
        check(f"{code} worklist membership", l_ids == b_ids)

sec("Fairness tables")
lf, bf = live["fairness"], bundled["fairness"]
check("fairness.proxy_method", lf["proxy_method"] == bf["proxy_method"])
check("fairness.score_any_failure", lf["score_any_failure"] == bf["score_any_failure"])
check("fairness.treatment_any_failure", lf["treatment_any_failure"] == bf["treatment_any_failure"])
for key in ["score_fairness", "treatment_fairness"]:
    lt, bt = lf[key].reset_index(drop=True), bf[key].reset_index(drop=True)
    same_shape = lt.shape == bt.shape
    check(f"fairness.{key} shape", same_shape, f"{lt.shape} vs {bt.shape}")
    if same_shape and len(lt):
        rates_match = np.allclose(lt["selection_rate"], bt["selection_rate"], atol=1e-9)
        passes_match = (lt["passes"] == bt["passes"]).all()
        check(f"fairness.{key} selection_rate + passes", rates_match and passes_match)
by_tier_both_none = lf["score_fairness_by_product_tier"] is None and bf["score_fairness_by_product_tier"] is None
by_tier_both_present = lf["score_fairness_by_product_tier"] is not None and bf["score_fairness_by_product_tier"] is not None
check("fairness.score_fairness_by_product_tier presence matches",
     by_tier_both_none or by_tier_both_present)

sec("ML — action counts and treatment fairness (if the ML model is deployed)")
check("ml_available matches", live["ml_available"] == bundled["ml_available"])
if live["ml_available"]:
    live_actions = live_cv["ml_action"].value_counts().sort_index()
    bundled_actions = bundled_cv["ml_action"].value_counts().sort_index()
    check("ml_action counts", live_actions.equals(bundled_actions),
         f"{live_actions.to_dict()} vs {bundled_actions.to_dict()}")
    lmf, bmf = live["ml_fairness"], bundled["ml_fairness"]
    check("ml_fairness.treatment_any_failure", lmf["treatment_any_failure"] == bmf["treatment_any_failure"])
    lt, bt = lmf["treatment_fairness"].reset_index(drop=True), bmf["treatment_fairness"].reset_index(drop=True)
    if len(lt):
        check("ml_fairness.treatment_fairness selection_rate",
             np.allclose(lt["selection_rate"], bt["selection_rate"], atol=1e-9))
else:
    print("  (skipped — no trained ML bundle in this environment)")

sec("Negative-control gate report")
check("gate_report present", gate_report_bundled is not None)
if gate_report_bundled is not None:
    from engine.governance import negative_control as NEGCTL  # noqa: E402
    from engine.run import portfolio_defect_count, MECHANISM_VARIED_IN_CONTROL  # noqa: E402
    gt_demo = portfolio_defect_count(DEMO_DIR)
    gt_ctrl = portfolio_defect_count(CONTROL_DIR)
    gate_results = [NEGCTL.check_defects(gt_demo, gt_ctrl)]
    for code, lever in live["levers"].items():
        gate_results.append(NEGCTL.check(
            lever, live_control["levers"][code], MECHANISM_VARIED_IN_CONTROL[code],
            live["customer_view"], live["populations"][code],
            live_control["customer_view"], live_control["populations"][code]))
    live_gate = NEGCTL.report(gate_results).reset_index(drop=True)
    bundled_gate = gate_report_bundled.reset_index(drop=True)
    check("gate_report row count", len(live_gate) == len(bundled_gate))
    check("gate_report lever order", live_gate["lever"].tolist() == bundled_gate["lever"].tolist())
    check("gate_report status column", live_gate["status"].tolist() == bundled_gate["status"].tolist())
    for col in ["driver_ratio", "value_ratio"]:
        both = pd.concat([live_gate[col], bundled_gate[col]], axis=1)
        ok = all(close(a, b, tol=1e-4) for a, b in zip(live_gate[col], bundled_gate[col]))
        check(f"gate_report {col}", ok)

sec("Manifest reconciliation — the headline totals the manifest claims")
check("manifest portfolio_nep_usd", close(manifest["headline_totals"]["portfolio_nep_usd"],
                                         live_cv["trailing_12m_net_economic_profit"].sum()))
check("manifest below_cost_count", manifest["headline_totals"]["below_cost_count"] == live_below)

sec("MEASUREMENTS")
print(f"  export time (demo + control): {export_elapsed:.1f}s")
print(f"  bundle size: {bundle_bytes_count / 1e6:.2f} MB")
print(f"  load time: {load_elapsed:.2f}s")

BUNDLE_OUT.unlink(missing_ok=True)

sec("RESULT TABLE")
n_pass = sum(1 for _, ok, _ in results if ok)
n_fail = len(results) - n_pass
width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"  {'PASS' if ok else 'FAIL':5} {name.ljust(width)}" + (f"  {detail}" if detail and not ok else ""))

sec(f"{n_pass}/{len(results)} CHECKS PASSED" if n_fail == 0 else
   f"{n_fail} CHECK(S) FAILED out of {len(results)}")
if n_fail:
    raise SystemExit(1)
