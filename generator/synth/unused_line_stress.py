"""Unused-line stress book: profile-only hooks for `unused_line_stress`.

SYNTHETIC STRESS DATA. A deliberately skewed book tuned so the workbook's
screen (unprofitable, utilisation < 30%, unused line >= $5,000) finds a
population shaped like the Unused Line RWA Scenario Model's: Credit-
Deteriorating ~9%, Relationship ~11%, Dormant ~32%, Sock-Drawer ~22%,
Low-Utilization Transactors ~27%, about -$97 per screened account. It is not a
realistic US book and must never be shown as the illustrative bank's headline
without that label.

Mechanism: each customer is given one workbook ARCHETYPE (or `standard`,
untouched). The archetype sets the population being acquired - latent traits,
segment, credit line, account age - and when the card is used. Everything
else (balances, payments, delinquency, PD, costs, profit) still emerges from
the generator's own causal logic; no outcome is written directly.

Only build() calls these functions, and only when the profile carries
`unused_line_archetypes`, so every other profile's draws and outputs are
unchanged. Every value below is `estimated - source: Unused Line RWA
Scenario Model` (its Assumptions sheet), tuned on the 10k stress book.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SOURCE = "estimated - source: Unused Line RWA Scenario Model"

# Workbook targets at the end of the window, per archetype. `line` is the
# credit line, `spend` annual card spend, `discipline` / `appetite` the
# payment-discipline and credit-appetite latents, `reliability` /
# `affluence` the factor means (they drive the credit score, income and
# segment), `activity` how the card is used, `persona` (optional) the
# spending mix (everyday spending has smaller, steadier tickets), `spend_sd`
# (optional) the spread of annual spend, `product` (optional) the product
# tier, reward programme and annual fee the workbook's segment carries,
# `monthly_budget` (optional) the cap on a month's spend as a multiple of the
# card's usual month.
ARCHETYPES = {
    "dormant": {
        "line": 7000, "spend": 3000, "discipline": 0.90, "appetite": 0.10,
        "reliability": -0.4, "affluence": 0.0, "activity": "dormant",
        "keep_deposits": False,
    },
    "sock_drawer": {
        "line": 10000, "spend": 1500, "discipline": 0.60, "appetite": 0.25,
        "reliability": -0.1, "affluence": 0.0, "activity": "occasional", "spend_sd": 0.20,
        "keep_deposits": False,
    },
    "transactor": {
        "line": 20500, "spend": 23000, "discipline": 0.95, "appetite": 0.08,
        "reliability": 0.5, "affluence": 0.4, "activity": "all", "persona": "everyday",
        "spend_sd": 0.25, "monthly_budget": 1.6,
        "keep_deposits": False,
    },
    "deteriorating": {
        "line": 12000, "spend": 2500, "discipline": 0.50, "appetite": 0.50,
        "reliability": -1.3, "affluence": -0.2, "activity": "all",
        "keep_deposits": False,
    },
    "relationship": {
        "line": 35000, "spend": 30000, "discipline": 0.72, "appetite": 0.20,
        "reliability": 0.8, "affluence": 1.8, "activity": "all", "persona": "travel",
        "keep_deposits": True,
        "product": ("World Elite", "PREMIUM_TRAVEL_5X", 95.0),
    },
}
LATENT_SD = 0.05            # spread around the discipline / appetite targets
FACTOR_SD = 0.35            # spread around the factor means
LINE_SD = 0.25              # lognormal spread of the credit line
SPEND_SD = 0.35             # lognormal spread of annual spend
# Expected growth from the demo bank's proactive line increases (score >= 680:
# 35% a review, x1.18, four eligible reviews), removed at origination so the
# line lands near the target at the end of the window.
PROACTIVE_GROWTH = 1.25
# Realised annual spend averages about 1.1x spend_level (persistent multiplier).
SPEND_LEVEL_PER_USD = 1 / 1.1
DORMANT_NO_WINDOW_USE = 0.6     # share of dormant cards unused for the whole window
DORMANT_ONSET_CYCLES = (2, 21)  # otherwise use stops in this range of cycles
OCCASIONAL_ACTIVE_MONTH = 0.20  # chance a sock-drawer card is used in a month
PREMIUM_SEGMENTS = ("Premier", "Private Banking")


def assign(n: int, rng: np.random.Generator, profile: dict) -> np.ndarray:
    w = profile["unused_line_archetypes"]
    names = list(w)
    p = np.array([w[k] for k in names], dtype=float)
    return rng.choice(names, n, p=p / p.sum())


def _mask(arche: np.ndarray) -> dict:
    return {k: arche == k for k in ARCHETYPES}


def adjust_latents(lat: pd.DataFrame, arche: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    lat = lat.copy()
    for k, m in _mask(arche).items():
        a, j = ARCHETYPES[k], int(m.sum())
        if not j:
            continue
        lat.loc[m, "_factor_reliability"] = a["reliability"] + FACTOR_SD * rng.normal(0, 1, j)
        lat.loc[m, "_factor_affluence"] = a["affluence"] + FACTOR_SD * rng.normal(0, 1, j)
        lat.loc[m, "payment_discipline"] = np.clip(a["discipline"] + LATENT_SD * rng.normal(0, 1, j), 0.02, 0.99)
        lat.loc[m, "credit_appetite"] = np.clip(a["appetite"] + LATENT_SD * rng.normal(0, 1, j), 0.01, 0.95)
        # spend_level is spend in a month of use x 12, so an occasional card
        # is scaled up by the share of months it is used.
        per_use = 1.0 / OCCASIONAL_ACTIVE_MONTH if a["activity"] == "occasional" else 1.0
        lat.loc[m, "spend_level"] = np.round(
            a["spend"] * per_use * SPEND_LEVEL_PER_USD * rng.lognormal(0, a.get("spend_sd", SPEND_SD), j), 2)
        # High relationship propensity and digital fluency keep the
        # generator's own dormancy (transactions.py) at its 8% floor for
        # active archetypes; deposits follow the archetype.
        active = a["activity"] != "dormant"
        lat.loc[m, "relationship_propensity"] = 0.99 if active else 0.2
        if active:
            lat.loc[m, "digital_fluency"] = 0.95
        if "persona" in a:
            lat.loc[m, "spend_persona"] = a["persona"]
        lat.loc[m, "deposit_propensity"] = 0.9 if a["keep_deposits"] else 0.05
    return lat


def adjust_customers(cust: pd.DataFrame, arche: np.ndarray) -> pd.DataFrame:
    """Premium segments only for the relationship archetype (the workbook's
    Relationship rule reads the segment); everyone else in a premium segment
    becomes Mass Affluent. The relationship archetype is premium."""
    cust = cust.copy()
    seg = cust["Segment"].to_numpy().copy()
    rel = arche == "relationship"
    other = np.isin(arche, [k for k in ARCHETYPES if k != "relationship"])
    seg[other & np.isin(seg, PREMIUM_SEGMENTS)] = "Mass Affluent"
    seg[rel & ~np.isin(seg, PREMIUM_SEGMENTS)] = "Premier"
    cust["Segment"] = seg
    return cust


def adjust_accounts(accounts: pd.DataFrame, cust: pd.DataFrame, arche: np.ndarray,
                    rng: np.random.Generator) -> pd.DataFrame:
    """Credit line near the archetype target, the workbook's annual fee, and
    an account open before the window so 12 months of history exist at its
    end."""
    accounts = accounts.copy()
    is_arch = arche != "standard"
    target = np.array([ARCHETYPES[k]["line"] if k in ARCHETYPES else 0.0 for k in arche])
    growth = np.where(cust["Credit Score"].to_numpy() >= 680, PROACTIVE_GROWTH, 1.0)
    line = np.round(target / growth * rng.lognormal(0, LINE_SD, len(arche)) / 250.0) * 250.0
    lim = np.where(is_arch, np.clip(line, 1000.0, 60000.0),
                   accounts["Current Credit Limit"].to_numpy())
    accounts["Original Credit Limit"] = lim
    accounts["Current Credit Limit"] = lim
    # The workbook's segments carry no annual fee except Relationship ($95);
    # the relationship archetype keeps the fee its product was priced with.
    fee_free = np.isin(arche, [k for k in ARCHETYPES if k != "relationship"])
    accounts["Annual Fee"] = np.where(fee_free, 0.0, accounts["Annual Fee"].to_numpy())
    for k, a in ARCHETYPES.items():
        if "product" in a:
            m = arche == k
            tier, program, fee = a["product"]
            accounts.loc[m, "Product Tier"] = tier
            accounts.loc[m, "Reward Program Code"] = program
            accounts.loc[m, "Annual Fee"] = fee
    oi = accounts["Account Open Cycle Index"].to_numpy()
    pre = -rng.integers(1, 61, len(arche))
    accounts["Account Open Cycle Index"] = np.where(is_arch & (oi >= 0), pre, oi)
    return accounts


def mask_activity(tx: pd.DataFrame, arche: np.ndarray, n_cyc: int,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Remove transactions in the months an archetype does not use the card."""
    n = len(arche)
    allowed = np.ones((n, n_cyc), dtype=bool)
    dormant = arche == "dormant"
    never = rng.random(n) < DORMANT_NO_WINDOW_USE
    onset = np.where(never, 0, rng.integers(*DORMANT_ONSET_CYCLES, n))
    allowed[dormant] = np.arange(n_cyc)[None, :] < onset[dormant, None]
    occasional = arche == "sock_drawer"
    allowed[occasional] = rng.random((int(occasional.sum()), n_cyc)) < OCCASIONAL_ACTIVE_MONTH
    keep = allowed[tx["_acct_ix"].to_numpy(), tx["_cycle_ix"].to_numpy()]
    tx = tx[keep]
    return _monthly_budget(tx, arche)


def _monthly_budget(tx: pd.DataFrame, arche: np.ndarray) -> pd.DataFrame:
    """Archetypes with a `monthly_budget` spend at most that multiple of their
    usual (median) month on this card; purchases beyond it, in date order,
    go elsewhere. The workbook's transactors have "peak balance small
    relative to line": without this, the generator's monthly shocks put a
    typical card's peak month at about 2.3x its average."""
    capped = [k for k, a in ARCHETYPES.items() if "monthly_budget" in a]
    if not capped:
        return tx
    acct = tx["_acct_ix"].to_numpy()
    in_scope = np.isin(arche[acct], capped)
    sub = tx[in_scope].sort_values(["_acct_ix", "_cycle_ix", "Transaction Date"], kind="stable")
    month = sub.groupby(["_acct_ix", "_cycle_ix"])["Transaction Amount"].sum()
    usual = month.groupby(level=0).median()
    mult = pd.Series({i: ARCHETYPES[arche[i]]["monthly_budget"] for i in usual.index})
    cap = (usual * mult).reindex(sub["_acct_ix"]).to_numpy()
    cum = sub.groupby(["_acct_ix", "_cycle_ix"])["Transaction Amount"].cumsum().to_numpy()
    drop = sub.index[cum > cap]
    return tx.drop(index=drop)


def keep_deposits_for(arche: np.ndarray) -> np.ndarray:
    """Customer indexes whose archetype keeps deposit and loan products."""
    keep = np.array([ARCHETYPES[k]["keep_deposits"] if k in ARCHETYPES else True for k in arche])
    return np.where(keep)[0]
