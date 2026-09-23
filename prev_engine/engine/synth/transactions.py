"""
Transactions, merchant categories and interchange.

Merchant mix comes from the customer's spend_persona latent. Interchange is
then LOOKED UP from the rate card by (product tier, merchant category) - it
is never drawn from a distribution, because in a real book it is a contractual
schedule. That is what makes "interchange below expected" detectable.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# Category mix by persona. Columns are categories; each row sums to 1.
CATEGORIES = ["grocery", "fuel", "restaurant", "travel_air", "travel_lodging",
              "travel_transit", "retail", "utilities", "pharmacy", "healthcare",
              "online", "business"]

PERSONA_MIX = {
    "travel":   [0.11, 0.06, 0.15, 0.14, 0.13, 0.07, 0.12, 0.04, 0.03, 0.02, 0.11, 0.02],
    "grocery":  [0.34, 0.10, 0.09, 0.01, 0.01, 0.02, 0.14, 0.09, 0.07, 0.03, 0.09, 0.01],
    "everyday": [0.22, 0.13, 0.13, 0.02, 0.02, 0.04, 0.16, 0.10, 0.06, 0.03, 0.08, 0.01],
    "business": [0.06, 0.13, 0.12, 0.07, 0.06, 0.04, 0.08, 0.05, 0.02, 0.02, 0.10, 0.25],
    "online":   [0.14, 0.06, 0.10, 0.02, 0.02, 0.03, 0.13, 0.08, 0.05, 0.02, 0.33, 0.02],
}

# Typical ticket size by category, lognormal mu on log dollars.
TICKET_MU = {"grocery": 3.95, "fuel": 3.65, "restaurant": 3.45, "travel_air": 5.65,
             "travel_lodging": 5.45, "travel_transit": 2.95, "retail": 4.05,
             "utilities": 4.65, "pharmacy": 3.35, "healthcare": 4.45,
             "online": 3.85, "business": 4.85}


def load_rate_card(path) -> dict:
    df = pd.read_csv(path)
    return {(r["product"], r["category"]): r["rate_pct"] / 100.0
            for _, r in df.iterrows()}


def load_mcc(path) -> pd.DataFrame:
    return pd.read_csv(path)


def generate(accounts: pd.DataFrame, latents: pd.DataFrame, cycles: list[str],
             rate_card: dict, mcc_cat: pd.DataFrame,
             rng: np.random.Generator) -> pd.DataFrame:
    """One row per transaction. Interchange looked up, never drawn."""
    mcc_by_cat = {c: g["mcc"].tolist() for c, g in mcc_cat.groupby("category")}
    rows = []
    n_cy = len(cycles)

    for i, acc in accounts.iterrows():
        lat = latents.loc[acc["latent_idx"]]
        persona = lat["spend_persona"]
        mix = np.array(PERSONA_MIX[persona], dtype=float)
        mix = mix / mix.sum()

        annual = float(lat["spend_level"])
        # Inactive-ish customers spend little; this emerges from appetite and
        # discipline rather than being assigned a label.
        if acc["dormant"]:
            annual *= rng.uniform(0.0, 0.06)

        monthly = annual / 12.0
        product = acc["Product"]

        for ci, cy in enumerate(cycles):
            # Seasonal lift in Nov/Dec, dip in Jan/Feb.
            mo = int(cy.split("-")[1])
            seas = {11: 1.22, 12: 1.34, 1: 0.84, 2: 0.88}.get(mo, 1.0)
            spend_m = max(0.0, rng.gamma(4.0, monthly * seas / 4.0))
            if spend_m < 1:
                continue
            n_tx = max(1, int(rng.poisson(max(1.0, spend_m / 90.0))))
            cats = rng.choice(CATEGORIES, n_tx, p=mix)
            amts = np.array([rng.lognormal(TICKET_MU[c], 0.62) for c in cats])
            if amts.sum() <= 0:
                continue
            amts = amts / amts.sum() * spend_m

            for c, a in zip(cats, amts):
                mcc = int(rng.choice(mcc_by_cat[c]))
                rate = rate_card.get((product, c), 0.015)
                rows.append((acc["Masked Customer Number"], acc["Masked Account Number"],
                             cy, "Debit", round(float(a), 2), mcc, c,
                             round(float(a) * rate, 4), round(rate * 100, 3)))

    return pd.DataFrame(rows, columns=[
        "Masked Customer Number", "Masked Account Number", "Cycle Month",
        "Amount Type", "Transaction amount", "Merchant Category Code (MCC)",
        "Merchant Category", "Interchange earned", "Interchange Rate Applied"])
