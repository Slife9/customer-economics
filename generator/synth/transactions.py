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


def _reward_behaviour(accounts: pd.DataFrame, lat: pd.DataFrame, mcc: pd.DataFrame,
                      pmat: np.ndarray, persona_i: np.ndarray, open_idx: np.ndarray,
                      n_cyc: int, b: dict, rng: np.random.Generator):
    """Profile-only reward behaviour (the `reward_stress` profile). Never
    called for a profile without `reward_behaviour`, so those profiles' draws
    are untouched. Returns the MCC table actually drawn from, one probability
    vector per spending group, each account's group, a spend multiplier, and
    the sign-up bonus chasers.

    - Optimizers: high-spend accounts on a bonus programme concentrate spend
      in that programme's bonus categories.
    - Quasi-cash users: part of the spend goes to cash-like / processor MCCs
      (wallet loads, money orders, rent) that earn full points at low
      interchange.
    - Bonus chasers: accounts opened inside the window spend hard in the
      3-month offer window, then go dormant.
    """
    n = len(accounts)
    program = accounts["Reward Program Code"].to_numpy()
    extra = b.get("quasi_mcc")
    mcc_all = mcc if extra is None else pd.concat([mcc, extra], ignore_index=True)
    pad = len(mcc_all) - len(mcc)
    vecs = [np.concatenate([pmat[p], np.zeros(pad)]) for p in range(len(pmat))]
    group = persona_i.copy()
    keyed: dict = {}

    def group_of(key, vec):
        if key not in keyed:
            keyed[key] = len(vecs)
            vecs.append(vec / vec.sum())
        return keyed[key]

    spend_rank = np.argsort(np.argsort(lat["spend_level"].to_numpy())) / max(n - 1, 1)
    u = rng.random((n, 3))  # fixed-size draws: optimizer, quasi-cash, chaser
    uplift = np.ones(n)

    cats = mcc_all["Reward Category"].to_numpy()
    within = np.where(mcc_all["Long Tail"].to_numpy() == 1, 0.35, 1.0)
    within[len(mcc):] = 0.0  # bonus categories never point at quasi-cash rows
    bonus_cats = b.get("optimizer_bonus_categories", {})
    opt = (np.isin(program, list(bonus_cats)) & (spend_rank >= b.get("optimizer_min_spend_rank", 1.0))
           & (u[:, 0] < b.get("optimizer_share", 0.0)))
    c = b.get("optimizer_bonus_concentration", 0.0)
    for i in np.where(opt)[0]:
        bv = np.where(np.isin(cats, bonus_cats[program[i]]), within, 0.0)
        group[i] = group_of(("opt", persona_i[i], program[i]),
                            (1 - c) * vecs[persona_i[i]] + c * bv / bv.sum())
    uplift[opt] = b.get("optimizer_spend_uplift", 1.0)

    no_reward = set(b.get("no_reward_programs", []))
    qc = (~opt & ~np.isin(program, list(no_reward)) & (u[:, 1] < b.get("quasi_cash_share", 0.0)))
    if extra is not None and qc.any():
        w = b.get("quasi_cash_mcc_weights", {})
        qv = np.concatenate([np.zeros(len(mcc)),
                             np.array([w.get(str(m), 0.0) for m in extra["MCC"]])])
        q = b.get("quasi_cash_count_share", 0.0)
        for i in np.where(qc)[0]:
            group[i] = group_of(("qc", persona_i[i]), (1 - q) * vecs[persona_i[i]] + q * qv / qv.sum())
        uplift[qc] = b.get("quasi_cash_spend_uplift", 1.0)

    chaser = (~opt & ~qc & np.isin(program, b.get("bonus_eligible_programs", []))
              & (open_idx >= 0) & (open_idx <= n_cyc - 6) & (u[:, 2] < b.get("bonus_chaser_share", 0.0)))
    return mcc_all, np.vstack(vecs), group, uplift, chaser


def generate(accounts: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
             open_idx: np.ndarray, closed_idx: np.ndarray,
             mcc: pd.DataFrame, card: pd.DataFrame,
             rng: np.random.Generator, behaviour: dict | None = None) -> pd.DataFrame:
    n_acct, n_cyc = len(accounts), len(cycles)
    personas, pmat = _persona_mcc_matrix(mcc)
    p_index = {p: i for i, p in enumerate(personas)}
    persona_i = np.array([p_index[p] for p in lat["spend_persona"]])
    if behaviour is not None:
        mcc, gvec, group, uplift, chaser = _reward_behaviour(
            accounts, lat, mcc, pmat, persona_i, open_idx, n_cyc, behaviour, rng)

    # ---- monthly spend intensity -------------------------------------
    base_monthly = lat["spend_level"].to_numpy() / 12.0
    # Persistent multiplier: realized circumstances the latent does not capture.
    persistent = np.exp(rng.normal(0.0, 0.45, n_acct))
    months = np.array([int(c.split("-")[1]) for c in cycles])
    seas = SEASONALITY[months - 1]
    shock = np.exp(rng.normal(0.0, 0.28, (n_acct, n_cyc)))
    intensity = base_monthly[:, None] * persistent[:, None] * seas[None, :] * shock
    if behaviour is not None:
        intensity = intensity * uplift[:, None]

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
    pre_dormancy = intensity
    intensity = np.where(dormant_mask, 0.0, intensity)
    if behaviour is not None and chaser.any():
        # A chaser spends hard in the offer window even if the generic
        # dormancy draw above would have silenced the card, then fades.
        o = open_idx[:, None]
        window = chaser[:, None] & (ci >= o) & (ci < o + 3)
        after = chaser[:, None] & (ci >= o + 3)
        intensity = np.where(window, pre_dormancy * behaviour.get("bonus_window_spend_boost", 1.0), intensity)
        intensity = np.where(after, intensity * behaviour.get("bonus_after_window_spend_factor", 1.0), intensity)

    # ---- transaction counts -------------------------------------------
    if behaviour is not None:
        mean_ticket = gvec[group] @ mcc["Ticket Mean USD"].to_numpy()
    else:
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
    if behaviour is not None:
        tx_group = group[tx_acct]
        for gi in range(len(gvec)):
            m = tx_group == gi
            k = int(m.sum())
            if k:
                tx_mcc_i[m] = rng.choice(len(mcc), k, p=gvec[gi])
    else:
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
    # Vectorized equivalent of [f"{cycles[c]}-{d:02d}" for c, d in zip(tx_cyc, day)] -
    # identical output for identical input, but the list-comprehension version
    # materializes `total` individual Python str objects before np.array() can
    # even start, which is fine at demo scale (a few million rows) but reliably
    # MemoryErrors once `total` reaches the tens-to-hundreds of millions a
    # 500,000-customer x 36-cycle run produces. Gathering from small lookup
    # tables never materializes a Python list, and - unlike day.astype(str),
    # which sizes every string for the largest POSSIBLE int64 (21 characters)
    # rather than the 1-2 digits a day-of-month actually needs - never
    # allocates wider strings than the 28 real values require.
    day_lookup = np.array([f"{d:02d}" for d in range(1, 29)])
    day_str = day_lookup[day - 1]
    tx_date = np.char.add(np.char.add(np.array(cycles)[tx_cyc], "-"), day_str)
    post_lag = rng.integers(0, 3, total)

    # copy=False: pandas' default DataFrame construction EAGERLY consolidates
    # every same-dtype column into one combined block, via np.vstack - here
    # that means all 9 of this frame's text columns (pandas stores any
    # string column as dtype=object internally, regardless of the input
    # array's own dtype) get vstacked into a single (9, total) object array.
    # At demo scale that is fine; at a 100,000-customer x 36-cycle scale
    # (~22.6M transaction rows) that single allocation is >1.5 GiB and
    # reliably MemoryErrors even when the 9 columns individually would fit.
    # copy=False skips that eager consolidation (safe here - every array
    # below is freshly computed, not a shared/mutable reference the caller
    # keeps using), keeping the 9 columns as separate smaller allocations
    # instead of doubling up during one giant merge. Verified byte-identical
    # output at demo scale; see also the day_lookup/tx_date fix above and
    # the two prior fixes in this same function for the same class of issue.
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
    }, copy=False)
