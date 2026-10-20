"""Shared schema/constants for the pre-computed results bundle (see
engine/export_bundle.py for the writer and app/lib/results_bundle.py for the
reader). Kept dependency-free of Streamlit and of any engine calculation
module, on purpose: both the export CLI and the hosted app import this file,
and it must never grow a reason for one side to drift from the other.

A bundle is a zip containing:
  manifest.json              schema version, provenance, file inventory
                              (sha256 + row count per file), headline totals
  tables/*.parquet           every DataFrame a page needs, typed and columnar
  sizes.json                 one dict per lever: the SizeResult fields
  levers.json                one dict per lever: code, name, gates (a plain
                              list[str]) - never a live Lever object
  fairness.json               the non-tabular companion fields for `fairness`
                              and (if present) `ml_fairness`
  ml.json                     ml_available, ml_policy, ml_policy_warnings
  ledger_measured.json       the ledger's measured-quantity dict, plus one
                              extra app-only scalar (see TOTAL_TX_KEY)

Deliberately NOT in the bundle (see ARCHITECTURE.md "Results bundle" section
for the reasoning): raw portfolio tables (Table2/5/11/12 etc.), `populations`,
`routed`, `leverage_policy`/`leverage_warnings`/`leverage_audit` (no page
reads these - confirmed by a full grep of app/, see STATUS.md), and live
Lever objects.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass

SCHEMA_VERSION = 1

# Generous headroom over the <200MB/50k target - a hosted 2GB instance can
# comfortably stage several times that during unzip + parquet decode, but an
# unbounded size defeats the point of validating before loading.
MAX_UNCOMPRESSED_BYTES = 750 * 1024 * 1024

# Headline-total reconciliation tolerance: $1 absolute, or 1 part per
# million of the expected value, whichever is larger - the same style of
# tolerance engine/core/ledger.py's own _reconcile() uses.
def reconcile_tolerance(expected: float) -> float:
    return max(1.0, abs(expected) * 1e-6)


LEVER_CODES = ["L1", "L2", "L3", "L4", "L5", "L6"]

# The one extra scalar the app needs that isn't a native key of
# engine.core.ledger.build()'s `measured` dict - see 10_Portfolio_Economics.py's
# "effective interchange rate" metric, whose denominator is otherwise the raw
# Table5_Transaction.csv, which a bundle deliberately excludes.
TOTAL_TX_KEY = "total_transaction_amount_usd"

MANIFEST_NAME = "manifest.json"
SIZES_NAME = "sizes.json"
LEVERS_NAME = "levers.json"
FAIRNESS_META_NAME = "fairness.json"
ML_META_NAME = "ml.json"
LEDGER_MEASURED_NAME = "ledger_measured.json"

TABLES_DIR = "tables"
CUSTOMER_VIEW_TABLE = f"{TABLES_DIR}/customer_view.parquet"
LEDGER_CARD_TABLE = f"{TABLES_DIR}/ledger_card.parquet"
ROUTING_SUMMARY_TABLE = f"{TABLES_DIR}/routing_summary.parquet"
SUPPRESSED_TABLE = f"{TABLES_DIR}/suppressed.parquet"
FAIRNESS_SCORE_TABLE = f"{TABLES_DIR}/fairness_score.parquet"
FAIRNESS_TREATMENT_TABLE = f"{TABLES_DIR}/fairness_treatment.parquet"
FAIRNESS_BY_PRODUCT_TIER_TABLE = f"{TABLES_DIR}/fairness_score_by_product_tier.parquet"
ML_FAIRNESS_TREATMENT_TABLE = f"{TABLES_DIR}/ml_fairness_treatment.parquet"
GATE_REPORT_TABLE = f"{TABLES_DIR}/gate_report.parquet"


def worklist_table(code: str) -> str:
    return f"{TABLES_DIR}/worklist_{code}.parquet"


class BundleValidationError(Exception):
    """Raised when a bundle fails any check in the load-time validation
    contract (manifest/schema, file presence, hash, row count, path
    traversal, size cap, or headline-total reconciliation). Always carries a
    human-readable message meant to be shown to the person who tried to load
    the bundle, never a raw traceback."""


class BundleTableUnavailable(KeyError):
    """Raised when a page asks a bundle-backed result for a raw portfolio
    table the bundle does not carry (e.g. Table5_Transaction.csv). A page
    must catch this and show a clear message - never let it surface as an
    unhandled exception."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class LeverStub:
    """Stand-in for a live engine.levers.base.Lever instance. A grep of every
    app page (see STATUS.md) confirms the ONLY attribute any page reads off a
    lever is `.gates` (a plain list[str], a class attribute) -
    20_Levers_and_Strategy.py:164-166. Nothing else - not `.driver()`,
    `.size()`, or `.population()` - is ever called on `result["levers"][code]`
    outside the negative-control gate, which a bundle stores pre-computed
    instead of recomputing. This stub carries only what is actually read."""
    code: str
    name: str
    gates: list


def compute_headline_totals(customer_view, total_transaction_amount_usd: float | None) -> dict:
    """The reconciliation totals stored in manifest.json and recomputed from
    the loaded tables on every bundle load (see results_bundle.py:validate).
    Mirrors exactly the arithmetic app/Home.py already displays."""
    is_below_cost = customer_view["is_below_cost"]
    return {
        "portfolio_nep_usd": float(customer_view["trailing_12m_net_economic_profit"].sum()),
        "below_cost_count": int(is_below_cost.sum()),
        "total_loss_usd": float(
            -customer_view.loc[is_below_cost, "trailing_12m_net_economic_profit"].sum()),
        "total_transaction_amount_usd": total_transaction_amount_usd,
    }
