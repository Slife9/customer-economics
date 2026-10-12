"""Verification script for the ML credit-limit model and decision engine.
Run as a script, like the other files in this directory - there is no
pytest suite in this repo to join.

    python audit/audit_ml_credit_limit.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.contract import load_portfolio  # noqa: E402
from engine.core import ledger as LEDGER  # noqa: E402
from engine.core import customer_view as CV  # noqa: E402
from engine.ml import features as F  # noqa: E402
from engine.ml import score as SCORE  # noqa: E402
from engine.ml import decisions as DEC  # noqa: E402

DEMO_DIR = ROOT / "generator" / "out" / "demo"


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


sec("Load bundle and demo portfolio")
bundle = SCORE.load_bundle()
portfolio = load_portfolio(DEMO_DIR)
led = LEDGER.build(portfolio)
cv = CV.build(led, portfolio)
print(f"  loaded bundle trained_at={bundle.get('trained_at_utc', '?')}")

sec("T-ID: Identifiers never reached the trained feature list")
assert F.CUSTOMER_ID not in F.MODEL_FEATURES
assert F.ACCOUNT_ID not in F.MODEL_FEATURES
assert "Age" not in F.MODEL_FEATURES, "Age is an ECOA/Reg B prohibited basis - must never be a feature"
assert "Charged Purchase APR" not in F.MODEL_FEATURES, \
    "Charged Purchase APR may proxy the generator's own L3 repricing mechanism"
for key in ("risk", "spend", "peak_balance"):
    trained_features = bundle[key]["features"]
    assert F.CUSTOMER_ID not in trained_features
    assert F.ACCOUNT_ID not in trained_features
    assert "Age" not in trained_features
    assert "Charged Purchase APR" not in trained_features
print("  PASS  no identifiers, Age, or Charged Purchase APR in any trained feature list")

sec("T-PANEL: Panel builder produces a leakage-safe grid")
panel = F.build_training_panel(portfolio)
assert (panel.groupby(F.ACCOUNT_ID)[F.CYCLE_IDX].apply(lambda s: s.is_monotonic_increasing)).all(), \
    "panel rows must be in Cycle Index order within each account"
labeled = panel[panel["target_complete"]]
max_idx_per_account = panel.groupby(F.ACCOUNT_ID)[F.CYCLE_IDX].transform("max")
assert (labeled[F.CYCLE_IDX] <= max_idx_per_account[panel["target_complete"]] - 3).all(), \
    "a labeled row must have at least 3 strictly later cycles available"
print(f"  PASS  {len(labeled):,} of {len(panel):,} rows have a complete 3-cycle-forward label, "
     f"none within 3 cycles of their account's last observed row")

sec("T-ELIGIBLE: Training eligibility excludes already-delinquent rows")
eligible = panel[panel["model_training_eligible"]]
assert (eligible["_latest_days_past_due"] < 30).all(), \
    "model_training_eligible must exclude rows already 30+ DPD (learn who BECOMES delinquent, not who IS)"
print(f"  PASS  all {len(eligible):,} training-eligible rows have Days Past Due < 30 as of the as-of cycle")

sec("T-SCORE: Scoring frame is latest-cycle-only, one row per account")
sf = F.build_scoring_frame(portfolio)
assert sf[F.ACCOUNT_ID].is_unique, "scoring frame must have exactly one row per account"
print(f"  PASS  {len(sf):,} accounts, {len(sf):,} rows")

sec("T-DECIDE: Decision engine produces valid actions and non-negative money figures")
scored = SCORE.score(portfolio, bundle)
policy, warnings = DEC.load_policy()
if warnings:
    print("  policy warnings:", warnings)
result = DEC.decide(scored, cv, policy)

valid_actions = {"INCREASE", "MAINTAIN", "DECREASE_UNUSED_EXPOSURE", "FREEZE_NO_INCREASE",
                 "MANUAL_REVIEW", "NOT_ELIGIBLE", "INSUFFICIENT_HISTORY"}
assert set(result["ml_action"].unique()).issubset(valid_actions)
print(f"  PASS  all actions in {sorted(valid_actions)}")

money_cols = ["ml_expected_3m_interchange_proxy", "ml_expected_loss_proxy",
             "ml_released_capacity_value_proxy_3m"]
for c in money_cols:
    assert (result[c].fillna(0) >= 0).all(), f"{c} must never be negative"
print("  PASS  interchange / expected loss / released capacity are all non-negative")

decreases = result[result["ml_action"] == "DECREASE_UNUSED_EXPOSURE"]
assert (decreases["ml_recommended_limit"] < decreases["current_limit"]).all()
increases = result[result["ml_action"] == "INCREASE"]
assert (increases["ml_recommended_limit"] > increases["current_limit"]).all()
print(f"  PASS  every DECREASE ({len(decreases)}) actually lowers the limit, "
     f"every INCREASE ({len(increases)}) actually raises it")

max_reductions = max(1, int(len(result) * policy["maximum_reduction_share_per_review"]))
assert (result["ml_action"] == "DECREASE_UNUSED_EXPOSURE").sum() <= max_reductions, \
    "the portfolio pilot cap must never be exceeded"
print(f"  PASS  {int((result['ml_action'] == 'DECREASE_UNUSED_EXPOSURE').sum())} reductions "
     f"<= pilot cap of {max_reductions}")

sec("T-SUPPRESS: decide() does not self-suppress; exclude_suppressed() does")
from engine.core import suppression as SUPP  # noqa: E402
suppressed_pop = SUPP.run(cv)
suppressed_ids = set(suppressed_pop.suppressed["Masked Customer Number"])
overlap_before = set(result["Masked Customer Number"]) & suppressed_ids
# decide() itself has no suppression concept by design (module docstring) -
# a suppressed customer legitimately appears in its raw output, exactly
# like every other pre-suppression computation in this engine. The real
# safety property lives in exclude_suppressed(), tested next.
print(f"  INFO  {len(overlap_before)} suppressed customers present in decide()'s raw output "
     f"(expected - this module filters nothing by design)")

filtered = DEC.exclude_suppressed(result, suppressed_ids)
overlap_after = set(filtered["Masked Customer Number"]) & suppressed_ids
assert not overlap_after, "exclude_suppressed() must remove every suppressed customer"
assert len(filtered) == len(result) - len(overlap_before), \
    "exclude_suppressed() must remove exactly the suppressed customers, nothing else"
print(f"  PASS  exclude_suppressed() removes all {len(overlap_before)} suppressed customers "
     f"and nothing else. The live app doesn't need to call it directly - engine/run.py merges "
     f"ml_* columns into `cv` BEFORE suppression.run(cv), so result['customer_view'] is already "
     f"suppression-safe by the time the page reads it, same as every other page. This helper is "
     f"for the one case that bypasses that ordering: calling decide() directly, as this script "
     f"just did.")

sec("ALL CHECKS PASSED")
