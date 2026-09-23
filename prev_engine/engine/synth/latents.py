"""
Latent customer traits.

These are the CAUSES. Everything the analytical engine reports must emerge
from these meeting bank policy (see synth/policy.py). Nothing in this module
may be named after an engine output.

Latents are written to Latent_Ground_Truth.csv and are NEVER joined into any
table the engine reads.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SPEND_PERSONAS = ["travel", "grocery", "everyday", "business", "online"]

# Persona mix varies by segment - this is a statement about people, not about
# profitability. Order matches SPEND_PERSONAS.
PERSONA_BY_SEGMENT = {
    "Private Banking": [0.34, 0.12, 0.20, 0.18, 0.16],
    "Premier":         [0.26, 0.16, 0.24, 0.14, 0.20],
    "Mass Affluent":   [0.16, 0.22, 0.30, 0.10, 0.22],
    "Mass Market":     [0.08, 0.30, 0.34, 0.06, 0.22],
    "Retail":          [0.06, 0.32, 0.36, 0.04, 0.22],
    "Small Business":  [0.12, 0.10, 0.18, 0.46, 0.14],
    "Student":         [0.05, 0.26, 0.38, 0.02, 0.29],
}

REDEMPTION_TYPES = ["fast", "steady", "hoarder", "never"]


def draw_latents(n: int, segments: np.ndarray, scores: np.ndarray,
                 rng: np.random.Generator, profile: dict) -> pd.DataFrame:
    """One latent vector per customer.

    `profile` shifts the population (used for the negative control and the
    portfolio variants). It never sets an outcome - only the distribution of
    traits and the bank's own generosity.
    """
    tilt = profile.get("latent_tilt", {})

    def beta(a, b, shift=0.0):
        v = rng.beta(a, b, n) + shift
        return np.clip(v, 0.01, 0.99)

    # Appetite for using credit. Low appetite + generous policy is what makes
    # a limit look underused - we never decide how many that will be.
    credit_appetite = beta(1.7, 3.9, tilt.get("credit_appetite", 0.0))

    # Willingness and ability to pay in full each month.
    payment_discipline = beta(3.4, 2.0, tilt.get("payment_discipline", 0.0))
    # Score correlates with discipline but does not determine it.
    score_z = (scores - scores.mean()) / max(scores.std(), 1e-9)
    payment_discipline = np.clip(
        0.72 * payment_discipline + 0.28 * (0.5 + 0.17 * score_z), 0.01, 0.99)

    digital_fluency = beta(2.6, 2.2, tilt.get("digital_fluency", 0.0))
    problem_rate = np.clip(rng.gamma(1.7, 1.15, n), 0.05, 14.0)
    relationship_propensity = beta(1.8, 2.8)
    price_sensitivity = beta(2.4, 2.4)
    latent_satisfaction = beta(4.0, 1.9)

    persona = np.array([
        rng.choice(SPEND_PERSONAS, p=PERSONA_BY_SEGMENT.get(s, PERSONA_BY_SEGMENT["Retail"]))
        for s in segments])

    # Annual spend scale, lognormal, shifted by segment affluence.
    seg_scale = {"Private Banking": 1.95, "Premier": 1.45, "Mass Affluent": 1.15,
                 "Mass Market": 0.88, "Retail": 0.72, "Small Business": 1.60,
                 "Student": 0.42}
    base = rng.lognormal(mean=9.05, sigma=0.72, size=n)
    spend_level = base * np.array([seg_scale.get(s, 0.8) for s in segments])

    redemption_propensity = rng.choice(
        REDEMPTION_TYPES, n, p=profile.get("redemption_mix", [0.28, 0.34, 0.27, 0.11]))

    return pd.DataFrame({
        "credit_appetite": credit_appetite.round(4),
        "payment_discipline": payment_discipline.round(4),
        "digital_fluency": digital_fluency.round(4),
        "problem_rate": problem_rate.round(3),
        "relationship_propensity": relationship_propensity.round(4),
        "price_sensitivity": price_sensitivity.round(4),
        "latent_satisfaction": latent_satisfaction.round(4),
        "spend_persona": persona,
        "spend_level": spend_level.round(2),
        "redemption_propensity": redemption_propensity,
    })
