"""Customers: demographics, geography, the bank's observables, and accounts.

The important causal choice lives here. The credit score is generated as a
NOISY OBSERVATION OF THE LATENTS, not as an independent draw that latents are
nudged toward. A bureau score is an estimate of repayment propensity, so this
is the causally correct direction - and it is what gives the book a real
charge-off gradient across score bands. Generating score independently and
correlating it weakly, as the previous engine did, produces a flat gradient
that no amount of tuning can fix without cheating.

Policy then reads the score. That is legitimate: it is reading a deliberately
degraded proxy, which is the real information asymmetry a bank operates under.

Under ECOA Regulation B a US issuer may not collect race or ethnicity for
credit cards, so none is generated. State and ZIP are generated instead, so
proxy-based fair lending testing can be demonstrated on realistic inputs.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import policy as P


def draw_demographics(n: int, rng: np.random.Generator, geo: pd.DataFrame,
                      profile: dict):
    age = np.clip(rng.gamma(5.2, 5.4, n) + 19, 19, 92).round().astype(int)
    w = geo["Population Weight"].to_numpy(dtype=float)
    idx = rng.choice(len(geo), n, p=w / w.sum())
    state = geo["State"].to_numpy()[idx]
    zip3 = geo["ZIP3"].to_numpy()[idx]
    zip5 = np.array([f"{z}{rng.integers(0, 100):02d}" for z in zip3])
    metro = geo["Metro Name"].to_numpy()[idx]
    return age, state, zip3, zip5, metro


def stated_income(lat: pd.DataFrame, age: np.ndarray,
                  rng: np.random.Generator) -> np.ndarray:
    """What the customer tells the bank. Noisy, and the bank cannot verify it."""
    base = np.exp(11.02 + 0.58 * lat["_factor_affluence"].to_numpy()
                  + 0.42 * rng.normal(0, 1, len(lat)))
    # Earnings profile over a working life.
    age_curve = np.clip(1.0 - 0.00055 * (age - 47) ** 2, 0.42, 1.0)
    inc = base * age_curve
    return np.round(np.clip(inc, 9000, 1500000), -2)


def credit_score(lat: pd.DataFrame, age: np.ndarray, tenure_years: np.ndarray,
                 rng: np.random.Generator, profile: dict) -> np.ndarray:
    """A noisy observation of repayment propensity.

    Correlation with payment_discipline lands near 0.75-0.80, which is strong
    but well short of recoverable. That is what a real bureau score is.
    """
    z = (1.10 * lat["_factor_reliability"].to_numpy()
         + 0.55 * (lat["payment_discipline"].to_numpy() - 0.5) * 2.0
         - 0.22 * (lat["credit_appetite"].to_numpy() - 0.35) * 2.0
         + 0.22 * lat["_factor_affluence"].to_numpy()
         + 0.030 * np.clip(tenure_years, 0, 25)
         + 0.008 * np.clip(age - 25, 0, 45))
    z = z + rng.normal(0, 0.62, len(lat)) + profile.get("score_shift_z", 0.0)
    score = 700 + 50.0 * z
    return np.clip(np.round(score), 480, 850).astype(int)


def hardship_and_scra(lat: pd.DataFrame, rng: np.random.Generator):
    """Hardship is caused by financial stress; SCRA is military service.

    Hardship must correlate with difficulty, otherwise the suppression test is
    meaningless - the engine would be asked to protect a group that looks
    exactly like everyone else.
    """
    n = len(lat)
    z = (-4.55 - 2.90 * (lat["payment_discipline"].to_numpy() - 0.5) * 2.0
         - 0.75 * lat["_factor_affluence"].to_numpy()
         + 0.30 * rng.normal(0, 1, n))
    p_hard = 1.0 / (1.0 + np.exp(-z))
    hardship = rng.random(n) < p_hard
    scra = rng.random(n) < 0.0062
    # An accommodation plan is the bank's response to hardship.
    accommodation = hardship & (rng.random(n) < 0.58)
    return hardship, scra, accommodation


def build_customers(n: int, lat: pd.DataFrame, geo: pd.DataFrame,
                    cycles: list[str], rng: np.random.Generator,
                    profile: dict) -> pd.DataFrame:
    age, state, zip3, zip5, metro = draw_demographics(n, rng, geo, profile)

    # Tenure with the bank, in years, before the observation window opens.
    tenure_years = np.clip(
        rng.gamma(1.8, 3.0, n) * (0.6 + 0.9 * lat["relationship_propensity"]),
        0.0, 38.0)
    tenure_years = np.minimum(tenure_years, np.clip(age - 18, 0, None))

    income = stated_income(lat, age, rng)
    is_business = (lat["spend_persona"].to_numpy() == "business") & (
        rng.random(n) < 0.55)
    segment = P.assign_segment(income, age, is_business, rng)
    score = credit_score(lat, age, tenure_years, rng, profile)
    hardship, scra, accommodation = hardship_and_scra(lat, rng)

    band = pd.cut(score, [0, 580, 620, 660, 700, 740, 780, 900],
                  labels=["<580", "580-619", "620-659", "660-699",
                          "700-739", "740-779", "780+"])

    cust_id = np.array([f"CUS{i:07d}" for i in range(n)])
    return pd.DataFrame({
        "Masked Customer Number": cust_id,
        "Segment": segment,
        "Age": age,
        "Stated Annual Income": income,
        "Credit Score": score,
        "Credit Score Band": band.astype(str),
        "Customer Tenure Years": np.round(tenure_years, 2),
        "State": state,
        "ZIP3": zip3,
        "ZIP Code": zip5,
        "Metro Name": metro,
        "Hardship Status": hardship,
        "Accommodation Plan": accommodation,
        "SCRA Flag": scra,
        "Provenance": f"synthetic:{profile.get('name', 'unknown')}",
    })


def build_card_accounts(cust: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
                        rng: np.random.Generator, profile: dict) -> pd.DataFrame:
    """One card account per customer at minimum; some customers hold two."""
    n = len(cust)
    score = cust["Credit Score"].to_numpy()
    segment = cust["Segment"].to_numpy()
    income = cust["Stated Annual Income"].to_numpy()

    product = P.assign_product(score, segment, rng)
    program = P.assign_program(product, rng)
    limit = P.origination_limit(score, product, segment, income, rng,
                                profile.get("limit_generosity", 1.0))
    apr_contract = P.contractual_apr(score, product, rng)

    # Expected annual reward value, used only by a fee policy that chooses to
    # align the fee to it. Computed from the published program rule, not a latent.
    exp_reward = np.where(
        np.isin(program, ["PREMIUM_TRAVEL_5X", "TRAVEL_REWARDS_3X",
                          "BUSINESS_CATEGORY_4X"]), 320.0,
        np.where(program == "EVERYDAY_3X_GROCERY_GAS", 210.0,
                 np.where(program == "CORE_CASHBACK_1_5", 120.0, 30.0)))
    fee = P.annual_fee(product, program, rng,
                       profile.get("fee_aligned_to_reward", False), exp_reward)

    # Account open date: most accounts predate the window, some open inside it.
    n_cycles = len(cycles)
    opened_before = rng.random(n) < 0.82
    months_before = np.where(
        opened_before,
        -np.clip(rng.gamma(2.2, 14.0, n), 1, 240).round().astype(int),
        rng.integers(0, max(n_cycles - 3, 1), n))
    open_idx = months_before

    acct_id = np.array([f"ACC{i:07d}" for i in range(n)])
    return pd.DataFrame({
        "Masked Customer Number": cust["Masked Customer Number"].to_numpy(),
        "Masked Account Number": acct_id,
        "Product Tier": product,
        "Reward Program Code": program,
        "Original Credit Limit": limit,
        "Current Credit Limit": limit,
        "Contractual Purchase APR": apr_contract,
        "Annual Fee": fee,
        "Account Open Cycle Index": open_idx,
        "Unconditionally Cancellable": True,
        "Over Limit Opt In": rng.random(n) < 0.031,
        "Acquisition Channel": lat["channel_affinity"].to_numpy(),
    })
