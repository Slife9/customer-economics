"""Transactions: merchant mix from persona, interchange from the rate card.

Interchange is LOOKED UP from the contractual schedule by (product tier,
interchange category). It is never drawn from a distribution. That is exactly
what makes a booked-below-entitled rate detectable.

Realized spend deliberately carries a large persistent multiplier and monthly
shocks on top of the spend_level latent, so that annual spend is not a direct
read of the latent.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# Weights over reward category for each spend persona.
PERSONA_CATEGORY_WEIGHTS = {
    "travel":   {"travel": .28, "dining": .17, "retail": .11, "online": .08,
                 "grocery": .09, "gas": .05, "utilities": .05, "healthcare": .04,
                 "entertainment": .04, "insurance": .02, "other": .02,
                 "business": .02, "drugstore": .01, "home": .01, "education": .01,
                 "auto": .00},
    "grocery":  {"grocery": .30, "gas": .10, "dining": .10, "retail": .12,
                 "online": .07, "utilities": .07, "healthcare": .05, "travel": .04,
                 "insurance": .03, "drugstore": .03, "entertainment": .03,
                 "other": .02, "business": .01, "home": .01, "education": .01,
                 "auto": .01},
    "everyday": {"grocery": .18, "retail": .16, "dining": .13, "gas": .12,
                 "online": .09, "utilities": .07, "healthcare": .05, "travel": .05,
                 "entertainment": .04, "insurance": .03, "drugstore": .02,
                 "other": .02, "business": .01, "home": .01, "education": .01,
                 "auto": .01},
    "business": {"business": .26, "travel": .14, "dining": .12, "online": .10,
                 "gas": .09, "retail": .08, "utilities": .05, "grocery": .05,
                 "insurance": .03, "healthcare": .02, "entertainment": .02,
                 "other": .02, "home": .01, "auto": .01, "education": .00,
                 "drugstore": .00},
    "online":   {"online": .31, "dining": .11, "grocery": .10, "retail": .10,
                 "entertainment": .07, "travel": .07, "utilities": .06,
                 "gas": .05, "business": .03, "healthcare": .03, "insurance": .02,
                 "other": .02, "drugstore": .01, "home": .01, "education": .01,
                 "auto": .00},
}

# Seasonal index by calendar month, 1-12. December lifts, February dips.
SEASONALITY = np.array([0.93, 0.88, 0.97, 0.97, 1.01, 1.00,
                        1.02, 1.03, 0.98, 1.01, 1.06, 1.24])


def load_config(cfg_dir):
    mcc = pd.read_csv(cfg_dir / "mcc_catalog.csv", dtype={"MCC": str})
    card = pd.read_csv(cfg_dir / "interchange_rate_card.csv")
    return mcc, card


def _persona_mcc_matrix(mcc: pd.DataFrame):
    """Probability over every MCC, per persona."""
    personas = list(PERSONA_CATEGORY_WEIGHTS)
    cats = mcc["Reward Category"].to_numpy()
    # Within a category, long-tail merchants carry a smaller share.
    within = np.where(mcc["Long Tail"].to_numpy() == 1, 0.35, 1.0)
    mat = np.zeros((len(personas), len(mcc)))
    for pi, p in enumerate(personas):
        w = PERSONA_CATEGORY_WEIGHTS[p]
        raw = np.array([w.get(c, 0.0) for c in cats]) * within
        for c in set(cats):
            m = cats == c
            s = raw[m].sum()
            if s > 0:
                raw[m] = raw[m] / s * w.get(c, 0.0)
        mat[pi] = raw / raw.sum()
    return personas, mat


def generate(accounts: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
             open_idx: np.ndarray, closed_idx: np.ndarray,
             mcc: pd.DataFrame, card: pd.DataFrame,
             rng: np.random.Generator) -> pd.DataFrame:
    n_acct, n_cyc = len(accounts), len(cycles)
    personas, pmat = _persona_mcc_matrix(mcc)
    p_index = {p: i for i, p in enumerate(personas)}
    persona_i = np.array([p_index[p] for p in lat["spend_persona"]])

    # ---- monthly spend intensity -------------------------------------
    base_monthly = lat["spend_level"].to_numpy() / 12.0
    # Persistent multiplier: realized circumstances the latent does not capture.
    persistent = np.exp(rng.normal(0.0, 0.45, n_acct))
    months = np.array([int(c.split("-")[1]) for c in cycles])
    seas = SEASONALITY[months - 1]
    shock = np.exp(rng.normal(0.0, 0.28, (n_acct, n_cyc)))
    intensity = base_monthly[:, None] * persistent[:, None] * seas[None, :] * shock

    # Account must be open and not yet closed in that cycle.
    ci = np.arange(n_cyc)[None, :]
    live = (ci >= open_idx[:, None]) & (ci < closed_idx[:, None])
    intensity = np.where(live, intensity, 0.0)

    # Dormancy: the account stays open but stops being used - a real and
    # common outcome (a card acquired, tried, then displaced by another
    # primary card) distinct from closure. Low relationship_propensity and
    # digital_fluency make a customer more likely to let a card go quiet.
    dormancy_p = np.clip(
        0.66 - 0.46 * lat["relationship_propensity"].to_numpy()
        - 0.12 * lat["digital_fluency"].to_numpy(), 0.08, 0.78)
    goes_dormant = rng.random(n_acct) < dormancy_p
    onset = np.where(goes_dormant,
                     np.maximum(open_idx, 0) + rng.integers(2, 13, n_acct),
                     10 ** 6)
    dormant_mask = ci >= onset[:, None]
    intensity = np.where(dormant_mask, 0.0, intensity)

    # ---- transaction counts -------------------------------------------
    mean_ticket = np.array([
        (mcc["Ticket Mean USD"].to_numpy() * pmat[pi]).sum() for pi in persona_i])
    lam = np.clip(intensity / mean_ticket[:, None], 0.0, 260.0)
    counts = rng.poisson(lam)
    total = int(counts.sum())
    if total == 0:
        return pd.DataFrame()

    acct_ix = np.repeat(np.arange(n_acct)[:, None], n_cyc, axis=1).ravel()
    cyc_ix = np.tile(np.arange(n_cyc), n_acct)
    flat = counts.ravel()
    tx_acct = np.repeat(acct_ix, flat)
    tx_cyc = np.repeat(cyc_ix, flat)

    # ---- merchant draw, grouped by persona for speed -------------------
    tx_mcc_i = np.empty(total, dtype=np.int64)
    tx_persona = persona_i[tx_acct]
    for pi in range(len(personas)):
        m = tx_persona == pi
        k = int(m.sum())
        if k:
            tx_mcc_i[m] = rng.choice(len(mcc), k, p=pmat[pi])

    ticket_mean = mcc["Ticket Mean USD"].to_numpy()[tx_mcc_i]
    ticket_cv = mcc["Ticket CV"].to_numpy()[tx_mcc_i]
    sigma = np.sqrt(np.log1p(ticket_cv ** 2))
    mu = np.log(ticket_mean) - 0.5 * sigma ** 2
    # Spend scale shifts ticket size as well as frequency.
    scale = np.clip(persistent[tx_acct] ** 0.35, 0.45, 3.0)
    amount = np.round(np.exp(rng.normal(mu, sigma)) * scale, 2)
    amount = np.clip(amount, 1.00, 45000.0)

    # ---- interchange looked up from the rate card ----------------------
    tier = accounts["Product Tier"].to_numpy()[tx_acct]
    icat = mcc["Interchange Category"].to_numpy()[tx_mcc_i]
    key = pd.MultiIndex.from_arrays([card["Product Tier"], card["Interchange Category"]])
    rate_lookup = pd.Series(card["Interchange Rate Percent"].to_numpy(), index=key)
    fixed_lookup = pd.Series(card["Interchange Fixed Fee USD"].to_numpy(), index=key)
    want = pd.MultiIndex.from_arrays([tier, icat])
    rate = rate_lookup.reindex(want).to_numpy()
    fixed = fixed_lookup.reindex(want).to_numpy()
    if np.isnan(rate).any():
        missing = set(zip(tier[np.isnan(rate)], icat[np.isnan(rate)]))
        raise ValueError(f"rate card does not cover: {list(missing)[:5]}")
    interchange = np.round(amount * rate / 100.0 + fixed, 4)

    cash_advance = rng.random(total) < 0.006
    foreign = rng.random(total) < 0.021
    disputed = rng.random(total) < 0.0035

    day = rng.integers(1, 29, total)
    tx_date = np.array([f"{cycles[c]}-{d:02d}" for c, d in zip(tx_cyc, day)])
    post_lag = rng.integers(0, 3, total)

    return pd.DataFrame({
        "Masked Customer Number": accounts["Masked Customer Number"].to_numpy()[tx_acct],
        "Masked Account Number": accounts["Masked Account Number"].to_numpy()[tx_acct],
        "Cycle Month": np.array(cycles)[tx_cyc],
        "Transaction Date": tx_date,
        "Posting Day Lag": post_lag,
        "Amount Type": "debit",
        "Transaction Amount": amount,
        "Merchant Category Code (MCC)": mcc["MCC"].to_numpy()[tx_mcc_i],
        "Merchant Category Description":
            mcc["Merchant Category Description"].to_numpy()[tx_mcc_i],
        "Interchange Category": icat,
        "Reward Category": mcc["Reward Category"].to_numpy()[tx_mcc_i],
        "Interchange Rate Applied Percent": rate,
        "Interchange Fixed Fee Applied": fixed,
        "Interchange Earned": interchange,
        "Cash Advance Indicator": cash_advance,
        "Foreign Transaction Indicator": foreign,
        "FX Markup Amount": np.where(foreign, np.round(amount * 0.03, 2), 0.0),
        "Disputed Indicator": disputed,
        "_acct_ix": tx_acct,
        "_cycle_ix": tx_cyc,
    })
