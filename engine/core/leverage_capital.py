"""Leverage capital cost on unused credit lines - a diagnostic completely
separate from the liquidity cost (LCR) diagnostic in customer_view.py, even
though both charge something against undrawn exposure. They are two
different rulebooks:

  - Liquidity (LCR, 12 CFR 249): a stress-scenario cash-outflow assumption.
  - Leverage (this module): a capital-adequacy backstop, risk-weight-agnostic.

US banks face two different leverage regimes, and which one applies decides
whether an unused credit line costs the bank anything at all:

  - Tier 1 leverage ratio (R-01): on-balance-sheet assets only. Unused lines
    are off-balance-sheet, so they are NOT charged. Cost is $0 by
    regulation, not by omission.
  - Supplementary Leverage Ratio / SLR (R-04, R-05): applies ONLY to large
    banks (Category I/II/III). Counts off-balance-sheet exposure too, and -
    critically - does NOT allow the 0% CCF that risk-based capital gives
    unconditionally cancellable commitments like card lines (R-09). Instead
    it uses a flat 10% CCF (R-06). So a bank subject to the SLR holds real
    capital against idle card capacity, even though its risk-based capital
    requirement says the same exposure costs nothing.

Rule IDs cited throughout (R-xx, M-xx) are defined in
governance/REGULATORY_RULEBOOK.md - that document is the single source of
truth for every citation; nothing here should be read as an independent
legal interpretation.

`slr_mode` is a policy fact set by a person from the bank's own regulatory
category, never inferred from asset size in code (M-03) - this module only
applies whichever regime the active policy file declares.

Like liquidity cost, this is a diagnostic: never blended into
trailing_12m_net_economic_profit, cev_score, or any headline total (M-01).
A bank's binding capital requirement is the HIGHER of its risk-based and
leverage requirements, not the sum of what this module and the existing
capital logic report - adding them together would double-count whenever
risk-based capital is the binding constraint.

Reuses customer_view's own avg_undrawn_12m (trailing-12-month average
undrawn exposure) as the base, for the same reason liquidity cost does:
consistency with this engine's customer-level, not ledger-period, framing.
The source spec (SPEC_leverage_capital_cost_v2.md) computes per
account-per-ledger-period and averages SLR off-balance-sheet exposure over
quarterly month-ends (R-13) - this module does not claim regulatory
reporting equivalence, only a comparable diagnostic at the same grain as
every other customer-level figure in this system.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
DEFAULT_POLICY_NAME = "case_b_tier1_regional"

_REGULATORY_DEFAULT_CCF = {
    "UNCONDITIONALLY_CANCELLABLE": 0.10,   # R-06
    "NON_UCC_ORIGINAL_MATURITY_LE_1Y": 0.20,  # R-07
    "NON_UCC_ORIGINAL_MATURITY_GT_1Y": 0.50,  # R-07
}
_RISK_BASED_DEFAULT_CCF_UCC = 0.00  # R-09

# Products this dataset tracks undrawn commitments for (M-05: a legal/
# product determination, not something this code infers). Anything in
# products_without_commitments (term loans, deposits) is skipped entirely.
_KNOWN_COMMITMENT_PRODUCTS = {"credit_card"}


class LeveragePolicyViolation(Exception):
    """A leverage_capital policy file failed a hard validation rule (V-01,
    V-04, V-06, V-07). Mirrors DataContractViolation's role for the data
    contract - this stops the run rather than silently guessing."""


def available_policies() -> dict[str, Path]:
    return {p.stem.replace("leverage_capital_policy.", ""): p
           for p in sorted(_CONFIG_DIR.glob("leverage_capital_policy.*.json"))}


def _policy_path(name_or_path: str | Path) -> Path:
    candidate = Path(name_or_path)
    if candidate.is_file():
        return candidate
    found = available_policies().get(str(name_or_path))
    if found is None:
        raise LeveragePolicyViolation(
            f"No leverage_capital policy named '{name_or_path}'. Available: "
            f"{sorted(available_policies())}")
    return found


def validate_policy(policy: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings). Errors correspond to V-01, V-04, V-06,
    V-07 (SLR mode only) - a caller should raise on any error. Warnings are
    informational (V-02, V-03, V-05, V-08, V-09) and should be surfaced to
    the user, never silently dropped."""
    errors: list[str] = []
    warnings: list[str] = []

    slr_mode = policy.get("slr_mode")
    if not isinstance(slr_mode, bool):
        errors.append("V-01: 'slr_mode' is missing or not a boolean - it "
                      "must be an explicit true/false set by a person (M-03).")
        return errors, warnings  # nothing else is checkable without it

    category = policy.get("bank_category")
    if category in ("I", "II", "III") and not slr_mode:
        warnings.append(f"V-02: bank_category '{category}' is normally an "
                        f"SLR category, but slr_mode is false. Confirm this "
                        f"is intentional.")
    if category in ("IV", "BELOW_100B") and slr_mode:
        warnings.append(f"V-03: bank_category '{category}' does not "
                        f"normally face the SLR, but slr_mode is true. "
                        f"Confirm this is intentional.")
    if category == "CBLR" and slr_mode:
        errors.append("V-04: bank_category is CBLR (Community Bank Leverage "
                      "Ratio) - CBLR banks are not SLR banks by definition "
                      "(R-12). slr_mode cannot be true.")

    if policy.get("eslr_buffer", 0) > 0 and category != "I":
        warnings.append("V-05: eslr_buffer is set above 0 but bank_category "
                        "is not 'I' - the enhanced SLR buffer (R-10) applies "
                        "only to US GSIBs.")

    rate_fields = ["tier1_leverage_minimum", "tier1_leverage_well_capitalised",
                  "slr_minimum", "eslr_buffer", "management_buffer",
                  "risk_based_ccf_ucc", "cost_of_capital_annual",
                  "capital_benefit_rate_annual"]
    for field in rate_fields:
        val = policy.get(field)
        if val is not None and not (0.0 <= val <= 1.0):
            errors.append(f"V-06: '{field}' = {val} is outside [0, 1].")
    for ctype, rate in policy.get("slr_ccf_by_commitment_type", {}).items():
        if not (0.0 <= rate <= 1.0):
            errors.append(f"V-06: slr_ccf_by_commitment_type.{ctype} = "
                          f"{rate} is outside [0, 1].")

    classified = set(policy.get("product_commitment_type", {}).keys())
    unclassified = _KNOWN_COMMITMENT_PRODUCTS - classified
    if unclassified:
        msg = (f"V-07: product(s) {sorted(unclassified)} carry undrawn "
              f"commitments in this dataset but have no entry in "
              f"product_commitment_type (M-05 - this is the bank's legal "
              f"determination, not something this code can infer).")
        if slr_mode:
            errors.append(msg)
        else:
            warnings.append(msg)

    if not policy.get("inputs_verified", False):
        warnings.append("V-08: inputs_verified is false - every regulatory "
                        "value in this policy is an illustrative default "
                        "until a reviewer confirms it against the primary "
                        "source and records the result in "
                        "governance/regulatory_verification_log.md.")

    for ctype, rate in policy.get("slr_ccf_by_commitment_type", {}).items():
        default = _REGULATORY_DEFAULT_CCF.get(ctype)
        if default is not None and rate != default:
            warnings.append(f"V-09: slr_ccf_by_commitment_type.{ctype} = "
                            f"{rate} differs from the regulatory default "
                            f"{default} (R-06/R-07) - requires a documented "
                            f"override reason.")
    if policy.get("risk_based_ccf_ucc", 0.0) != _RISK_BASED_DEFAULT_CCF_UCC:
        warnings.append(f"V-09: risk_based_ccf_ucc = "
                        f"{policy.get('risk_based_ccf_ucc')} differs from "
                        f"the regulatory default {_RISK_BASED_DEFAULT_CCF_UCC} "
                        f"(R-09).")

    return errors, warnings


def load_policy(name_or_path: str | Path = DEFAULT_POLICY_NAME) -> tuple[dict, Path, list[str]]:
    """Loads, validates, and returns (policy, path, warnings). Raises
    LeveragePolicyViolation on any hard error (V-01, V-04, V-06, V-07)."""
    path = _policy_path(name_or_path)
    policy = json.loads(path.read_text(encoding="utf-8"))
    errors, warnings = validate_policy(policy)
    if errors:
        raise LeveragePolicyViolation(
            f"{path.name} failed validation:\n" + "\n".join(f"  - {e}" for e in errors))
    return policy, path, warnings


def compute(cv: pd.DataFrame, policy: dict) -> pd.DataFrame:
    """Per customer: leverage exposure, capital held, and annual capital
    cost on the trailing-12m average undrawn card exposure, under whichever
    regime the policy declares. Always also computes the SLR-as-if "shadow"
    cost (R-06, informational-only panel on the diagnostic page) without
    ever charging it when slr_mode is false - that shadow value is never
    read by L2 or any other downstream consumer (T-10)."""
    out = cv[["Masked Customer Number"]].copy()
    undrawn = cv["avg_undrawn_12m"].clip(lower=0.0)  # M-06

    slr_mode = bool(policy["slr_mode"])
    commitment_type = policy["product_commitment_type"].get(
        "credit_card", "UNCONDITIONALLY_CANCELLABLE")
    ccf = policy["slr_ccf_by_commitment_type"].get(
        commitment_type, policy["slr_ccf_by_commitment_type"]["UNCONDITIONALLY_CANCELLABLE"])
    target_ratio = (policy["slr_minimum"] + policy["eslr_buffer"]
                    + policy["management_buffer"])
    cost_gap = policy["cost_of_capital_annual"] - policy["capital_benefit_rate_annual"]

    shadow_exposure = undrawn * ccf                         # R-05, R-06, R-08
    shadow_capital = shadow_exposure * target_ratio          # R-04, R-10
    shadow_cost = shadow_capital * cost_gap

    out["avg_undrawn_12m"] = undrawn
    out["leverage_regime"] = "SLR" if slr_mode else "TIER1"
    out["commitment_type"] = commitment_type
    out["shadow_leverage_capital_cost"] = shadow_cost

    if slr_mode:
        out["leverage_exposure"] = shadow_exposure
        out["leverage_capital_held"] = shadow_capital
        out["leverage_capital_cost"] = shadow_cost
        out["leverage_status"] = "SLR_CHARGED"
        out["rule_ids"] = "R-04,R-05,R-06,R-08,R-09,R-10"
    else:
        out["leverage_exposure"] = 0.0
        out["leverage_capital_held"] = 0.0
        out["leverage_capital_cost"] = 0.0
        out["leverage_status"] = "TIER1_REGIME_NOT_CHARGED"
        out["rule_ids"] = "R-01,R-09"

    return out[["Masked Customer Number", "avg_undrawn_12m", "leverage_regime",
               "commitment_type", "leverage_exposure", "leverage_capital_held",
               "leverage_capital_cost", "leverage_status", "rule_ids",
               "shadow_leverage_capital_cost"]]


def audit_record(policy_path: Path, policy: dict, warnings: list[str],
                 leverage_df: pd.DataFrame) -> dict:
    """A lightweight run-audit record (9.2): there is no pre-existing
    SHA-256 model-registry pattern in this codebase to extend, so this is a
    plain dict a caller can attach to the run result and download - not a
    persisted registry. The policy file's own hash makes it possible to
    prove, after the fact, exactly which assumptions produced a given run's
    numbers."""
    digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    all_rule_ids = sorted({r for row in leverage_df["rule_ids"] for r in row.split(",")}) \
        if len(leverage_df) else []
    return {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "policy_file": policy_path.name,
        "policy_sha256": digest,
        "policy_version": policy.get("policy_version"),
        "case_label": policy.get("case_label"),
        "slr_mode": bool(policy["slr_mode"]),
        "bank_category": policy.get("bank_category"),
        "rule_ids_applied": all_rule_ids,
        "validation_warnings": warnings,
        "inputs_verified": bool(policy.get("inputs_verified", False)),
        "totals": {
            "customers": int(len(leverage_df)),
            "total_avg_undrawn_12m": float(leverage_df["avg_undrawn_12m"].sum()),
            "total_leverage_exposure": float(leverage_df["leverage_exposure"].sum()),
            "total_leverage_capital_held": float(leverage_df["leverage_capital_held"].sum()),
            "total_leverage_capital_cost": float(leverage_df["leverage_capital_cost"].sum()),
            "total_shadow_leverage_capital_cost": float(
                leverage_df["shadow_leverage_capital_cost"].sum()),
        },
    }
