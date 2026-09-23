"""
Bank policy.

These are the bank's own rules, written from "how a bank works". They are
deliberately blind to the latents in synth/latents.py - a real bank cannot
see credit appetite either. Mispricing and underused limits emerge from the
mismatch between what policy grants and what the customer actually wants.

Nothing here may reference a customer's eventual profitability.
"""
from __future__ import annotations
import numpy as np

PRODUCTS = ["Secured Standard", "Standard", "World", "World Elite"]

# Programme available on each product tier.
PROGRAMME_BY_PRODUCT = {
    "Secured Standard": ["SECURED_CASHBACK_1"],
    "Standard": ["LOW_RATE_NONE", "OSU_VOICE_LOW_RATE", "CASHBACK_1_5"],
    "World": ["CASHBACK_1_5", "OSU_VOICE_REWARDS", "VOICE_REWARDS_3X"],
    "World Elite": ["VOICE_REWARDS_3X", "BUSINESS_CATEGORY_4", "CASHBACK_1_5"],
}

ANNUAL_FEE_BY_PRODUCT = {
    "Secured Standard": [0, 39], "Standard": [0, 39],
    "World": [0, 95, 150], "World Elite": [95, 195, 395],
}


def assign_product(score: np.ndarray, segment: np.ndarray,
                   rng: np.random.Generator) -> np.ndarray:
    """Underwriting policy: score and segment decide the tier offered."""
    out = np.empty(len(score), dtype=object)
    for i, (s, seg) in enumerate(zip(score, segment)):
        if s < 600:
            out[i] = "Secured Standard"
        elif s < 670:
            out[i] = "Standard"
        elif s < 740:
            out[i] = rng.choice(["Standard", "World"], p=[0.45, 0.55])
        else:
            if seg in ("Private Banking", "Premier", "Small Business"):
                out[i] = rng.choice(["World", "World Elite"], p=[0.35, 0.65])
            else:
                out[i] = rng.choice(["World", "World Elite"], p=[0.68, 0.32])
    return out


def limit_policy(score: np.ndarray, product: np.ndarray, segment: np.ndarray,
                 rng: np.random.Generator, generosity: float = 1.0) -> np.ndarray:
    """Limit assignment. Blind to credit appetite - which is the whole point.

    `generosity` is a bank-side dial. Turning it down (negative control)
    produces a book with fewer wildly oversized limits, without ever naming
    how many underused limits should exist.
    """
    base = {"Secured Standard": 900, "Standard": 3200, "World": 9000, "World Elite": 17000}
    seg_mult = {"Private Banking": 1.9, "Premier": 1.45, "Mass Affluent": 1.15,
                "Mass Market": 0.92, "Retail": 0.8, "Small Business": 1.5, "Student": 0.5}
    b = np.array([base[p] for p in product], dtype=float)
    m = np.array([seg_mult.get(s, 1.0) for s in segment])
    score_mult = 0.55 + (np.clip(score, 500, 850) - 500) / 350.0 * 1.25
    noise = rng.lognormal(0.0, 0.26, len(score))
    lim = b * m * score_mult * noise * generosity
    return (np.round(lim / 250.0) * 250.0).clip(300, 60000)


def pricing_policy(score: np.ndarray, product: np.ndarray,
                   rng: np.random.Generator) -> np.ndarray:
    """Risk-based APR set at origination. Risk drifts afterwards; the rate
    largely does not. Mispricing emerges from that gap, not from a flag."""
    base = 28.5 - (np.clip(score, 500, 850) - 500) / 350.0 * 12.0
    prod_adj = np.array([{"Secured Standard": 1.6, "Standard": 0.0,
                          "World": -0.8, "World Elite": -1.6}[p] for p in product])
    return np.round(np.clip(base + prod_adj + rng.normal(0, 0.9, len(score)), 9.99, 31.99), 2)


def assign_programme(product: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return np.array([rng.choice(PROGRAMME_BY_PRODUCT[p]) for p in product])


def assign_annual_fee(product: np.ndarray, programme: np.ndarray,
                      rng: np.random.Generator) -> np.ndarray:
    """Richer programmes carry a fee more often - but not always, which is
    exactly the gap lever 1 is meant to find."""
    out = np.zeros(len(product))
    for i, (p, pg) in enumerate(zip(product, programme)):
        opts = ANNUAL_FEE_BY_PRODUCT[p]
        rich = pg in ("VOICE_REWARDS_3X", "BUSINESS_CATEGORY_4")
        w = [0.30, 0.45, 0.25] if (rich and len(opts) == 3) else \
            [0.62, 0.28, 0.10] if len(opts) == 3 else \
            [0.55, 0.45] if rich else [0.80, 0.20]
        out[i] = rng.choice(opts, p=w[:len(opts)] / np.sum(w[:len(opts)]))
    return out
