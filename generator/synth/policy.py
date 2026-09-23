"""Bank policy. THE BANK'S RULES.

This module must never import from latents.py. Policy sees only what a bank
sees: credit score, segment, product, tenure, stated income, and - for line
management after origination - the account's own observed behavior.

Observed behavior is a legitimate input. It is caused by latents, but it is
published data the bank actually holds. Reading it is not the same as reading
a latent, and refusing it would make line management unrealistic.

Every dial here is named after a bank decision, never after an outcome.
"""
from __future__ import annotations
import numpy as np

PRODUCTS = ["Secured Standard", "Standard", "World", "World Elite"]

PROGRAM_BY_PRODUCT = {
    "Secured Standard": ["SECURED_CASHBACK_1"],
    "Standard": ["CORE_LOW_RATE_NO_REWARDS", "CORE_CASHBACK_1_5"],
    "World": ["CORE_CASHBACK_1_5", "EVERYDAY_3X_GROCERY_GAS", "TRAVEL_REWARDS_3X"],
    "World Elite": ["TRAVEL_REWARDS_3X", "PREMIUM_TRAVEL_5X", "BUSINESS_CATEGORY_4X"],
}

ANNUAL_FEE_OPTIONS = {
    "Secured Standard": [0.0],
    "Standard": [0.0, 39.0],
    "World": [0.0, 95.0, 150.0],
    "World Elite": [95.0, 195.0, 395.0],
}

SEGMENTS = ["Retail", "Mass Market", "Mass Affluent", "Premier",
            "Small Business", "Private Banking", "Student"]


def assign_segment(stated_income: np.ndarray, age: np.ndarray,
                   is_business: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Segmentation from what the bank collects: income, age, business flag."""
    out = np.empty(len(stated_income), dtype=object)
    for i, (inc, a, biz) in enumerate(zip(stated_income, age, is_business)):
        if a <= 24 and inc < 45000:
            out[i] = "Student"
        elif biz:
            out[i] = "Small Business"
        elif inc >= 250000:
            out[i] = "Private Banking"
        elif inc >= 130000:
            out[i] = "Premier"
        elif inc >= 80000:
            out[i] = "Mass Affluent"
        elif inc >= 45000:
            out[i] = "Mass Market"
        else:
            out[i] = "Retail"
    return out


def assign_product(score: np.ndarray, segment: np.ndarray,
                   rng: np.random.Generator) -> np.ndarray:
    """Underwriting: score and segment decide the tier offered."""
    out = np.empty(len(score), dtype=object)
    for i, (s, seg) in enumerate(zip(score, segment)):
        if s < 600:
            out[i] = "Secured Standard"
        elif s < 660:
            out[i] = rng.choice(["Secured Standard", "Standard"], p=[0.22, 0.78])
        elif s < 720:
            out[i] = rng.choice(["Standard", "World"], p=[0.62, 0.38])
        elif s < 780:
            if seg in ("Private Banking", "Premier", "Small Business"):
                out[i] = rng.choice(["World", "World Elite"], p=[0.62, 0.38])
            else:
                out[i] = rng.choice(["Standard", "World"], p=[0.28, 0.72])
        else:
            if seg in ("Private Banking", "Premier", "Small Business"):
                out[i] = rng.choice(["World", "World Elite"], p=[0.34, 0.66])
            else:
                out[i] = rng.choice(["World", "World Elite"], p=[0.70, 0.30])
    return out


def assign_program(product: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return np.array([rng.choice(PROGRAM_BY_PRODUCT[p]) for p in product])


def origination_limit(score: np.ndarray, product: np.ndarray, segment: np.ndarray,
                      stated_income: np.ndarray, rng: np.random.Generator,
                      generosity: float = 1.0) -> np.ndarray:
    """Limit at origination. Blind to credit appetite, which is the point.

    `generosity` is a bank-side dial. Turning it down produces fewer wildly
    oversized lines without ever naming how many underused lines should exist.
    """
    base = {"Secured Standard": 385.0, "Standard": 1520.0,
            "World": 4100.0, "World Elite": 7800.0}
    seg_mult = {"Private Banking": 1.85, "Premier": 1.45, "Mass Affluent": 1.18,
                "Mass Market": 0.94, "Retail": 0.80, "Small Business": 1.50,
                "Student": 0.45}
    b = np.array([base[p] for p in product])
    m = np.array([seg_mult.get(s, 1.0) for s in segment])
    score_mult = 0.55 + (np.clip(score, 500, 850) - 500) / 350.0 * 1.30
    # Income is a real underwriting input and caps exposure.
    income_cap = np.clip(stated_income, 12000, 600000) * 0.42
    noise = rng.lognormal(0.0, 0.24, len(score))
    lim = np.minimum(b * m * score_mult * noise * generosity, income_cap)
    return (np.round(lim / 250.0) * 250.0).clip(300.0, 60000.0)


def line_review(current_limit: float, observed_peak_utilization: float,
                observed_months_active: int, days_past_due: int,
                score: int, generosity: float, use_observed_behavior: bool,
                review_draw: float = 0.0):
    """Periodic line review. Returns (new_limit, reason_code) or (None, None).

    `use_observed_behavior` is the negative control's line-management
    mechanism: a well-run bank right-sizes a line against the utilization it
    has actually seen. It reads published behavior, never a latent, and it is
    lagged - it cannot act on utilization it has not yet observed.
    """
    if days_past_due >= 60:
        return max(current_limit * 0.55, 300.0), "RISK_DETERIORATION"
    if observed_months_active < 6:
        return None, None

    if use_observed_behavior:
        # Right-size toward observed demand, with generous headroom.
        if observed_peak_utilization < 0.12 and current_limit > 1500:
            target = max(current_limit * 0.62, 1000.0)
            return round(target / 250.0) * 250.0, "LINE_RIGHT_SIZED"
        if observed_peak_utilization > 0.82 and score >= 660 and days_past_due == 0:
            target = current_limit * 1.28
            return round(target / 250.0) * 250.0, "CUSTOMER_DEMAND"
    else:
        # Growth-led line management: increase on good standing regardless of
        # whether the customer has shown any demand for the line.
        if (score >= 680 and days_past_due == 0 and observed_months_active >= 12
                and review_draw < 0.35):
            target = current_limit * (1.18 * generosity)
            return round(target / 250.0) * 250.0, "PROACTIVE_INCREASE"
    return None, None


def contractual_apr(score: np.ndarray, product: np.ndarray,
                    rng: np.random.Generator) -> np.ndarray:
    """Risk-based APR written into the cardholder agreement at origination."""
    base = 28.15 - (np.clip(score, 500, 850) - 500) / 350.0 * 11.5
    prod_adj = np.array([{"Secured Standard": 1.75, "Standard": 0.0,
                          "World": -0.95, "World Elite": -1.80}[p] for p in product])
    return np.round(np.clip(base + prod_adj + rng.normal(0, 0.85, len(score)),
                            12.99, 31.99), 2)


def annual_fee(product: np.ndarray, program: np.ndarray,
               rng: np.random.Generator, fee_aligned_to_reward: bool = False,
               expected_reward_value: np.ndarray | None = None) -> np.ndarray:
    """Annual fee decision.

    `fee_aligned_to_reward` is the negative control's pricing mechanism: only
    charge a fee where the program's expected reward value plausibly supports
    it. The demo book prices the fee off the product tier alone, which is what
    leaves fee-bearing accounts with thin reward take.
    """
    out = np.zeros(len(product))
    rich = {"PREMIUM_TRAVEL_5X", "TRAVEL_REWARDS_3X", "BUSINESS_CATEGORY_4X"}
    for i, (p, pg) in enumerate(zip(product, program)):
        opts = ANNUAL_FEE_OPTIONS[p]
        if len(opts) == 1:
            out[i] = opts[0]
            continue
        if len(opts) == 3:
            w = [0.55, 0.30, 0.15] if pg in rich else [0.90, 0.08, 0.02]
        else:
            w = [0.68, 0.32] if pg in rich else [0.95, 0.05]
        w = np.array(w[:len(opts)], dtype=float)
        draw = rng.choice(opts, p=w / w.sum())
        if fee_aligned_to_reward and expected_reward_value is not None:
            # The SAME draw as the base policy, capped so it never exceeds
            # what the program's expected reward value plausibly supports.
            # This fixes overcharging without independently inflating
            # incidence - the defect is the gap between fee and value, not
            # the presence of a fee.
            affordable = [o for o in opts if o <= expected_reward_value[i] * 0.85]
            cap = max(affordable) if affordable else 0.0
            draw = min(draw, cap)
        out[i] = draw
    return out


def digital_deflection_rate(base_rate: float = 0.42) -> float:
    """Share of servicing contacts the bank's self-service estate absorbs.

    This is the servicing-efficiency mechanism the negative control varies. It
    is a property of the bank's channel estate, not of the customer.
    """
    return base_rate


CHANNEL_ACQUISITION_COST_MEAN = {
    "branch": 145.0, "digital": 95.0, "aggregator": 220.0,
    "partner": 175.0, "direct_mail": 130.0,
}


def acquisition_cost(channel: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Cost per account acquired, by channel. A bank cost, not an outcome -
    channels differ in cost the same way they differ in customer quality, and
    the two are independent inputs. Lognormal noise keeps individual accounts
    from carrying an identical, obviously-synthetic cost."""
    mean = np.array([CHANNEL_ACQUISITION_COST_MEAN[c] for c in channel])
    noise = rng.lognormal(0.0, 0.22, len(channel))
    return np.round(mean * noise, 2)


def waiver_policy(rng: np.random.Generator, n: int, waiver_rate: float,
                  review_discipline: float):
    """Fee concession policy.

    `waiver_rate` - how readily the bank grants concessions.
    `review_discipline` - share of concessions given a review date at all.
    Both are bank behaviors. Whether an expired concession then keeps
    suppressing fees is a defect, planted separately.
    """
    granted = rng.random(n) < waiver_rate
    has_review_date = rng.random(n) < review_discipline
    return granted, has_review_date
