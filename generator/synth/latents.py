"""Latent customer traits. THE CAUSES.

This module must never import from policy.py, and policy.py must never import
from here. A real bank cannot observe credit appetite, which is exactly why it
grants limits people never use.

Latents are written to Latent_Ground_Truth.csv and are never joined into a
published table. Nothing here may be named after anything the analytical
engine reports.

Structure: three correlated factors (affluence, reliability, engagement) sit
behind the twelve published latents. Acquisition channel is drawn first, as a
population characteristic, and the factors are conditioned on it - so channels
genuinely differ in customer quality rather than being relabeled noise.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SPEND_PERSONAS = ["travel", "grocery", "everyday", "business", "online"]
REDEMPTION_TYPES = ["fast", "steady", "hoarder", "never"]
CHANNELS = ["branch", "digital", "aggregator", "partner", "direct_mail"]

# Channel mix of the acquired population.
CHANNEL_MIX = [0.20, 0.32, 0.20, 0.14, 0.14]

# How each channel shifts the three latent factors, in standard deviations.
# Aggregators draw price-sensitive thin-file customers; branch draws
# relationship-prone ones. The value gap between channels then emerges.
CHANNEL_FACTOR_SHIFT = {
    #            affluence  reliability  engagement  price_sensitivity
    "branch":      (+0.22,      +0.30,      -0.35,      -0.30),
    "digital":     (+0.10,      +0.06,      +0.62,      +0.05),
    "aggregator":  (-0.34,      -0.40,      +0.30,      +0.75),
    "partner":     (+0.16,      +0.10,      +0.10,      -0.10),
    "direct_mail": (-0.18,      -0.12,      -0.48,      +0.12),
}

CHANNEL_RELATIONSHIP_SHIFT = {
    "branch": +0.55, "digital": -0.05, "aggregator": -0.60,
    "partner": +0.20, "direct_mail": -0.15,
}

PERSONA_BY_AFFLUENCE = {
    # persona weights at low / mid / high affluence
    "low":  [0.04, 0.32, 0.38, 0.05, 0.21],
    "mid":  [0.14, 0.24, 0.31, 0.11, 0.20],
    "high": [0.30, 0.13, 0.20, 0.19, 0.18],
}


def _logistic(z):
    return 1.0 / (1.0 + np.exp(-z))


def draw_latents(n: int, age: np.ndarray, rng: np.random.Generator,
                 profile: dict) -> pd.DataFrame:
    """One latent vector per customer.

    `profile` may shift the *population* being acquired (used by the portfolio
    variants). It never sets an outcome. The negative control does NOT tilt
    anything here: a clean book must be the same customers meeting a
    better-run bank, otherwise the comparison measures the population.
    """
    tilt = profile.get("latent_tilt", {})
    chan_mix = np.array(profile.get("channel_mix", CHANNEL_MIX), dtype=float)
    chan_mix = chan_mix / chan_mix.sum()

    channel = rng.choice(CHANNELS, n, p=chan_mix)

    aff_shift = np.array([CHANNEL_FACTOR_SHIFT[c][0] for c in channel])
    rel_shift = np.array([CHANNEL_FACTOR_SHIFT[c][1] for c in channel])
    eng_shift = np.array([CHANNEL_FACTOR_SHIFT[c][2] for c in channel])
    prc_shift = np.array([CHANNEL_FACTOR_SHIFT[c][3] for c in channel])
    rlp_shift = np.array([CHANNEL_RELATIONSHIP_SHIFT[c] for c in channel])

    # ---- three correlated latent factors -------------------------------
    f_affluence = rng.normal(0, 1, n) + aff_shift + tilt.get("affluence", 0.0)
    f_reliability = (0.30 * f_affluence + 0.954 * rng.normal(0, 1, n)
                     + rel_shift + tilt.get("reliability", 0.0))
    # Digital fluency falls with age; engagement is otherwise idiosyncratic.
    age_z = (age - 48.0) / 17.0
    f_engagement = (rng.normal(0, 1, n) + eng_shift - 0.62 * age_z
                    + tilt.get("engagement", 0.0))

    # ---- the twelve published latents ----------------------------------
    # Appetite to draw on a line. Falls with affluence and reliability: people
    # with money and discipline borrow a smaller share of what they are given.
    credit_appetite = _logistic(
        -0.55 - 0.42 * f_affluence - 0.30 * f_reliability
        + 0.85 * rng.normal(0, 1, n) + tilt.get("credit_appetite", 0.0))

    payment_discipline = _logistic(
        0.45 + 0.95 * f_reliability + 0.55 * rng.normal(0, 1, n)
        + tilt.get("payment_discipline", 0.0))

    digital_fluency = _logistic(
        0.10 + 1.05 * f_engagement + 0.50 * rng.normal(0, 1, n))

    # Events needing service per year. Rises when engagement is low and when
    # the customer is financially stretched.
    problem_rate = np.clip(
        rng.gamma(1.9, 1.05, n) * np.exp(-0.18 * f_reliability
                                         - 0.10 * f_engagement),
        0.05, 18.0)

    relationship_propensity = _logistic(
        -0.25 + 0.55 * f_affluence + rlp_shift + 0.80 * rng.normal(0, 1, n))

    price_sensitivity = _logistic(
        0.05 - 0.38 * f_affluence + prc_shift + 0.90 * rng.normal(0, 1, n))

    latent_satisfaction = _logistic(
        0.95 + 0.25 * f_affluence + 0.70 * rng.normal(0, 1, n))

    deposit_propensity = _logistic(
        -0.30 + 0.88 * f_affluence + 0.22 * f_reliability
        + 0.70 * rng.normal(0, 1, n))

    # Spend scale. This is a PROPENSITY, not realized spend: realized spend
    # carries a large persistent multiplier plus cycle shocks (transactions.py)
    # so that spend_level is not readable straight off an annual spend column.
    spend_level = np.exp(9.05 + 0.62 * f_affluence + 0.55 * rng.normal(0, 1, n))

    # Persona mix shifts with affluence rather than with the bank's segment,
    # because the bank's segment is a consequence, not a cause.
    aff_rank = np.argsort(np.argsort(f_affluence)) / max(n - 1, 1)
    persona = np.empty(n, dtype=object)
    for i, r in enumerate(aff_rank):
        key = "low" if r < 0.33 else ("mid" if r < 0.75 else "high")
        persona[i] = rng.choice(SPEND_PERSONAS, p=PERSONA_BY_AFFLUENCE[key])

    red_mix = profile.get("redemption_mix", [0.26, 0.33, 0.29, 0.12])
    redemption_propensity = rng.choice(REDEMPTION_TYPES, n,
                                       p=np.array(red_mix) / np.sum(red_mix))

    return pd.DataFrame({
        "credit_appetite": credit_appetite.round(4),
        "payment_discipline": payment_discipline.round(4),
        "digital_fluency": digital_fluency.round(4),
        "problem_rate": problem_rate.round(3),
        "redemption_propensity": redemption_propensity,
        "relationship_propensity": relationship_propensity.round(4),
        "price_sensitivity": price_sensitivity.round(4),
        "latent_satisfaction": latent_satisfaction.round(4),
        "spend_persona": persona,
        "spend_level": spend_level.round(2),
        "deposit_propensity": deposit_propensity.round(4),
        "channel_affinity": channel,
        # factors retained in ground truth only, for counterfactual scoring
        "_factor_affluence": f_affluence.round(4),
        "_factor_reliability": f_reliability.round(4),
        "_factor_engagement": f_engagement.round(4),
    })


def true_default_hazard(payment_discipline: np.ndarray,
                        credit_appetite: np.ndarray) -> np.ndarray:
    """The TRUE monthly hazard of entering delinquency.

    This is a cause. The bank never sees it - risk.py estimates PD from
    observables with model error, and the truth is written to ground truth so
    the estimate can be scored against it.
    """
    # Calibrated so the monthly entry hazard runs from roughly 4.5% at
    # payment_discipline 0.35 to 0.12% at 0.80, which lands the delinquency
    # gradient across score bands inside the 15-40x range real US books show.
    z = -1.53 - 5.20 * payment_discipline + 0.90 * (credit_appetite - 0.40)
    return _logistic(z)
