"""Reward model assumptions: the Excel workbook's defaults, editable.

config/reward_model_assumptions.json was extracted from the Reward
Profitability Scenario Model v2 (its sha256 is recorded inside). Everything in
it is an illustrative industry-average estimate, not portfolio data.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

CONFIG = Path(__file__).parent / "config" / "reward_model_assumptions.json"
SEGMENTS = ["optimizers", "bonus_chasers", "quasi_cash", "low_spend", "relationship"]
SCENARIOS = ["conservative", "base", "aggressive"]
LEVERS = ["earn_rate_reduction_pp", "excluded_spend_share", "bonus_category_cap_cut",
          "redemption_steering_cut", "annual_fee_increase_usd", "merchant_funded_share",
          "product_change_share", "revolving_balance_uplift", "signup_bonus_cost_cut"]
LEVER_LABELS = {
    "earn_rate_reduction_pp": "Earn-rate reduction (pp of spend)",
    "excluded_spend_share": "Quasi-cash / low-interchange spend excluded from earn",
    "bonus_category_cap_cut": "Bonus-category cap (cut in reward earned)",
    "redemption_steering_cut": "Redemption steering (cut in cost per $ redeemed)",
    "annual_fee_increase_usd": "Annual fee increase ($)",
    "merchant_funded_share": "Merchant-funded offers (share of reward cost)",
    "product_change_share": "Product change to non-rewards (share of accounts)",
    "revolving_balance_uplift": "Revolving balance stimulation (increase)",
    "signup_bonus_cost_cut": "Sign-up bonus controls (cut in bonus cost)",
}


class AssumptionsError(ValueError):
    pass


def load(path: Path | str | None = None) -> tuple[dict, str]:
    p = Path(path) if path else CONFIG
    raw = p.read_bytes()
    cfg = json.loads(raw)
    for scn in SCENARIOS:
        for lever in LEVERS:
            missing = [s for s in SEGMENTS if s not in cfg["levers"][scn][lever]]
            if missing:
                raise AssumptionsError(f"{p.name}: {scn}.{lever} missing segments {missing}")
    for lever in LEVERS:
        timing = cfg["lever_timing"].get(lever)
        if timing is None or not 0 <= timing["year1_share"] <= 1:
            raise AssumptionsError(f"{p.name}: lever_timing.{lever} missing or year1_share outside [0, 1]")
    return cfg, hashlib.sha256(raw).hexdigest()


def levers_for(cfg: dict, scenario: str) -> dict:
    """{lever: {segment: value}} for one scenario (a copy)."""
    if scenario not in SCENARIOS:
        raise AssumptionsError(f"unknown scenario {scenario!r}")
    return copy.deepcopy(cfg["levers"][scenario])


def with_overrides(cfg: dict, overrides: dict) -> dict:
    """A copy of `cfg` with nested overrides, e.g.
    {"behaviour": {"attrition_per_10pct_value_cut": {"optimizers": 0.06}},
     "portfolio": {"behavioural_response_multiplier": 1.5}}."""
    out = copy.deepcopy(cfg)

    def merge(dst, src, path):
        for k, v in src.items():
            if k not in dst:
                raise AssumptionsError(f"unknown assumption {'.'.join(path + [k])}")
            if isinstance(v, dict):
                merge(dst[k], v, path + [k])
            else:
                dst[k] = v
    merge(out, overrides, [])
    return out
