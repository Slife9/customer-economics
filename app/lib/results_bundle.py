"""Load a pre-computed results bundle (see engine/export_bundle.py for the
writer, engine/core/bundle_schema.py for the format) into a `result` dict the
existing pages can use with no changes to their reading of `result[...]`,
except where a page explicitly needs a raw portfolio table the bundle does
not carry (see BundleTableUnavailable usages in 10_Portfolio_Economics.py and
20_Levers_and_Strategy.py).

SECURITY: a bundle is UNTRUSTED input - it may have been produced on another
machine, or tampered with in transit. This module:
  - never calls pickle/joblib or anything that executes code on load - every
    table is read as Parquet (data only, via pyarrow) and every object is
    read as JSON;
  - validates the manifest, every file's presence/hash/row-count, and
    rejects any zip entry outside the bundle root, before trusting anything
    in it;
  - enforces a maximum uncompressed size;
  - recomputes headline totals from the loaded tables and compares them to
    the manifest's claimed totals within an explicit tolerance.
Any failure raises BundleValidationError with a message meant to be shown
directly to the person who tried to load the bundle - never a raw traceback.
"""
from __future__ import annotations
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.core import bundle_schema as SCHEMA  # noqa: E402
from engine.core.bundle_schema import BundleValidationError, BundleTableUnavailable  # noqa: E402,F401
from engine.core.suppression import SuppressedPopulation  # noqa: E402
from engine.levers.base import SizeResult  # noqa: E402

__all__ = ["BundleValidationError", "BundleTableUnavailable", "BundleMetadata",
          "load_bundle_from_bytes"]


@dataclass
class BundleMetadata:
    """Everything the sidebar / portfolio-info panel shows about a loaded
    bundle. Mirrors the manifest's own fields (minus the file inventory)."""
    schema_version: int
    created_at_utc: str
    engine_git_commit: str | None
    portfolio_label: str
    leverage_policy_name: str
    customers_analysed: int
    customers_protected: int
    cycles: int
    data_source: str
    ml_available: bool
    has_negative_control_gate: bool
    bundle_file_name: str
    bundle_size_bytes: int


class BundlePortfolioStub:
    """Stand-in for engine.core.contract.Portfolio. A bundle never carries
    raw portfolio tables (see bundle_schema.py's module docstring), so every
    lookup raises BundleTableUnavailable with a message a page can catch and
    turn into an st.info(...) - never a raw KeyError/traceback."""

    def __init__(self, label: str):
        self.root = Path(f"<pre-computed bundle: {label}>")
        self.tables: dict[str, pd.DataFrame] = {}

    def __getitem__(self, name: str) -> pd.DataFrame:
        raise BundleTableUnavailable(
            f"'{name}' is not included in this pre-computed results bundle. "
            f"Raw portfolio tables are left out to keep bundles small enough "
            f"to host - re-run the engine on the full portfolio to see this.")

    def get(self, name: str, default=None):
        return default


def _validate_entry_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        raise BundleValidationError(f"refusing to load bundle: unsafe entry path {name!r}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts or any(p == "" for p in parts[1:]):
        raise BundleValidationError(f"refusing to load bundle: unsafe entry path {name!r}")


def _read_json(zf: zipfile.ZipFile, path: str) -> Any:
    return json.loads(zf.read(path).decode("utf-8"))


def _read_table(zf: zipfile.ZipFile, path: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(zf.read(path)), engine="pyarrow")


def _validate(zf: zipfile.ZipFile, manifest: dict) -> None:
    if "schema_version" not in manifest or "files" not in manifest:
        raise BundleValidationError(
            "manifest.json is missing required fields - this does not look "
            "like a ProfitInsight results bundle.")
    if manifest["schema_version"] != SCHEMA.SCHEMA_VERSION:
        raise BundleValidationError(
            f"unsupported bundle schema version {manifest['schema_version']} "
            f"(this app supports version {SCHEMA.SCHEMA_VERSION}). Re-export "
            f"the bundle with a matching engine version.")

    infos = zf.infolist()
    names_on_disk = set()
    total_uncompressed = 0
    for info in infos:
        _validate_entry_name(info.filename)
        names_on_disk.add(info.filename)
        total_uncompressed += info.file_size
    if total_uncompressed > SCHEMA.MAX_UNCOMPRESSED_BYTES:
        raise BundleValidationError(
            f"bundle is too large uncompressed "
            f"({total_uncompressed / 1e6:,.0f} MB > "
            f"{SCHEMA.MAX_UNCOMPRESSED_BYTES / 1e6:,.0f} MB limit) - refusing to load.")

    expected_names = set(manifest["files"].keys()) | {SCHEMA.MANIFEST_NAME}
    unexpected = names_on_disk - expected_names
    if unexpected:
        raise BundleValidationError(
            f"bundle contains {len(unexpected)} file(s) not listed in its own "
            f"manifest (e.g. {sorted(unexpected)[0]!r}) - refusing to load.")
    missing = expected_names - names_on_disk
    if missing:
        raise BundleValidationError(
            f"bundle is missing {len(missing)} file(s) its own manifest lists "
            f"(e.g. {sorted(missing)[0]!r}) - refusing to load a truncated bundle.")

    for path, meta in manifest["files"].items():
        data = zf.read(path)
        actual_sha256 = SCHEMA.sha256_bytes(data)
        if actual_sha256 != meta.get("sha256"):
            raise BundleValidationError(
                f"checksum mismatch for {path!r} - the bundle may be corrupted "
                f"or tampered with. Refusing to load.")
        if meta.get("row_count") is not None and path.endswith(".parquet"):
            actual_rows = len(pd.read_parquet(io.BytesIO(data), engine="pyarrow"))
            if actual_rows != meta["row_count"]:
                raise BundleValidationError(
                    f"row count mismatch for {path!r}: manifest says "
                    f"{meta['row_count']:,}, file has {actual_rows:,}. "
                    f"Refusing to load.")


def _reconcile(manifest: dict, customer_view: pd.DataFrame) -> None:
    claimed = manifest.get("headline_totals", {})
    recomputed = SCHEMA.compute_headline_totals(
        customer_view, claimed.get("total_transaction_amount_usd"))
    for key in ("portfolio_nep_usd", "total_loss_usd"):
        expected = claimed.get(key)
        if expected is None:
            continue
        actual = recomputed[key]
        tol = SCHEMA.reconcile_tolerance(expected)
        if abs(actual - expected) > tol:
            raise BundleValidationError(
                f"reconciliation failure: manifest claims {key}=${expected:,.2f}, "
                f"the loaded tables sum to ${actual:,.2f} (tolerance "
                f"${tol:,.2f}). Refusing to load a bundle whose own numbers "
                f"don't add up.")
    if claimed.get("below_cost_count") is not None:
        if recomputed["below_cost_count"] != claimed["below_cost_count"]:
            raise BundleValidationError(
                f"reconciliation failure: manifest claims "
                f"{claimed['below_cost_count']:,} below-cost customers, the "
                f"loaded table has {recomputed['below_cost_count']:,}. "
                f"Refusing to load.")


def load_bundle_from_bytes(data: bytes, file_name: str
                           ) -> tuple[dict, BundleMetadata, pd.DataFrame | None]:
    """Validates and loads a bundle. Returns (result, metadata, gate_report).

    `result` has the same keys/attribute surface every page already reads
    from a live-engine result (see ARCHITECTURE.md's "Results bundle"
    section for the few documented exceptions). `gate_report` is the
    negative-control gate DataFrame if the bundle was exported with
    --compare-to, else None - callers should put it in
    st.session_state["gate_report"] exactly like a live sample-portfolio run
    does, never inside `result` itself (that is also where the live app
    keeps it)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BundleValidationError(
            f"{file_name!r} is not a valid zip file - refusing to load.")

    if SCHEMA.MANIFEST_NAME not in zf.namelist():
        raise BundleValidationError(
            f"{file_name!r} has no manifest.json - this does not look like a "
            f"ProfitInsight results bundle.")
    manifest = _read_json(zf, SCHEMA.MANIFEST_NAME)
    _validate(zf, manifest)

    cv = _read_table(zf, SCHEMA.CUSTOMER_VIEW_TABLE)
    _reconcile(manifest, cv)

    ledger_card = _read_table(zf, SCHEMA.LEDGER_CARD_TABLE)
    suppressed_df = _read_table(zf, SCHEMA.SUPPRESSED_TABLE)
    routing_summary = _read_table(zf, SCHEMA.ROUTING_SUMMARY_TABLE).set_index("routed_lever")

    # Reconstructed via the REAL SuppressedPopulation constructor (not
    # pickled, not duck-typed) - safe because it's just calling a known
    # type-checked constructor on data that already passed validation above.
    # `routed.frame` and `customer_view` stay the same object, matching the
    # live engine's own invariant (build_pipeline returns `routed.frame` as
    # `customer_view`).
    routed = SuppressedPopulation(cv, suppressed_df)
    customer_view = routed.frame
    suppressed = SuppressedPopulation(customer_view, suppressed_df)

    worklists = {code: _read_table(zf, SCHEMA.worklist_table(code))
                for code in SCHEMA.LEVER_CODES}

    sizes_json = _read_json(zf, SCHEMA.SIZES_NAME)
    sizes = {code: SizeResult(**d) for code, d in sizes_json.items()}

    levers_json = _read_json(zf, SCHEMA.LEVERS_NAME)
    levers = {code: SCHEMA.LeverStub(**d) for code, d in levers_json.items()}

    fairness_meta = _read_json(zf, SCHEMA.FAIRNESS_META_NAME)
    by_tier = (_read_table(zf, SCHEMA.FAIRNESS_BY_PRODUCT_TIER_TABLE)
              if fairness_meta.get("score_fairness_by_product_tier_present") else None)
    fairness = {
        "proxy_method": fairness_meta["proxy_method"],
        "score_fairness": _read_table(zf, SCHEMA.FAIRNESS_SCORE_TABLE),
        "treatment_fairness": _read_table(zf, SCHEMA.FAIRNESS_TREATMENT_TABLE),
        "score_fairness_by_product_tier": by_tier,
        "score_any_failure": fairness_meta["score_any_failure"],
        "treatment_any_failure": fairness_meta["treatment_any_failure"],
    }

    ml_meta = _read_json(zf, SCHEMA.ML_META_NAME)
    ml_fairness = None
    if "ml_proxy_method" in fairness_meta:
        # Only `proxy_method`, `treatment_fairness` and `treatment_any_failure`
        # are ever read by a page (25_ML_Credit_Limit.py) - `score_fairness`
        # is numerically identical to the non-ML score_fairness above (both
        # score every customer by cev_band, independent of any worklist) and
        # is not carried twice; see STATUS.md's documented limitations.
        ml_fairness = {
            "proxy_method": fairness_meta["ml_proxy_method"],
            "score_fairness": None,
            "treatment_fairness": _read_table(zf, SCHEMA.ML_FAIRNESS_TREATMENT_TABLE),
            "score_fairness_by_product_tier": None,
            "score_any_failure": None,
            "treatment_any_failure": fairness_meta["ml_treatment_any_failure"],
        }

    ledger_measured = _read_json(zf, SCHEMA.LEDGER_MEASURED_NAME)

    gate_report = (_read_table(zf, SCHEMA.GATE_REPORT_TABLE)
                  if manifest.get("has_negative_control_gate") else None)

    portfolio = BundlePortfolioStub(manifest.get("portfolio_label", file_name))

    result = {
        "portfolio": portfolio,
        "ledger": {
            "card": ledger_card,
            "deposit_by_customer": pd.DataFrame(
                columns=["Masked Customer Number", "Cycle Month", "deposit_net"]),
            "loan_by_customer": pd.DataFrame(
                columns=["Masked Customer Number", "Cycle Month", "loan_net"]),
            "measured": ledger_measured,
        },
        "customer_view": customer_view,
        "suppressed": suppressed,
        "routed": routed,
        "levers": levers,
        "populations": {},
        "sizes": sizes,
        "worklists": worklists,
        "fairness": fairness,
        "routing_summary": routing_summary,
        "leverage_policy": {},
        "leverage_policy_path": f"<pre-computed bundle: policy "
                                f"'{manifest.get('leverage_policy_name')}' was "
                                f"used at export time>",
        "leverage_warnings": [],
        "leverage_audit": {},
        "ml_available": ml_meta["ml_available"],
        "ml_policy": ml_meta["ml_policy"],
        "ml_policy_warnings": ml_meta["ml_policy_warnings"],
        "ml_fairness": ml_fairness,
    }

    metadata = BundleMetadata(
        schema_version=manifest["schema_version"],
        created_at_utc=manifest.get("created_at_utc", "unknown"),
        engine_git_commit=manifest.get("engine_git_commit"),
        portfolio_label=manifest.get("portfolio_label", file_name),
        leverage_policy_name=manifest.get("leverage_policy_name", "unknown"),
        customers_analysed=manifest.get("customers_analysed", len(customer_view)),
        customers_protected=manifest.get("customers_protected", len(suppressed_df)),
        cycles=manifest.get("cycles", 0),
        data_source=manifest.get("data_source", "unknown"),
        ml_available=ml_meta["ml_available"],
        has_negative_control_gate=manifest.get("has_negative_control_gate", False),
        bundle_file_name=file_name,
        bundle_size_bytes=len(data),
    )

    return result, metadata, gate_report
