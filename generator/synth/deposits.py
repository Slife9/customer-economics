"""Deposit accounts: relationship breadth, funded from deposit_propensity alone.

Deposit revenue is the FTP credit on the balance, not a customer-paid rate.
Balance stability comes from deposit_propensity; seasonality and a payroll
cycle are generated so balances are not flat lines.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ACCOUNT_TYPES = ["checking", "savings", "money_market", "cd"]


def build_accounts(cust: pd.DataFrame, lat: pd.DataFrame, n_cycles: int,
                   rng: np.random.Generator, profile: dict) -> pd.DataFrame:
    n = len(cust)
    has_deposit = rng.random(n) < np.clip(
        0.30 + 0.55 * lat["deposit_propensity"].to_numpy(), 0, 0.94)
    idx = np.where(has_deposit)[0]
    k = len(idx)
    if k == 0:
        return pd.DataFrame()

    typ = rng.choice(ACCOUNT_TYPES, k, p=[0.52, 0.30, 0.12, 0.06])
    direct_deposit = rng.random(k) < np.clip(
        0.35 + 0.5 * lat["deposit_propensity"].to_numpy()[idx], 0, 0.92)

    # Most deposit relationships predate the observation window. A share are a
    # genuine cross-sell event happening DURING the window - more likely for
    # customers with higher relationship_propensity, which is what lets the
    # Product Holding Timeline show a real card-then-deposit sequence rather
    # than every relationship starting at the same time.
    rel_prop = lat["relationship_propensity"].to_numpy()[idx]
    is_cross_sell = rng.random(k) < np.clip(0.15 + 0.35 * rel_prop, 0.05, 0.65)
    open_idx = np.where(
        is_cross_sell,
        rng.integers(0, max(n_cycles - 1, 1), k),
        -np.clip(rng.gamma(2.0, 16.0, k), 1, 300).round().astype(int))

    return pd.DataFrame({
        "Masked Customer Number": cust["Masked Customer Number"].to_numpy()[idx],
        "Masked Deposit Account Number": [f"DEP{i:07d}" for i in idx],
        "Deposit Account Open Cycle Index": open_idx,
        "Deposit Account Type": typ,
        "Direct Deposit Indicator": direct_deposit,
        "_latent_ix": idx,
    })


def simulate_cycles(dep: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
                    ftp_curve: pd.DataFrame, stated_income: np.ndarray,
                    rng: np.random.Generator) -> pd.DataFrame:
    if not len(dep):
        return pd.DataFrame()
    n, n_cyc = len(dep), len(cycles)
    idx = dep["_latent_ix"].to_numpy()
    propensity = lat["deposit_propensity"].to_numpy()[idx]

    target_bal = np.exp(8.95 + 1.55 * propensity) * (
        1.0 + 0.35 * (stated_income[idx] / 90000.0 - 1.0).clip(-0.6, 3.0))
    is_cd = (dep["Deposit Account Type"] == "cd").to_numpy()
    target_bal = np.where(is_cd, target_bal * 2.2, target_bal)

    months = np.array([int(c.split("-")[1]) for c in cycles])
    payroll_boost = np.where(np.isin(months, [1, 4, 7, 10]), 1.04, 1.0)
    seasonal = 1.0 + 0.05 * np.sin(2 * np.pi * (months - 1) / 12.0)

    ftp_1m = ftp_curve[ftp_curve["Tenor Months"] == 1].set_index(
        "Cycle Month")["Rate Percent"]

    ending = np.zeros((n, n_cyc))
    bal = target_bal * rng.uniform(0.7, 1.1, n)
    for c in range(n_cyc):
        drift = rng.normal(0, 0.05, n)
        bal = np.clip(bal * (0.90 + 0.10 * (target_bal / np.maximum(bal, 1))
                             + drift) * seasonal[c] * payroll_boost[c], 0, None)
        ending[:, c] = bal

    open_idx = dep["Deposit Account Open Cycle Index"].to_numpy()
    rows = []
    for c, cm in enumerate(cycles):
        live = c >= open_idx
        credit_rate = float(ftp_1m.get(cm, 4.5))
        pay_rate = np.where(is_cd, credit_rate * 0.72,
                            np.where(dep["Deposit Account Type"].to_numpy() == "savings",
                                     credit_rate * 0.22, credit_rate * 0.04))
        interest_paid = ending[:, c] * pay_rate / 100.0 / 12.0
        ftp_credit = ending[:, c] * credit_rate / 100.0 / 12.0
        nsf = (rng.random(n) < np.clip(0.02 - 0.015 * propensity, 0.001, 0.05)).astype(int)
        maintenance_fee = np.where(
            (ending[:, c] < 1500) & (dep["Deposit Account Type"].to_numpy() == "checking")
            & (rng.random(n) < 0.4), 12.0, 0.0)
        txn_count = rng.poisson(np.clip(6 + 14 * propensity, 1, 40))
        if not live.any():
            continue
        k = np.where(live)[0]
        rows.append(pd.DataFrame({
            "Masked Customer Number": dep["Masked Customer Number"].to_numpy()[k],
            "Masked Deposit Account Number": dep["Masked Deposit Account Number"].to_numpy()[k],
            "Cycle Month": cm,
            "Deposit Account Type": dep["Deposit Account Type"].to_numpy()[k],
            "Ending Balance": np.round(ending[k, c], 2),
            "Average Daily Balance": np.round(ending[k, c] * rng.uniform(0.92, 1.0, len(k)), 2),
            "Interest Paid": np.round(interest_paid[k], 2),
            "FTP Credit Rate Percent": credit_rate,
            "FTP Credit Value Monthly": np.round(ftp_credit[k], 2),
            "Maintenance Fee Charged": maintenance_fee[k],
            "NSF Fee Count": nsf[k],
            "NSF Fee Amount": nsf[k] * 32.0,
            "Transaction Count": txn_count[k],
            "Direct Deposit Indicator": dep["Direct Deposit Indicator"].to_numpy()[k],
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
