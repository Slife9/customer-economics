"""Verification script for engine/core/leverage_capital.py against the
worked examples in SPEC_leverage_capital_cost_v2.md section 4.3 (tests
T-01, T-02, T-03, T-08, T-09, T-13). Run as a script, like the other files
in this directory - there is no pytest suite in this repo to join, so this
follows the existing print-based, assert-driven diagnostic convention
(see audit_causal_integrity.py / audit_fees_and_control.py).

    python audit/audit_leverage_capital.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core import leverage_capital as LEV  # noqa: E402


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def _cv(undrawn: float) -> pd.DataFrame:
    return pd.DataFrame({"Masked Customer Number": ["CUS0000000"],
                         "avg_undrawn_12m": [undrawn]})


def _base_policy(slr_mode: bool, ccf_override: float | None = None) -> dict:
    policy, _, _ = LEV.load_policy(
        "case_a_slr_category_iii" if slr_mode else "case_b_tier1_regional")
    if ccf_override is not None:
        policy["slr_ccf_by_commitment_type"] = dict(policy["slr_ccf_by_commitment_type"])
        policy["product_commitment_type"] = {"credit_card": "NON_UCC_ORIGINAL_MATURITY_LE_1Y"}
        policy["slr_ccf_by_commitment_type"]["NON_UCC_ORIGINAL_MATURITY_LE_1Y"] = ccf_override
    return policy


sec("T-01: Case A worked example (limit 10,000, balance 2,000 -> undrawn 8,000)")
cv = _cv(8000.0)
policy = _base_policy(slr_mode=True)
out = LEV.compute(cv, policy)
row = out.iloc[0]
assert row["leverage_exposure"] == 800.0, row["leverage_exposure"]
assert abs(row["leverage_capital_held"] - 32.00) < 1e-9, row["leverage_capital_held"]
assert abs(row["leverage_capital_cost"] - 3.84) < 1e-9, row["leverage_capital_cost"]
assert row["leverage_status"] == "SLR_CHARGED"
print(f"  PASS  exposure={row['leverage_exposure']:.2f} capital={row['leverage_capital_held']:.2f} "
     f"cost={row['leverage_capital_cost']:.2f}")

sec("T-02: Case B worked example (same account, Tier 1 regime)")
policy_b = _base_policy(slr_mode=False)
out_b = LEV.compute(cv, policy_b)
row_b = out_b.iloc[0]
assert row_b["leverage_exposure"] == 0.0
assert row_b["leverage_capital_held"] == 0.0
assert row_b["leverage_capital_cost"] == 0.0
assert row_b["leverage_status"] == "TIER1_REGIME_NOT_CHARGED"
print(f"  PASS  all zero, status={row_b['leverage_status']}")

sec("T-03: Non-UCC <=1y commitment in SLR mode (same amounts, 20% CCF)")
policy_nonucc = _base_policy(slr_mode=True, ccf_override=0.20)
out_nonucc = LEV.compute(cv, policy_nonucc)
row_nonucc = out_nonucc.iloc[0]
assert row_nonucc["leverage_exposure"] == 1600.0, row_nonucc["leverage_exposure"]
assert abs(row_nonucc["leverage_capital_held"] - 64.00) < 1e-9, row_nonucc["leverage_capital_held"]
assert abs(row_nonucc["leverage_capital_cost"] - 7.68) < 1e-9, row_nonucc["leverage_capital_cost"]
print(f"  PASS  exposure={row_nonucc['leverage_exposure']:.2f} "
     f"capital={row_nonucc['leverage_capital_held']:.2f} cost={row_nonucc['leverage_capital_cost']:.2f}")

sec("T-08: Tier 1 mode charges nothing across a multi-row portfolio")
cv_multi = pd.DataFrame({
    "Masked Customer Number": ["A", "B", "C"],
    "avg_undrawn_12m": [1000.0, 50000.0, 0.0],
})
out_multi = LEV.compute(cv_multi, policy_b)
assert out_multi["leverage_capital_cost"].sum() == 0.0
print(f"  PASS  sum(leverage_capital_cost) = {out_multi['leverage_capital_cost'].sum():.2f}")

sec("T-09: Edge cases - zero and negative undrawn (over-limit) never produce negative exposure")
cv_edge = pd.DataFrame({
    "Masked Customer Number": ["OVERLIMIT", "ZERO"],
    "avg_undrawn_12m": [-500.0, 0.0],
})
out_edge = LEV.compute(cv_edge, policy)
assert (out_edge["leverage_exposure"] >= 0).all()
assert out_edge.loc[out_edge["Masked Customer Number"] == "OVERLIMIT", "leverage_exposure"].iloc[0] == 0.0
print("  PASS  over-limit and zero-undrawn rows both floor at $0 exposure")

sec("T-13: Non-negativity across all leverage fields")
assert (out[["leverage_exposure", "leverage_capital_held", "leverage_capital_cost",
            "shadow_leverage_capital_cost"]] >= 0).all().all()
print("  PASS  no negative leverage fields")

sec("Validation rules (V-01, V-04, V-06, V-07 hard errors; V-02/V-03/V-05/V-08/V-09 warnings)")
bad_v01 = dict(policy_b)
bad_v01["slr_mode"] = "yes"
errors, _ = LEV.validate_policy(bad_v01)
assert any(e.startswith("V-01") for e in errors)
print("  PASS  V-01 (non-bool slr_mode) raises")

bad_v04 = dict(policy_b)
bad_v04["bank_category"] = "CBLR"
bad_v04["slr_mode"] = True
errors, _ = LEV.validate_policy(bad_v04)
assert any(e.startswith("V-04") for e in errors)
print("  PASS  V-04 (CBLR + slr_mode=true) raises")

bad_v06 = dict(policy_b)
bad_v06["slr_minimum"] = 1.5
errors, _ = LEV.validate_policy(bad_v06)
assert any(e.startswith("V-06") for e in errors)
print("  PASS  V-06 (rate outside [0,1]) raises")

bad_v07 = dict(policy_b)
bad_v07["product_commitment_type"] = {}
bad_v07["slr_mode"] = True
errors, _ = LEV.validate_policy(bad_v07)
assert any(e.startswith("V-07") for e in errors)
print("  PASS  V-07 (unclassified product in SLR mode) raises")

_, warnings = LEV.validate_policy(policy_b)
assert any(w.startswith("V-08") for w in warnings)
print("  PASS  V-08 (inputs_verified=false) warns")

sec("ALL CHECKS PASSED")
