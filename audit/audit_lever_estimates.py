"""Acceptance audit for the lever valuation rebuild
(specs/lever_valuation_rebuild/SPEC_lever_valuation_rebuild.md section 7).
Run as a script, like every other file in this directory - there is no
pytest suite in this repo to join.

    python audit/audit_lever_estimates.py
    python audit/audit_lever_estimates.py --bundle-100k <results bundle zip>
    python audit/audit_lever_estimates.py --expected <expected values json>

Fixtures:
  5k demo     full engine pipeline on generator/out/demo, default leverage
              regime (Tier 1, Case B)
  100k bundle a results bundle (schema v2) exported by this engine from the
              100,000-customer portfolio under Case A (SLR). The engine's own
              scenario outputs are read from the bundle - L4 cannot be
              recomputed from a bundle because it needs the raw driver table.

Compares the ENGINE's scenario outputs (not the spec's reference script)
with the expected values. Tolerance: +/-0.5% for L1, L2, L3, L5, L6 totals,
components and numeric extras; +/-15% for L4 (the engine windows the
trailing 12 cycles where the reference scales the full history by 12/36 -
the difference is explained in the output). Counts are compared exactly.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.run import build_pipeline, portfolio_defect_count, MECHANISM_VARIED_IN_CONTROL  # noqa: E402
from engine.core import leverage_capital as LEV  # noqa: E402
from engine.levers import assumptions as ASSUME  # noqa: E402
from engine.levers import summary as LSUMMARY  # noqa: E402
from engine.levers import (l1_rewards, l2_lines, l3_pricing, l4_cost_to_serve,  # noqa: E402
                           l5_retention, l6_crosssell)
from engine.governance import negative_control as NEGCTL  # noqa: E402
from app.lib.results_bundle import load_bundle_from_bytes  # noqa: E402

SPEC_DIR = ROOT / "specs" / "lever_valuation_rebuild"
DEMO_DIR = ROOT / "generator" / "out" / "demo"
CONTROL_DIR = ROOT / "generator" / "out" / "negative_control"
DEFAULT_BUNDLE_100K = Path(os.environ.get("TEMP", "/tmp")) / "bundle_100k_v2.zip"
MODULES = {"L1": l1_rewards, "L2": l2_lines, "L3": l3_pricing, "L4": l4_cost_to_serve,
           "L5": l5_retention, "L6": l6_crosssell}
TOL = {"L1": 0.005, "L2": 0.005, "L3": 0.005, "L4": 0.15, "L5": 0.005, "L6": 0.005}
COUNT_EXTRAS = {"offered_fee", "targeted", "flagged", "customers"}
RATIO_EXTRAS = {"breakeven_keep_rate", "breakeven_quality"}  # expected rounded to 2dp

results: list[tuple[str, bool, str]] = []


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def rel(a: float, b: float) -> float:
    if b == 0:
        return abs(a)
    return abs(a - b) / abs(b)


def engine_headline(code: str, scen: dict) -> float:
    return scen["extras"]["net_conditional"] if code == "L5" else scen["total_usd"]


def compare_fixture(label: str, sizes: dict, expected: dict):
    sec(f"{label}: engine scenario outputs vs expected values")
    for code, exp_lever in expected.items():
        s = sizes[code]
        if not s.has_scenarios:
            check(f"{label} {code} has scenario outputs", False,
                  "no scenarios - a pre-rebuild (schema v1) bundle?")
            continue
        tol = TOL[code]
        for sc in ASSUME.SCENARIOS:
            e, g = exp_lever[sc], s.scenarios[sc]
            tk = "net_conditional" if code == "L5" else "total"
            got = engine_headline(code, g)
            r = rel(got, e[tk])
            check(f"{label} {code} {sc} total", r <= tol,
                  f"engine {got:,.2f} vs expected {e[tk]:,.2f}, {r:.3%} (tol {tol:.1%})")
            for cname, ev in e["components"].items():
                gv = g["components"].get(cname, {}).get("value_usd")
                if gv is None:
                    check(f"{label} {code} {sc} component {cname}", False, "missing in engine output")
                    continue
                rc = rel(gv, ev)
                if rc > tol or code == "L4":
                    check(f"{label} {code} {sc} component {cname}", rc <= tol,
                          f"engine {gv:,.2f} vs {ev:,.2f}, {rc:.3%}")
            bad = []
            for k, ev in e.items():
                if k in ("components", tk):
                    continue
                gv = g["extras"].get(k)
                if isinstance(ev, str):
                    if gv != ev:
                        bad.append(f"{k}: {gv!r} vs {ev!r}")
                elif gv is None:
                    bad.append(f"{k}: missing")
                elif k in COUNT_EXTRAS:
                    if round(float(gv), 6) != round(float(ev), 6):
                        bad.append(f"{k}: {gv} vs {ev}")
                elif k in RATIO_EXTRAS:
                    if abs(float(gv) - float(ev)) > 0.005 + 1e-9:
                        bad.append(f"{k}: {float(gv):.4f} vs {ev}")
                elif rel(float(gv), float(ev)) > tol:
                    bad.append(f"{k}: {float(gv):,.2f} vs {float(ev):,.2f} ({rel(float(gv), float(ev)):.2%})")
            if code == "L4":
                # Annual volumes legitimately differ (window vs scaled history) -
                # shown, judged only through the +/-15% total.
                g_calls = g["extras"]["annual_avoidable_calls"]
                g_paper = g["extras"]["annual_paper_statements"]
                if sc == "base":
                    print(f"        L4 annual avoidable calls: engine (trailing 12 cycles) "
                          f"{g_calls:,.0f} vs reference (full history x 12/36) "
                          f"{e['annual_avoidable_calls']:,.0f} "
                          f"({g_calls / e['annual_avoidable_calls'] - 1:+.1%})")
                    print(f"        L4 annual paper statements: engine {g_paper:,.0f} vs "
                          f"reference {e['annual_paper_statements']:,.0f} "
                          f"({g_paper / e['annual_paper_statements'] - 1:+.1%})")
                bad = [b for b in bad if not b.startswith(("annual_avoidable_calls",
                                                           "annual_paper_statements"))]
            check(f"{label} {code} {sc} extras", not bad, "; ".join(bad))


def invariants(label: str, sizes: dict):
    sec(f"{label}: invariants")
    for code, s in sizes.items():
        if not s.has_scenarios:
            continue
        lo, ba, hi = (engine_headline(code, s.scenarios[x]) for x in ASSUME.SCENARIOS)
        check(f"{label} {code} low <= base <= high", lo <= ba <= hi,
              f"{lo:,.0f} / {ba:,.0f} / {hi:,.0f}")
        bad = [f"{sc}.{c}" for sc in ASSUME.SCENARIOS
               for c, v in s.scenarios[sc]["components"].items()
               if v.get("value_type") not in ASSUME.VALUE_TYPES or v.get("basis") not in ASSUME.BASES]
        check(f"{label} {code} every component has value_type and basis", not bad, ", ".join(bad))

    summ = LSUMMARY.portfolio_summary(sizes)
    in_total = summ["levers_in_total"]
    check(f"{label} L5 never in the portfolio total", "L5" not in in_total,
          f"levers in total: {in_total}")
    for sc in ASSUME.SCENARIOS:
        expect = sum(sizes[c].scenarios[sc]["total_usd"] for c in in_total)
        check(f"{label} portfolio {sc} total = sum of L1,L2,L3,L4,L6",
              abs(summ["scenarios"][sc]["total_usd"] - expect) < 0.01,
              f"${summ['scenarios'][sc]['total_usd']:,.0f}")
    print(f"        portfolio low/base/high: "
          + " / ".join(f"${summ['scenarios'][sc]['total_usd']:,.0f}" for sc in ASSUME.SCENARIOS))

    l6 = sizes["L6"]
    if l6.has_scenarios:
        spend = l6.scenarios["base"]["extras"]["annual_acquisition_spend_usd"]
        check(f"{label} L6 base < annual acquisition spend",
              l6.scenarios["base"]["total_usd"] < spend,
              f"${l6.scenarios['base']['total_usd']:,.0f} < ${spend:,.0f}")
    l4 = sizes["L4"]
    if l4.has_scenarios:
        cts = l4.inputs["population_trailing_12m_cost_to_serve"]
        y2 = l4.scenarios["base"]["extras"]["from_year2"]
        check(f"{label} L4 from_year2 <= population trailing-12m servicing cost",
              y2 <= cts, f"${y2:,.0f} <= ${cts:,.0f}")


def _leaf_paths(node, prefix=()):
    if isinstance(node, dict) and not any(s in node for s in ASSUME.SCENARIOS):
        for k, v in node.items():
            yield from _leaf_paths(v, prefix + (k,))
    else:
        yield prefix


def _perturb(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, dict):
        return {k: _perturb(x) for k, x in v.items()}
    return v * 1.25 + (0.01 if isinstance(v, float) else 1)


def sensitivity(label: str, sizes: dict, A: dict):
    sec(f"{label}: sensitivity - changing any configured assumption changes the output")
    for code, mod in MODULES.items():
        s = sizes[code]
        if not s.has_scenarios:
            continue
        before = mod.value_scenarios(s.inputs, A[code])
        for path in _leaf_paths(A[code]):
            a2 = copy.deepcopy(A[code])
            node = a2
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = _perturb(node[path[-1]])
            after = mod.value_scenarios(s.inputs, a2)
            changed = json.dumps(after, sort_keys=True, default=str) != \
                json.dumps(before, sort_keys=True, default=str)
            name = f"{label} {code}.{'.'.join(path)} changes the output"
            if code == "L4" and path[0] == "unit_costs":
                # By spec, unit costs are read from the cost pools (Table 11);
                # config is only the fallback when a pool is absent.
                from_pools = all(v.startswith("cost pool") for v in s.inputs["unit_cost_sources"].values())
                check(name.replace("changes the output",
                                   "is overridden by the cost pools (fallback only)"),
                      (not changed) and from_pools,
                      "unit costs come from Table 11 here, as the spec requires")
                continue
            check(name, changed)


def unit_cost_fallback():
    """The L4 unit-cost fallback really uses config when no cost pool exists."""
    import pandas as pd
    sec("L4 unit-cost fallback uses lever_assumptions.json when no cost pool exists")
    drv = pd.DataFrame({"Masked Customer Number": ["C1"], "Cycle Month": ["2025-12"],
                        "Primary Call Reason": ["billing_query"], "Contact Center Calls": [1],
                        "Paper Statements Produced": [1]})
    pop = pd.DataFrame({"Masked Customer Number": ["C1"], "cost_to_serve": [10.0]})
    empty = pd.DataFrame(columns=["Activity", "Volume Band From", "Volume Band To",
                                  "Band Fixed Cost USD Monthly", "Marginal Unit Cost USD"])
    cfg = {"call": 9.0, "digital_session": 1.0, "paper_statement": 3.0, "electronic_statement": 1.0}
    inp = l4_cost_to_serve.valuation_inputs(pop, drv, empty, cfg)
    check("L4 fallback unit costs equal config when pools are absent",
          inp["unit_costs"] == cfg, str(inp["unit_cost_sources"]))


def end_to_end_config(A: dict, base_sizes: dict):
    sec("End to end: a changed config value flows through build_pipeline()")
    a2 = copy.deepcopy(A)
    a2["L1"]["accept_share"]["base"] = 0.9
    r = build_pipeline(DEMO_DIR, LEV.DEFAULT_POLICY_NAME, lever_assumptions=a2)
    b0 = base_sizes["L1"].scenarios["base"]["total_usd"]
    b1 = r["sizes"]["L1"].scenarios["base"]["total_usd"]
    check("L1 base total changes when accept_share.base changes 0.65 -> 0.90",
          abs(b1 - b0) > 1, f"${b0:,.0f} -> ${b1:,.0f}")


def gate_across_scenarios(demo: dict):
    sec("Negative-control gate verdict is the same under low / base / high")
    ctrl = build_pipeline(CONTROL_DIR, LEV.DEFAULT_POLICY_NAME)
    for code in ("L1", "L2", "L3", "L4"):
        if not MECHANISM_VARIED_IN_CONTROL[code]:
            continue
        dl, cl = demo["levers"][code], ctrl["levers"][code]
        driver_ratio = cl.driver(ctrl["customer_view"]) / dl.driver(demo["customer_view"])
        sd, scn = demo["sizes"][code], ctrl["sizes"][code]
        verdicts = {}
        for sc in ASSUME.SCENARIOS:
            def gv(s):
                comps = s.scenarios[sc]["components"]
                keys = l2_lines.DECREASE_COMPONENTS if code == "L2" else comps.keys()
                return sum(comps[k]["value_usd"] for k in keys)
            vr = gv(scn) / gv(sd) if gv(sd) else float("nan")
            verdicts[sc] = (vr <= driver_ratio * (1 + NEGCTL.DEFAULT_SLACK), vr)
        same = len({v[0] for v in verdicts.values()}) == 1
        check(f"gate {code} verdict identical across scenarios", same,
              f"driver ratio {driver_ratio:.3f}; value ratio "
              + ", ".join(f"{sc} {v[1]:.3f}" for sc, v in verdicts.items())
              + f" -> {'PASS' if verdicts['base'][0] else 'FAIL'}")
    gr = [NEGCTL.check_defects(portfolio_defect_count(DEMO_DIR), portfolio_defect_count(CONTROL_DIR))]
    for code, lever in demo["levers"].items():
        gr.append(NEGCTL.check(lever, ctrl["levers"][code], MECHANISM_VARIED_IN_CONTROL[code],
                               demo["customer_view"], demo["populations"][code],
                               ctrl["customer_view"], ctrl["populations"][code]))
    rep = NEGCTL.report(gr)
    print(rep[["lever", "status", "driver_ratio", "value_ratio"]].to_string(index=False))
    check("gate: no tested lever FAILs", not (rep["status"] == "FAIL").any())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-100k", default=str(DEFAULT_BUNDLE_100K))
    ap.add_argument("--expected", default=str(SPEC_DIR / "expected_values.json"))
    ap.add_argument("--skip-100k", action="store_true")
    args = ap.parse_args()

    expected = json.loads(Path(args.expected).read_text())
    A, sha = ASSUME.load()
    print(f"assumptions: engine/config/lever_assumptions.json sha256 {sha}")
    print(f"expected values: {args.expected}")

    sec("Fixture 1: 5k demo, full pipeline, default leverage regime")
    demo = build_pipeline(DEMO_DIR, LEV.DEFAULT_POLICY_NAME)
    compare_fixture("5k", demo["sizes"], expected["fixture_5k_demo"])
    invariants("5k", demo["sizes"])
    sensitivity("5k", demo["sizes"], A)
    unit_cost_fallback()
    end_to_end_config(A, demo["sizes"])
    gate_across_scenarios(demo)

    if not args.skip_100k:
        sec(f"Fixture 2: 100k results bundle ({args.bundle_100k})")
        p = Path(args.bundle_100k)
        if not p.exists():
            check("100k bundle present", False, f"not found: {p}")
        else:
            r100, meta, _ = load_bundle_from_bytes(p.read_bytes(), p.name)
            print(f"  schema v{meta.schema_version} ({meta.valuation_label}), "
                  f"policy {meta.leverage_policy_name}, {meta.customers_analysed:,} customers, "
                  f"assumptions sha256 {meta.lever_assumptions_sha256}")
            check("100k bundle exported under the configured assumptions",
                  meta.lever_assumptions_sha256 == sha, str(meta.lever_assumptions_sha256))
            check("100k bundle uses leverage Case A (SLR)",
                  meta.leverage_policy_name == "case_a_slr_category_iii", meta.leverage_policy_name)
            compare_fixture("100k", r100["sizes"], expected["fixture_100k_bundle"])
            invariants("100k", r100["sizes"])
            sensitivity("100k", r100["sizes"], A)

    sec("RESULT TABLE")
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        if not ok:
            print(f"  FAIL  {name.ljust(width)}  {detail}")
    n_fail = sum(1 for _, ok, _ in results if not ok)
    groups: dict[str, list[bool]] = {}
    for name, ok, _ in results:
        key = " ".join(name.split()[:2])
        groups.setdefault(key, []).append(ok)
    for key, oks in groups.items():
        print(f"  {'PASS' if all(oks) else 'FAIL'}  {key:<40} {sum(oks)}/{len(oks)}")
    sec(f"{len(results) - n_fail}/{len(results)} CHECKS PASSED" if not n_fail
        else f"{n_fail} CHECK(S) FAILED out of {len(results)}")
    if n_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
