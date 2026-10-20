"""Export a pre-computed results bundle: run the engine locally, write a
compact zip the hosted app can load WITHOUT re-running the engine and
without uploading the (potentially multi-GB) raw portfolio.

    python -m engine.export_bundle --data <portfolio_dir> --out <bundle.zip>
    python -m engine.export_bundle --data <portfolio_dir> --compare-to <control_dir> --out <bundle.zip>

This module calls build_pipeline() (engine/run.py) exactly as the CLI and the
app already do, and the existing negative-control gate logic
(governance/negative_control.py) exactly as app/lib/pipeline_runner.py
already does. It performs NO new calculation of its own - every number in
the bundle is a number the engine already produced. See
engine/core/bundle_schema.py for the format this writes, and
ARCHITECTURE.md's "Results bundle" section for why each key is (or is not)
included.

SECURITY NOTE: this writer is a trusted, local, developer-run tool - it is
not the security boundary. The security boundary is the LOADER
(app/lib/results_bundle.py), which treats every bundle as untrusted input
regardless of where it claims to come from.
"""
from __future__ import annotations
import argparse
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.run import build_pipeline, portfolio_defect_count, MECHANISM_VARIED_IN_CONTROL  # noqa: E402
from engine.core import leverage_capital as LEV  # noqa: E402
from engine.core.contract import DataContractViolation  # noqa: E402
from engine.core import bundle_schema as SCHEMA  # noqa: E402
from engine.governance import negative_control as NEGCTL  # noqa: E402


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _detect_data_source(data_dir: Path) -> str:
    # A generator-produced portfolio always carries this directory (planted
    # defects, used for the negative-control gate) - a real bank extract
    # never would. See engine/core/contract.py:load_portfolio, which never
    # opens this directory itself.
    return "synthetic" if (data_dir / "_ground_truth").exists() else "real"


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()


def _json_bytes(obj) -> bytes:
    return json.dumps(obj, indent=2, default=str).encode("utf-8")


class _BundleWriter:
    """Accumulates (path -> bytes) entries and the manifest's per-file
    inventory (sha256, size, row count) as they are added, so the manifest
    can never drift from what actually went into the zip."""

    def __init__(self):
        self.entries: dict[str, bytes] = {}
        self.file_inventory: dict[str, dict] = {}

    def add_table(self, path: str, df: pd.DataFrame) -> None:
        data = _parquet_bytes(df)
        self.entries[path] = data
        self.file_inventory[path] = {
            "sha256": SCHEMA.sha256_bytes(data), "bytes": len(data),
            "row_count": int(len(df)),
        }

    def add_json(self, path: str, obj) -> None:
        data = _json_bytes(obj)
        self.entries[path] = data
        self.file_inventory[path] = {
            "sha256": SCHEMA.sha256_bytes(data), "bytes": len(data),
            "row_count": None,
        }

    def write_zip(self, out_path: Path, manifest: dict) -> None:
        manifest_bytes = _json_bytes(manifest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr(SCHEMA.MANIFEST_NAME, manifest_bytes)
            for path, data in self.entries.items():
                zf.writestr(path, data)


def export_bundle(data_dir: Path, out_path: Path, compare_to: Path | None = None,
                  leverage_policy_name: str = LEV.DEFAULT_POLICY_NAME,
                  portfolio_label: str | None = None,
                  data_source: str | None = None) -> dict:
    """Runs the pipeline (and, if compare_to is given, the negative-control
    gate) and writes `out_path`. Returns the manifest dict that was written,
    plus timing, for the caller to report."""
    t0 = datetime.now(timezone.utc)
    result = build_pipeline(data_dir, leverage_policy_name)
    cv = result["customer_view"]
    led = result["ledger"]["card"]
    measured = dict(result["ledger"]["measured"])

    w = _BundleWriter()
    w.add_table(SCHEMA.CUSTOMER_VIEW_TABLE,
               SCHEMA.optimize_dtypes_for_storage(cv, "customer_view"))
    w.add_table(SCHEMA.LEDGER_CARD_TABLE,
               SCHEMA.optimize_dtypes_for_storage(led, "ledger_card"))
    w.add_table(SCHEMA.ROUTING_SUMMARY_TABLE, result["routing_summary"].reset_index())
    w.add_table(SCHEMA.SUPPRESSED_TABLE, result["suppressed"].suppressed)

    for code in SCHEMA.LEVER_CODES:
        w.add_table(SCHEMA.worklist_table(code), result["worklists"][code])

    fairness = result["fairness"]
    w.add_table(SCHEMA.FAIRNESS_SCORE_TABLE, fairness["score_fairness"])
    w.add_table(SCHEMA.FAIRNESS_TREATMENT_TABLE, fairness["treatment_fairness"])
    by_tier = fairness["score_fairness_by_product_tier"]
    if by_tier is not None:
        w.add_table(SCHEMA.FAIRNESS_BY_PRODUCT_TIER_TABLE, by_tier)

    ml_fairness = result["ml_fairness"]
    if ml_fairness is not None:
        w.add_table(SCHEMA.ML_FAIRNESS_TREATMENT_TABLE, ml_fairness["treatment_fairness"])

    sizes_json = {code: {
        "priced_value_usd": s.priced_value_usd, "basis": s.basis,
        "caveat": s.caveat, "unpriced_context_usd": s.unpriced_context_usd,
    } for code, s in result["sizes"].items()}
    w.add_json(SCHEMA.SIZES_NAME, sizes_json)

    levers_json = {code: {"code": lever.code, "name": lever.name, "gates": list(lever.gates)}
                  for code, lever in result["levers"].items()}
    w.add_json(SCHEMA.LEVERS_NAME, levers_json)

    fairness_meta = {
        "proxy_method": fairness["proxy_method"],
        "score_any_failure": fairness["score_any_failure"],
        "treatment_any_failure": fairness["treatment_any_failure"],
        "score_fairness_by_product_tier_present": by_tier is not None,
    }
    if ml_fairness is not None:
        fairness_meta["ml_proxy_method"] = ml_fairness["proxy_method"]
        fairness_meta["ml_treatment_any_failure"] = ml_fairness["treatment_any_failure"]
    w.add_json(SCHEMA.FAIRNESS_META_NAME, fairness_meta)

    w.add_json(SCHEMA.ML_META_NAME, {
        "ml_available": result["ml_available"],
        "ml_policy": result["ml_policy"],
        "ml_policy_warnings": result["ml_policy_warnings"],
    })

    tx = result["portfolio"]["Table5_Transaction.csv"]
    measured[SCHEMA.TOTAL_TX_KEY] = float(tx["Transaction Amount"].sum())
    w.add_json(SCHEMA.LEDGER_MEASURED_NAME, measured)

    has_gate = False
    if compare_to is not None:
        control_result = build_pipeline(compare_to, leverage_policy_name)
        gt_demo = portfolio_defect_count(data_dir)
        gt_ctrl = portfolio_defect_count(compare_to)
        gate_results = [NEGCTL.check_defects(gt_demo, gt_ctrl)]
        for code, lever in result["levers"].items():
            gate_results.append(NEGCTL.check(
                lever, control_result["levers"][code], MECHANISM_VARIED_IN_CONTROL[code],
                result["customer_view"], result["populations"][code],
                control_result["customer_view"], control_result["populations"][code]))
        gate_report = NEGCTL.report(gate_results)
        w.add_table(SCHEMA.GATE_REPORT_TABLE, gate_report)
        has_gate = True

    headline_totals = SCHEMA.compute_headline_totals(cv, measured[SCHEMA.TOTAL_TX_KEY])

    manifest = {
        "schema_version": SCHEMA.SCHEMA_VERSION,
        "created_at_utc": t0.isoformat(),
        "engine_git_commit": _git_commit(),
        "portfolio_label": portfolio_label or data_dir.name,
        "leverage_policy_name": leverage_policy_name,
        "customers_analysed": int(len(cv)),
        "customers_protected": int(len(result["suppressed"].suppressed)),
        "cycles": int(led["Cycle Month"].nunique()),
        "data_source": data_source or _detect_data_source(data_dir),
        "ml_available": result["ml_available"],
        "has_negative_control_gate": has_gate,
        "headline_totals": headline_totals,
        "files": w.file_inventory,
    }
    w.write_zip(out_path, manifest)

    elapsed_s = (datetime.now(timezone.utc) - t0).total_seconds()
    manifest["_export_elapsed_seconds"] = elapsed_s
    manifest["_bundle_bytes"] = out_path.stat().st_size
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="portfolio directory to analyse")
    ap.add_argument("--out", required=True, help="path to write the bundle zip to")
    ap.add_argument("--compare-to", default=None,
                    help="a second portfolio (the negative control) - if given, "
                        "the gate report is computed once here and stored "
                        "finished in the bundle")
    ap.add_argument("--leverage-policy", default=LEV.DEFAULT_POLICY_NAME)
    ap.add_argument("--label", default=None,
                    help="portfolio label shown in the app's info panel "
                        "(defaults to the data directory's name)")
    ap.add_argument("--data-source", default=None, choices=["synthetic", "real"],
                    help="overrides auto-detection (a _ground_truth/ directory "
                        "present means synthetic)")
    a = ap.parse_args()
    try:
        manifest = export_bundle(
            Path(a.data), Path(a.out),
            Path(a.compare_to) if a.compare_to else None,
            a.leverage_policy, a.label, a.data_source)
    except DataContractViolation as e:
        print(f"DATA CONTRACT VIOLATION - refusing to export: {e}")
        raise SystemExit(1)

    print(f"Wrote {a.out}")
    print(f"  {manifest['customers_analysed']:,} customers analysed, "
         f"{manifest['customers_protected']:,} protected, "
         f"{manifest['cycles']} cycles")
    print(f"  bundle size: {manifest['_bundle_bytes'] / 1e6:.1f} MB")
    print(f"  export time: {manifest['_export_elapsed_seconds']:.1f}s")
    print(f"  negative-control gate included: {manifest['has_negative_control_gate']}")
