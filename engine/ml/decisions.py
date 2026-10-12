"""Decision engine for the ML credit-limit recommendation - pressure score,
stress flags, the 9-step waterfall, reduction/increase arithmetic, the
portfolio pilot cap, and the money figures. Ported from the sibling
credit-limit-recommendation-system's decisions.py (SYSTEM_BREAKDOWN.md
Parts 9-10), adapted to CES's column names and policy file format.

The pressure score is a DETERMINISTIC COMPOSITE of already-observed
behavior, not a model output - confirmed from the source system's own
documentation. It is safe under this repo's "never fabricate" discipline
for the same reason the six existing levers' rule-based logic is: every
input is a measured quantity, nothing here is invented.

Two CES-specific adaptations from a blind port, both deliberate:
  - The expected-loss money figure uses CES's own measured per-customer
    `lgd` (from customer_view) when available, falling back to the
    policy-configured constant only when it isn't - never fabricate a
    number when a measured one already exists.
  - CES has no "Account block code" / "Account status code" concept
    anywhere in its generator, so CLRS's STEP 4 (MANUAL_REVIEW on a
    blocked account) has no CES equivalent and is omitted; "is_active"
    here means "not charged off" (CES accounts simply stop appearing in
    Table4_Account_Cycle.csv after charge-off - see
    generator/synth/cycles.py - there is no separate status flag to check).

Suppression (hardship/accommodation/SCRA) is applied by the CALLER
(app/pages/25_ML_Credit_Limit.py), using result["suppressed"].suppressed,
exactly as every other page in this repo does - this module has no concept
of suppression and does not need one.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
DEFAULT_POLICY_PATH = _CONFIG_DIR / "ml_credit_limit_policy.json"

REDUCTION_CUT_FLOOR = 0.85  # candidate <= current_limit * 0.85 (CLRS: "the cut must be >=15%")
INCREASE_MIN_RAISE = 1.10   # max(demand_limit, current_limit * 1.10)


class MLCreditLimitPolicyViolation(Exception):
    """A ml_credit_limit_policy.json failed a hard validation rule."""


def validate_policy(policy: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rate_fields = ["risk_low_threshold", "risk_high_threshold",
                  "maximum_percentage_reduction", "maximum_reduction_share_per_review",
                  "reduction_average_utilisation_max", "reduction_peak_utilisation_max",
                  "reduction_projected_utilisation_max", "increase_target_utilisation",
                  "interchange_revenue_rate", "loss_given_difficulty_fallback",
                  "undrawn_exposure_conversion_factor", "annual_released_capacity_value_rate"]
    for f in rate_fields:
        v = policy.get(f)
        if v is not None and not (0.0 <= v <= 1.0):
            errors.append(f"'{f}' = {v} is outside [0, 1].")
    if policy.get("risk_low_threshold", 0) >= policy.get("risk_high_threshold", 1):
        errors.append("'risk_low_threshold' must be less than 'risk_high_threshold'.")
    bands = policy.get("increase_bands", {})
    if not ("small" in bands and "moderate" in bands and "large" in bands):
        errors.append("'increase_bands' must define small/moderate/large.")
    if policy.get("minimum_history_cycles", 0) < 1:
        errors.append("'minimum_history_cycles' must be >= 1.")
    if not policy.get("product_minimum_limits") or not policy.get("product_maximum_limits"):
        warnings.append("No product_minimum_limits/product_maximum_limits configured - "
                        "every product falls back to default_minimum_limit/default_maximum_limit.")
    return errors, warnings


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> tuple[dict, list[str]]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    errors, warnings = validate_policy(policy)
    if errors:
        raise MLCreditLimitPolicyViolation(
            f"{path.name} failed validation:\n" + "\n".join(f"  - {e}" for e in errors))
    return policy, warnings


def _product_limit(product_tier: pd.Series, table: dict, default: float) -> pd.Series:
    return product_tier.astype(str).map(table).fillna(default)


def pressure_score(d: pd.DataFrame) -> pd.Series:
    a = (d["utilization_6m_avg"].clip(0, 1.5) / 1.5).fillna(0)
    m = (d["utilization_6m_max"].clip(0, 1.5) / 1.5).fillna(0)
    p = (d["months_utilization_over_70_6m"].clip(0, 6) / 6).fillna(0)
    t = (-d["balance_trend_3m"] / d["current_limit"].clip(lower=1)).clip(lower=0).fillna(0)
    g = (d["spend_trend_3m"] / d["spend_6m_avg"].clip(lower=1)).clip(lower=0).fillna(0)
    return (100 * (0.30 * a + 0.25 * m + 0.20 * p + 0.15 * t + 0.10 * g)).clip(0, 100)


def stress_flags(d: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=d.index)
    out["REPEATED_MISSED_PAYMENTS"] = d["missed_payments_6m"] >= 2
    out["REPEATED_LATE_FEES"] = d["late_fees_6m"] >= 2
    out["PERSISTENT_MINIMUM_ONLY_PAYMENTS"] = d["minimum_only_rate_6m"] >= 0.67
    cash_advance_relevant = d["_has_cash_advance_data"]
    out["HIGH_CASH_ADVANCE_USAGE"] = cash_advance_relevant & (
        d["cash_advance_6m_sum"] > np.maximum(d["spend_6m_sum"] * 0.25, 500))
    out["EXTREME_UTILISATION"] = d["latest_utilization"] >= 0.95
    out["CONSECUTIVE_MISSED_PAYMENTS"] = d["consecutive_missed_payments"] >= 2
    out["severe_stress"] = (out["REPEATED_MISSED_PAYMENTS"] | out["CONSECUTIVE_MISSED_PAYMENTS"]
                            | (out["EXTREME_UTILISATION"] & out["PERSISTENT_MINIMUM_ONLY_PAYMENTS"]))
    return out


def confidence(d: pd.DataFrame, policy: dict) -> pd.Series:
    low, high = policy["risk_low_threshold"], policy["risk_high_threshold"]
    risk = d["predicted_risk_probability"]
    distance = pd.concat([(risk - low).abs(), (risk - high).abs()], axis=1).min(axis=1)
    out = pd.Series("Low", index=d.index)
    scoreable = (d["history_cycles"] >= 6) & risk.notna()
    high_conf = scoreable & (d["history_cycles"] >= 12) & (distance >= 0.03)
    med_conf = scoreable & ~high_conf
    out = out.where(~med_conf, "Medium")
    out = out.where(~high_conf, "High")
    return out


def risk_category(risk: pd.Series, policy: dict) -> pd.Series:
    low, high = policy["risk_low_threshold"], policy["risk_high_threshold"]
    cat = pd.Series("Unavailable", index=risk.index)
    cat = cat.where(risk.isna(), "Moderate")
    cat = cat.where(~(risk <= low), "Low")
    cat = cat.where(~(risk >= high), "High")
    return cat.where(risk.notna(), "Unavailable")


def _reduction_eligible(d: pd.DataFrame, policy: dict) -> pd.Series:
    risk = d["predicted_risk_probability"]
    proj_util = (d["predicted_3m_peak_balance"] / d["current_limit"].replace(0, np.nan))
    cur_util = (d["current_balance"] / d["current_limit"].replace(0, np.nan))
    return (
        (d["history_cycles"] >= policy["minimum_reduction_history_cycles"])
        & (d["utilization_6m_avg"] <= policy["reduction_average_utilisation_max"])
        & (d["utilization_12m_max"] <= policy["reduction_peak_utilisation_max"])
        & (proj_util <= policy["reduction_projected_utilisation_max"])
        & (cur_util <= 0.10)
        & (d["missed_payments_6m"] == 0)
        & (d["late_payments_6m"] == 0)
        & (risk <= policy["risk_low_threshold"])
        & (d["spend_trend_3m"] <= np.maximum(d["spend_6m_avg"] * 0.10, 50))
    ).fillna(False)


def _reduction_amount(d: pd.DataFrame, policy: dict, min_limit: pd.Series) -> pd.DataFrame:
    required = pd.concat([
        min_limit,
        d["current_balance"] / 0.40,
        d["balance_6m_max"] * 1.25,
        d["predicted_3m_peak_balance"] / 0.40,
    ], axis=1).max(axis=1)
    floor_from_cap = d["current_limit"] * (1 - policy["maximum_percentage_reduction"])
    candidate = pd.concat([required, floor_from_cap, min_limit], axis=1).max(axis=1)
    candidate = pd.concat([d["current_limit"], candidate], axis=1).min(axis=1)
    inc = policy["rounding_increment"]
    candidate = (np.ceil(candidate / inc) * inc)
    accept = ((d["current_limit"] - candidate) >= policy["minimum_reduction_amount"]) & (
        candidate <= d["current_limit"] * REDUCTION_CUT_FLOOR)
    return pd.DataFrame({"reduction_candidate": candidate, "reduction_accept": accept})


def _increase_eligible(d: pd.DataFrame, policy: dict, severe: pd.Series, pressure: pd.Series) -> pd.Series:
    risk = d["predicted_risk_probability"]
    demand_ratio = d["predicted_3m_spend"] / d["current_limit"].replace(0, np.nan)
    return (
        (risk <= policy["risk_low_threshold"]) & (~severe)
        & (pressure >= 38) & (demand_ratio >= 0.70)
    ).fillna(False)


def _increase_amount(d: pd.DataFrame, policy: dict, pressure: pd.Series,
                     max_limit: pd.Series) -> pd.DataFrame:
    demand_ratio = d["predicted_3m_spend"] / d["current_limit"].replace(0, np.nan)
    bands = policy["increase_bands"]
    band_pct = pd.Series(bands["small"], index=d.index)
    band_pct = band_pct.where(~((pressure >= 50) & (demand_ratio >= 1.00)), bands["moderate"])
    band_pct = band_pct.where(~((pressure >= 65) & (demand_ratio >= 1.50)), bands["large"])

    percentage_amount = d["current_limit"] * (1 + band_pct)
    absolute_ceiling = d["current_limit"] + policy["maximum_absolute_increase"]
    demand_limit = pd.concat([
        d["current_limit"],
        d["predicted_3m_peak_balance"] / policy["increase_target_utilisation"],
        (d["predicted_3m_spend"] / 3) / 0.50,
    ], axis=1).max(axis=1)
    demand_floor = pd.concat([demand_limit, d["current_limit"] * INCREASE_MIN_RAISE],
                             axis=1).max(axis=1)
    candidate = pd.concat([percentage_amount, absolute_ceiling, max_limit, demand_floor],
                          axis=1).min(axis=1)
    inc = policy["rounding_increment"]
    candidate = (np.ceil(candidate / inc) * inc)
    accept = candidate > d["current_limit"]
    return pd.DataFrame({"increase_candidate": candidate, "increase_accept": accept})


def _waterfall(d: pd.DataFrame, policy: dict, severe: pd.Series, pressure: pd.Series,
              reduction: pd.DataFrame, increase: pd.DataFrame) -> pd.DataFrame:
    n = len(d)
    action = pd.Series("MAINTAIN", index=d.index)
    reason = pd.Series("CURRENT_LIMIT_APPROPRIATE", index=d.index)
    recommended_limit = d["current_limit"].copy()

    def _set(mask, act, why, limit=None):
        action[mask] = act
        reason[mask] = why
        if limit is not None:
            recommended_limit[mask] = limit[mask] if isinstance(limit, pd.Series) else limit

    unresolved = pd.Series(True, index=d.index)

    step1 = unresolved & (d["history_cycles"] < policy["minimum_history_cycles"])
    _set(step1, "INSUFFICIENT_HISTORY", "INSUFFICIENT_BEHAVIOURAL_HISTORY")
    unresolved &= ~step1

    step2 = unresolved & (~d["is_active"])
    _set(step2, "NOT_ELIGIBLE", "ACCOUNT_NOT_ACTIVE")
    unresolved &= ~step2

    step3 = unresolved & (~d["valid_limit"])
    _set(step3, "NOT_ELIGIBLE", "INVALID_CURRENT_LIMIT")
    unresolved &= ~step3

    step5 = unresolved & (d["_latest_days_past_due"] > 0)
    _set(step5, "FREEZE_NO_INCREASE", "CURRENT_DELINQUENCY")
    unresolved &= ~step5

    step6 = unresolved & d["predicted_risk_probability"].isna()
    _set(step6, "MANUAL_REVIEW", "MODEL_SCORE_UNAVAILABLE")
    unresolved &= ~step6

    elevated_risk = d["predicted_risk_probability"] >= policy["risk_high_threshold"]
    step7 = unresolved & (elevated_risk | severe)
    step7_reason = np.where(elevated_risk[step7], "ELEVATED_REPAYMENT_RISK", "SEVERE_FINANCIAL_STRESS")
    reason[step7] = step7_reason
    action[step7] = "FREEZE_NO_INCREASE"
    unresolved &= ~step7

    step8 = unresolved & reduction["reduction_accept"]
    _set(step8, "DECREASE_UNUSED_EXPOSURE", "LOW_AND_STABLE_UTILISATION", reduction["reduction_candidate"])
    unresolved &= ~step8

    step9_inc = unresolved & increase["increase_accept"]
    _set(step9_inc, "INCREASE", "SUSTAINED_DEMAND_AND_LOW_RISK", increase["increase_candidate"])
    unresolved &= ~step9_inc

    mixed = unresolved & (d["predicted_risk_probability"] > policy["risk_low_threshold"]) & (
        (pressure >= 50) | severe)
    _set(mixed, "MANUAL_REVIEW", "MIXED_RISK_AND_OPPORTUNITY_SIGNALS")

    return pd.DataFrame({"ml_action": action, "ml_primary_reason": reason,
                         "ml_recommended_limit": recommended_limit})


def _apply_pilot_cap(d: pd.DataFrame, waterfall: pd.DataFrame, pressure: pd.DataFrame,
                     policy: dict) -> pd.DataFrame:
    wf = waterfall.copy()
    is_reduction = wf["ml_action"] == "DECREASE_UNUSED_EXPOSURE"
    max_reductions = max(1, math.floor(len(d) * policy["maximum_reduction_share_per_review"]))
    n_reductions = int(is_reduction.sum())
    if n_reductions <= max_reductions:
        return wf

    proj_util = (d["predicted_3m_peak_balance"] / d["current_limit"].replace(0, np.nan)).fillna(1)
    priority = (35 * d["utilization_6m_avg"].fillna(1) + 25 * d["utilization_12m_max"].fillna(1)
               + 25 * proj_util + 15 * d["predicted_risk_probability"].fillna(1))
    candidates = priority[is_reduction].sort_values()
    keep_ids = set(candidates.index[:max_reductions])
    revert = is_reduction & ~pd.Series(d.index.isin(keep_ids), index=d.index)
    wf.loc[revert, "ml_action"] = "MAINTAIN"
    wf.loc[revert, "ml_primary_reason"] = "REDUCTION_CANDIDATE_OUTSIDE_PILOT_CAP"
    wf.loc[revert, "ml_recommended_limit"] = d.loc[revert, "current_limit"]
    wf["ml_pilot_cap_deferred"] = revert
    return wf


def _money_figures(d: pd.DataFrame, waterfall: pd.DataFrame, policy: dict) -> pd.DataFrame:
    undrawn = (waterfall["ml_recommended_limit"] - d["current_balance"]).clip(lower=0)
    ead = d["current_balance"].clip(lower=0) + undrawn * policy["undrawn_exposure_conversion_factor"]
    lgd = d["lgd"].fillna(policy["loss_given_difficulty_fallback"]) if "lgd" in d.columns \
        else pd.Series(policy["loss_given_difficulty_fallback"], index=d.index)

    interchange = (d["predicted_3m_spend"].fillna(0) * policy["interchange_revenue_rate"])
    expected_loss = (d["predicted_risk_probability"].fillna(0) * ead * lgd)
    is_decrease = waterfall["ml_action"] == "DECREASE_UNUSED_EXPOSURE"
    released_exposure = (d["current_limit"] - waterfall["ml_recommended_limit"]).clip(lower=0).where(
        is_decrease, 0.0)
    released_value_3m = released_exposure * policy["annual_released_capacity_value_rate"] / 4
    risk_adjusted = interchange + released_value_3m - expected_loss

    return pd.DataFrame({
        "ml_expected_3m_interchange_proxy": interchange,
        "ml_expected_loss_proxy": expected_loss,
        "ml_released_capacity_value_proxy_3m": released_value_3m,
        "ml_risk_adjusted_value_proxy": risk_adjusted,
    })


def exclude_suppressed(result: pd.DataFrame, suppressed_customer_ids) -> pd.DataFrame:
    """This module has no concept of suppression (see module docstring) -
    decide()'s output will happily carry an actionable action for a
    hardship/accommodation/SCRA customer, exactly like every other
    pre-suppression computation in this engine. In the live app this is
    harmless: engine/run.py merges the ml_* columns into `cv` BEFORE
    suppression.run(cv) executes, so result["customer_view"] is already
    suppression-safe by the time any page reads it - the same free
    protection every other page in this repo gets. This helper exists only
    for the one case that bypasses that ordering: calling decide() directly,
    outside build_pipeline() (what audit/audit_ml_credit_limit.py does to
    test this property in isolation). The page does not call it."""
    suppressed_ids = set(suppressed_customer_ids)
    return result[~result["Masked Customer Number"].isin(suppressed_ids)]


def decide(scored: pd.DataFrame, cv: pd.DataFrame, policy: dict) -> pd.DataFrame:
    """scored: engine.ml.score.score()'s output (one row per account).
    cv: the full customer_view frame (pre-suppression, i.e. result's own
    `routed.frame` equivalent before suppression is applied by the caller) -
    used only to look up each customer's own measured `lgd` for the money
    figures. Returns `scored` with every decision/money-figure column
    appended, still keyed by Masked Customer Number for the caller to join
    against suppression and L2's action."""
    d = scored.merge(cv[["Masked Customer Number", "lgd"]], on="Masked Customer Number", how="left")

    min_limit = _product_limit(d["product_tier"], policy["product_minimum_limits"],
                               policy["default_minimum_limit"])
    max_limit = _product_limit(d["product_tier"], policy["product_maximum_limits"],
                               policy["default_maximum_limit"])

    pressure = pressure_score(d)
    flags = stress_flags(d)
    severe = flags["severe_stress"]

    reduction_eligible = _reduction_eligible(d, policy)
    reduction = _reduction_amount(d, policy, min_limit)
    reduction["reduction_accept"] = reduction["reduction_accept"] & reduction_eligible

    increase_eligible = _increase_eligible(d, policy, severe, pressure)
    increase = _increase_amount(d, policy, pressure, max_limit)
    increase["increase_accept"] = increase["increase_accept"] & increase_eligible

    waterfall = _waterfall(d, policy, severe, pressure, reduction, increase)
    waterfall["ml_recommended_limit"] = waterfall["ml_recommended_limit"].clip(
        lower=min_limit, upper=max_limit)
    waterfall = _apply_pilot_cap(d, waterfall, pressure, policy)
    if "ml_pilot_cap_deferred" not in waterfall.columns:
        waterfall["ml_pilot_cap_deferred"] = False

    money = _money_figures(d, waterfall, policy)

    out = pd.concat([d, waterfall, money], axis=1)
    out["ml_pressure_score"] = pressure
    out["ml_severe_stress"] = severe
    out["ml_risk_category"] = risk_category(d["predicted_risk_probability"], policy)
    out["ml_confidence"] = confidence(d, policy)
    for col in flags.columns:
        out[f"ml_flag_{col}"] = flags[col]
    return out
