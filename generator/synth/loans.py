"""Personal and auto loans. Same CECL/capital treatment as cards, except the
commitment is fully drawn at origination, so no CCF question arises.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import policy as P
from .latents import true_default_hazard


def build_and_simulate(cust: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
                       rng: np.random.Generator, profile: dict):
    n = len(cust)
    holds_loan = rng.random(n) < np.clip(
        0.10 + 0.22 * lat["relationship_propensity"].to_numpy(), 0, 0.55)
    idx = np.where(holds_loan)[0]
    k = len(idx)
    if k == 0:
        return pd.DataFrame(), pd.DataFrame()

    is_auto = rng.random(k) < 0.62
    loan_type = np.where(is_auto, "auto", "personal")
    score = cust["Credit Score"].to_numpy()[idx]
    original = np.where(is_auto,
                        np.round(rng.uniform(12000, 48000, k), -2),
                        np.round(rng.uniform(3000, 25000, k), -2))
    term = np.where(is_auto, rng.choice([48, 60, 72], k, p=[.3, .5, .2]),
                    rng.choice([24, 36, 48, 60], k, p=[.2, .35, .30, .15]))
    apr = np.round(np.clip(
        (16.5 - (np.clip(score, 500, 850) - 500) / 350.0 * 10.5)
        + np.where(is_auto, -2.0, 3.5) + rng.normal(0, 0.7, k), 3.99, 29.99), 2)
    origination_idx = -rng.integers(0, 30, k)
    channel = np.where(
        is_auto,
        np.where(rng.random(k) < 0.78, "dealer_partner",
                np.where(rng.random(k) < 0.5, "branch", "digital")),
        np.where(rng.random(k) < 0.5, "branch", "digital"))

    acct_id = np.array([f"LOAN{i:07d}" for i in idx])
    accounts = pd.DataFrame({
        "Masked Customer Number": cust["Masked Customer Number"].to_numpy()[idx],
        "Masked Loan Account Number": acct_id,
        "Loan Type": loan_type,
        "Original Balance": original,
        "Term Months": term,
        "Purchase Rate (APR)": apr,
        "Origination Cycle Index": origination_idx,
        "Origination Channel": channel,
        "_latent_ix": idx,
        "_discipline": lat["payment_discipline"].to_numpy()[idx],
        "_appetite": lat["credit_appetite"].to_numpy()[idx],
    })

    n_cyc = len(cycles)
    hazard = true_default_hazard(accounts["_discipline"].to_numpy(),
                                 accounts["_appetite"].to_numpy())
    rows = []
    balance = original.copy()
    monthly_rate = apr / 100.0 / 12.0
    payment = balance * monthly_rate / (1 - (1 + monthly_rate) ** (-term))
    dpd = np.zeros(k, dtype=int)
    alive = np.ones(k, dtype=bool)
    for c in range(n_cyc):
        age_months = c - origination_idx
        live = alive & (age_months >= 0) & (age_months < term) & (balance > 1)
        if not live.any():
            continue
        interest = balance * monthly_rate
        miss = live & (rng.random(k) < hazard) & (dpd < 90)
        pay = np.where(miss, 0.0, np.minimum(payment, balance + interest))
        principal = np.clip(pay - interest, 0, balance)
        balance = np.where(live, np.maximum(balance - principal, 0), balance)
        dpd = np.where(live, np.where(miss, dpd + 30, np.maximum(dpd - 30, 0)), dpd)
        charged_off = live & (dpd >= 120)
        alive = alive & ~charged_off
        rows.append(pd.DataFrame({
            "Masked Customer Number": accounts["Masked Customer Number"].to_numpy()[live],
            "Masked Loan Account Number": accounts["Masked Loan Account Number"].to_numpy()[live],
            "Cycle Month": cycles[c],
            "Loan Type": accounts["Loan Type"].to_numpy()[live],
            "Current Balance": np.round(balance[live], 2),
            "Scheduled Payment": np.round(payment[live], 2),
            "Payment Made": np.round(pay[live], 2),
            "Interest Accrued": np.round(interest[live], 2),
            "Days Past Due": dpd[live],
            "Charged Off Indicator": charged_off[live],
        }))
    cyc = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return accounts.drop(columns=["_latent_ix", "_discipline", "_appetite"]), cyc
