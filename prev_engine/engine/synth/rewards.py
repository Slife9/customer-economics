"""
Rewards: earn by rule, redeem by propensity, carry a liability.

Earn is APPLIED from the published rule per transaction using MCC, the way a
real rewards engine does. Blended earn rate is therefore a measured OUTPUT of
the data, not an input.

Breakage is likewise measured - it is whatever the hoarders and never-redeemers
leave unredeemed. It is not a parameter.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def load_rules(path) -> pd.DataFrame:
    df = pd.read_csv(path).fillna({"bonus_categories": ""})
    df["bonus_set"] = df["bonus_categories"].apply(
        lambda s: set(str(s).split("|")) if s else set())
    return df.set_index("programme")


def load_channels(path) -> pd.DataFrame:
    return pd.read_csv(path)


def earn(tx: pd.DataFrame, accounts: pd.DataFrame, rules: pd.DataFrame,
         defect_accounts: set) -> pd.DataFrame:
    """Award units per transaction from the programme rule and the MCC.

    `defect_accounts` are Type A plants: accounts where the wrong earn rule
    was applied. They are not marked in the output - only in ground truth.
    """
    prog = accounts.set_index("Masked Account Number")["Reward Programme"]
    tx = tx.copy()
    tx["Reward Programme"] = tx["Masked Account Number"].map(prog)

    units = np.zeros(len(tx))
    applied = np.empty(len(tx), dtype=object)
    for pg, grp in tx.groupby("Reward Programme"):
        if pg not in rules.index:
            continue
        r = rules.loc[pg]
        bonus = r["bonus_set"]
        is_bonus = grp["Merchant Category"].isin(bonus).values
        rate = np.where(is_bonus, r["bonus_rate"], r["base_rate"])
        # Planted defect: base rate applied where bonus was due.
        hit = grp["Masked Account Number"].isin(defect_accounts).values
        rate = np.where(hit & is_bonus, r["base_rate"], rate)
        units[grp.index] = grp["Transaction amount"].values * rate
        applied[grp.index] = np.where(is_bonus, "bonus", "base")

    tx["Points earned on transaction"] = np.round(units, 2)
    tx["Earn Basis"] = applied
    tx["Rewards Indicator"] = np.where(units > 0, "Eligible", "Not Eligible")
    return tx


def redeem(tx: pd.DataFrame, accounts: pd.DataFrame, latents: pd.DataFrame,
           rules: pd.DataFrame, channels: pd.DataFrame, cycles: list[str],
           rng: np.random.Generator):
    """Redemption events and a per-cycle liability balance.

    Cashback (USD) settles every cycle at face value - no liability, no
    breakage. Points accrue and are redeemed on propensity.
    """
    prog = accounts.set_index("Masked Account Number")["Reward Programme"]
    lat_idx = accounts.set_index("Masked Account Number")["latent_idx"]
    cur = rules["currency"].to_dict()

    earned = (tx.groupby(["Masked Account Number", "Cycle Month"])
                ["Points earned on transaction"].sum())

    # Propensity -> monthly hazard of redeeming the accrued balance.
    HAZ = {"fast": 0.42, "steady": 0.17, "hoarder": 0.035, "never": 0.0}
    ch_w = {r["channel"]: r for _, r in channels.iterrows()}

    red_rows, liab_rows, exp_rows = [], [], []
    ci = {c: i for i, c in enumerate(cycles)}

    for acct in accounts["Masked Account Number"]:
        pg = prog.get(acct)
        if pg not in cur:
            continue
        currency = cur[pg]
        prop = latents.loc[lat_idx[acct], "redemption_propensity"]
        bal = 0.0
        since_redeem = 0
        for cy in cycles:
            e = float(earned.get((acct, cy), 0.0))
            if currency == "USD":
                # Cash back settles immediately at one cent per unit.
                if e > 0:
                    red_rows.append((acct, cy, round(e, 2), "statement_credit",
                                     round(e * 0.01, 2)))
                liab_rows.append((acct, cy, 0.0, 0.0))
                continue
            if currency == "NONE":
                liab_rows.append((acct, cy, 0.0, 0.0))
                continue
            bal += e
            since_redeem += 1
            # Expiry: a stale balance forfeits. This is the MECHANISM that
            # produces breakage - breakage itself is never a parameter.
            if since_redeem >= 18 and bal > 0 and rng.random() < 0.14:
                forfeit = bal * rng.uniform(0.55, 1.0)
                exp_rows.append((acct, cy, round(forfeit, 2), "expired", 0.0))
                bal -= forfeit
            h = HAZ[prop]
            if bal > 500 and rng.random() < h:
                share = rng.uniform(0.55, 1.0) if prop != "hoarder" else rng.uniform(0.8, 1.0)
                pts = bal * share
                wcol = f"weight_{prop}" if f"weight_{prop}" in channels.columns else "weight_steady"
                w = channels[wcol].values.astype(float)
                ch = channels["channel"].values[rng.choice(len(w), p=w / w.sum())]
                cost = pts * float(ch_w[ch]["cost_per_point_usd"])
                red_rows.append((acct, cy, round(pts, 2), ch, round(cost, 2)))
                bal -= pts
                since_redeem = 0
            liab_rows.append((acct, cy, round(bal, 2),
                              round(bal * 0.0105, 2)))  # carrying value

    red = pd.DataFrame(red_rows, columns=[
        "Masked Account Number", "Cycle Month", "Points Redeemed",
        "Redemption Channel", "Redemption Cost USD"])
    liab = pd.DataFrame(liab_rows, columns=[
        "Masked Account Number", "Cycle Month", "Points Liability Balance",
        "Liability Carrying Value USD"])
    exp = pd.DataFrame(exp_rows, columns=[
        "Masked Account Number", "Cycle Month", "Points Expired",
        "Reason", "Cost USD"])
    return red, liab, exp


def measure_breakage(tx: pd.DataFrame, red: pd.DataFrame, rules: pd.DataFrame) -> dict:
    """Breakage as an OUTPUT. Points programmes only."""
    pts_progs = [p for p, c in rules["currency"].items() if c == "POINTS"]
    accts = tx[tx["Reward Programme"].isin(pts_progs)]["Masked Account Number"].unique()
    earned = tx[tx["Masked Account Number"].isin(accts)]["Points earned on transaction"].sum()
    redeemed = red[red["Masked Account Number"].isin(accts)]["Points Redeemed"].sum()
    return {"points_earned": float(earned), "points_redeemed": float(redeemed),
            "breakage_rate": float(1 - redeemed / earned) if earned else 0.0}
