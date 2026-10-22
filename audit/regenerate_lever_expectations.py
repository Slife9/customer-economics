"""Regenerate the lever acceptance expectations after the Stage A5 population
fixes (L3 first-year exclusion for routed accounts; L5 closure-request signal
limited to the trailing 12 cycles), and document the deltas.

The expectations are computed by the spec's REFERENCE implementation
(specs/lever_valuation_rebuild/reference_lever_estimates.py), not by the
engine - so audit/audit_lever_estimates.py keeps comparing the engine with
an independent calculation, exactly as it did against the reviewer's
original expected_values.json.

    python audit/regenerate_lever_expectations.py --bundle-100k <v2 bundle zip>

Writes:
    specs/lever_valuation_rebuild/expected_values_after_population_fixes.json
    specs/lever_valuation_rebuild/POPULATION_FIX_DELTAS.md
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.run import build_pipeline  # noqa: E402
from engine.core import leverage_capital as LEV  # noqa: E402
from app.lib.results_bundle import load_bundle_from_bytes  # noqa: E402

SPEC_DIR = ROOT / "specs" / "lever_valuation_rebuild"
OUT_JSON = SPEC_DIR / "expected_values_after_population_fixes.json"
OUT_MD = SPEC_DIR / "POPULATION_FIX_DELTAS.md"


def _reference():
    spec = importlib.util.spec_from_file_location("reference_lever_estimates",
                                                  SPEC_DIR / "reference_lever_estimates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _to_expected(est: dict) -> dict:
    """The reference's raw output, rounded and shaped like expected_values.json."""
    out = {}
    for code, scen in est.items():
        out[code] = {}
        for s, v in scen.items():
            row = {"components": {k: round(float(x), 2) for k, x in v["components"].items()}}
            for k, x in v.items():
                if k == "components":
                    continue
                if isinstance(x, str):
                    row[k] = x
                elif k in ("breakeven_keep_rate", "breakeven_quality"):
                    row[k] = round(float(x), 2)
                else:
                    row[k] = round(float(x), 2)
            out[code][s] = row
    return out


def _headline(code, row):
    return row["net_conditional"] if code == "L5" else row["total"]


def _delta_table(name, before, after, counts_before, counts_after):
    lines = [f"### {name}", "",
             "| Lever | Worklist before | Worklist after | Base before | Base after | Change |",
             "|---|---:|---:|---:|---:|---:|"]
    for code in ("L1", "L2", "L3", "L4", "L5", "L6"):
        b, a = _headline(code, before[code]["base"]), _headline(code, after[code]["base"])
        ch = "no change" if abs(a - b) < 0.005 else f"{a - b:+,.2f}"
        lines.append(f"| {code} | {counts_before.get(code, 'n/a')} | {counts_after[code]} | "
                     f"{b:,.2f} | {a:,.2f} | {ch} |")
    extra = []
    for code, keys in (("L3", ("flagged", "targeted")), ("L5", ("customers", "value_at_risk",
                                                               "breakeven_keep_rate"))):
        for k in keys:
            bv, av = before[code]["base"].get(k), after[code]["base"].get(k)
            if bv != av:
                extra.append(f"- {code} `{k}`: {bv} -> {av}")
    if extra:
        lines += ["", *extra]
    return lines + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-100k", default=str(Path(os.environ.get("TEMP", "/tmp"))
                                                 / "bundle_100k_v2.zip"))
    ap.add_argument("--bundle-100k-before", default=None,
                    help="a bundle exported before the population fixes (e.g. the original "
                         "schema-v1 100k bundle) - used only for the 'worklist before' counts")
    ap.add_argument("--before-counts-5k", default=None,
                    help='JSON of pre-fix 5k worklist counts, e.g. {"L3": 179, "L5": 470}')
    args = ap.parse_args()
    ref = _reference()
    A = json.loads((ROOT / "engine" / "config" / "lever_assumptions.json").read_text())
    original = json.loads((SPEC_DIR / "expected_values.json").read_text())

    demo = build_pipeline(ROOT / "generator" / "out" / "demo", LEV.DEFAULT_POLICY_NAME)
    est5 = ref.estimate_all(demo["customer_view"], demo["worklists"], demo["n_cycles"], A)
    counts5 = {k: len(v) for k, v in demo["worklists"].items()}

    p = Path(args.bundle_100k)
    r100, meta, _ = load_bundle_from_bytes(p.read_bytes(), p.name)
    est100 = ref.estimate_all(r100["customer_view"], r100["worklists"], meta.cycles, A)
    counts100 = {k: len(v) for k, v in r100["worklists"].items()}

    new = {"fixture_100k_bundle": _to_expected(est100), "fixture_5k_demo": _to_expected(est5),
           "_provenance": {
               "computed_by": "specs/lever_valuation_rebuild/reference_lever_estimates.py",
               "on": "post-population-fix pipeline outputs (Stage A5)",
               "fixture_5k_demo": "generator/out/demo, full pipeline, default leverage regime",
               "fixture_100k_bundle": f"{p.name}, schema v{meta.schema_version}, "
                                      f"{meta.leverage_policy_name}"}}
    OUT_JSON.write_text(json.dumps(new, indent=1))

    md = ["# Population fixes: effect on lever counts and values (Stage A5)", "",
          "Two population fixes from the spec, applied as a separate stage:", "",
          "1. **L3** - accounts with tenure under 12 months are excluded even when added",
          "   via `routed_lever == \"L3\"` (CARD Act first-year protection applies to every",
          "   candidate).",
          "2. **L5** - the closure-request signal uses the trailing 12 cycles only, not any",
          "   closure-request contact in the full history.", "",
          "Expectations regenerated with the spec's reference implementation on the",
          "post-fix pipeline outputs (`audit/regenerate_lever_expectations.py`). 'Before' is",
          "the reviewer's original `expected_values.json`.", ""]
    before5 = json.loads(args.before_counts_5k) if args.before_counts_5k else {}
    before100 = {}
    if args.bundle_100k_before:
        pb = Path(args.bundle_100k_before)
        rb, _, _ = load_bundle_from_bytes(pb.read_bytes(), pb.name)
        before100 = {k: len(v) for k, v in rb["worklists"].items()}
    md += _delta_table("5k demo (Tier 1 regime)", original["fixture_5k_demo"],
                       new["fixture_5k_demo"], before5, counts5)
    md += _delta_table("100k bundle (Case A, SLR)", original["fixture_100k_bundle"],
                       new["fixture_100k_bundle"], before100, counts100)
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"wrote {OUT_JSON}\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
