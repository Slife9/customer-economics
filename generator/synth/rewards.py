"""Rewards: earn by published rule, redeem by propensity, expire by mechanism.

Points are awarded by applying the PUBLISHED PROGRAM RULE to the transaction's
merchant category. A 3x program earns 3x on its bonus categories and 1x
elsewhere. Blended earn rate is therefore a measured output, never a parameter.

Breakage is produced by an expiry mechanism acting on a FIFO point ledger. It
is measured from the resulting expiry events. There is no breakage parameter
anywhere in this module - only hoarders, never-redeemers and an expiry rule.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# Which channels each redeemer type reaches for. Channel choice is a behavior,
# so it is driven by the latent, not by a fixed portfolio-level share.
CHANNEL_WEIGHTS = {
    "travel":    {"travel_portal": .34, "transfer_partner": .30,
                  "statement_credit": .18, "gift_card": .09,
                  "merchandise": .06, "charity_donation": .03},
    "default":   {"statement_credit": .38, "cash_back": .24, "gift_card": .16,
                  "merchandise": .12, "travel_portal": .06,
                  "transfer_partner": .02, "charity_donation": .02},
}

REDEEM_BEHAVIOR = {
    # (monthly redemption probability, share of balance redeemed when it fires)
    "fast":   (0.34, 0.85),
    "steady": (0.14, 0.75),
    "hoarder": (0.035, 0.60),
    "never":  (0.004, 0.40),
}


def load_config(cfg_dir):
    rules = pd.read_csv(cfg_dir / "reward_program_rules.csv")
    channels = pd.read_csv(cfg_dir / "redemption_channels.csv")
    return rules, channels


def earn(tx: pd.DataFrame, accounts: pd.DataFrame, rules: pd.DataFrame,
         wrong_earn_accounts: set) -> pd.DataFrame:
    """Apply the published rule to each transaction's reward category."""
    r = rules.set_index("Program Code")
    prog = accounts.set_index("Masked Account Number")["Reward Program Code"]
    tx = tx.copy()
    tx["Reward Program Code"] = tx["Masked Account Number"].map(prog)

    base = tx["Reward Program Code"].map(r["Base Earn Rate"]).astype(float)
    bonus_rate = tx["Reward Program Code"].map(r["Bonus Earn Rate"]).astype(float)
    bonus_cats = tx["Reward Program Code"].map(
        r["Bonus Reward Categories"]).fillna("")

    qualifies = np.array([
        (str(bc) != "" and str(bc) != "nan" and rc in str(bc).split("|"))
        for bc, rc in zip(bonus_cats, tx["Reward Category"])])

    # Annual bonus spend cap, applied on a running basis within each year.
    cap = tx["Reward Program Code"].map(
        r["Annual Bonus Spend Cap USD"]).astype(float).to_numpy()
    tx["_year"] = tx["Cycle Month"].str.slice(0, 4)
    bonus_amt = np.where(qualifies, tx["Transaction Amount"].to_numpy(), 0.0)
    running = (pd.DataFrame({"a": tx["Masked Account Number"], "y": tx["_year"],
                             "v": bonus_amt})
               .groupby(["a", "y"])["v"].cumsum().to_numpy())
    under_cap = (cap <= 0) | (running <= cap)
    applies_bonus = qualifies & under_cap

    # WRONG_EARN_RULE defect: base rate applied where the category qualified.
    if wrong_earn_accounts:
        suppressed = tx["Masked Account Number"].isin(wrong_earn_accounts).to_numpy()
        applies_bonus = applies_bonus & ~suppressed

    rate = np.where(applies_bonus, bonus_rate, base)
    tx["Points Earned"] = np.round(tx["Transaction Amount"].to_numpy() * rate, 2)
    tx["Earn Rate Applied"] = rate
    tx["Earn Basis"] = np.where(applies_bonus, "bonus",
                                np.where(rate > 0, "base", "none"))
    return tx.drop(columns=["_year"])


def redeem_and_expire(tx: pd.DataFrame, accounts: pd.DataFrame, lat: pd.DataFrame,
                      rules: pd.DataFrame, channels: pd.DataFrame,
                      cycles: list[str], closed_at: np.ndarray,
                      rng: np.random.Generator):
    """FIFO point ledger per account: earn, redeem, expire, carry liability."""
    r = rules.set_index("Program Code")
    chan_cost = channels.set_index("Redemption Channel")["Cost Per Point Cents"]
    n_cyc = len(cycles)

    earned = np.zeros((len(accounts), n_cyc))
    if len(tx):
        g = tx.groupby(["_acct_ix", "_cycle_ix"])["Points Earned"].sum()
        idx = np.array(list(g.index.to_list()))
        earned[idx[:, 0], idx[:, 1]] = g.to_numpy()

    acct_ids = accounts["Masked Account Number"].to_numpy()
    programs = accounts["Reward Program Code"].to_numpy()
    persona = lat["spend_persona"].to_numpy()
    propensity = lat["redemption_propensity"].to_numpy()

    expire_after = r["Points Expire After Months"].to_dict()
    inactivity_months = r["Expire On Inactivity Months"].to_dict()

    red_rows, exp_rows, liab_rows = [], [], []

    for i in range(len(accounts)):
        prog = programs[i]
        if prog == "CORE_LOW_RATE_NO_REWARDS":
            continue
        hard_exp = int(expire_after.get(prog, 0) or 0)
        inact_exp = int(inactivity_months.get(prog, 0) or 0)
        p_red, share = REDEEM_BEHAVIOR[propensity[i]]
        cw = CHANNEL_WEIGHTS["travel"] if persona[i] == "travel" else CHANNEL_WEIGHTS["default"]
        # Cash-back programs can only use cash-like channels.
        if r.loc[prog, "Currency"] == "cashback":
            cw = {"statement_credit": .55, "cash_back": .40, "charity_donation": .05}
        ch_names = list(cw)
        ch_p = np.array([cw[c] for c in ch_names], dtype=float)
        ch_p = ch_p / ch_p.sum()

        ledger = []  # (cycle_earned, points_remaining)
        last_activity = -1
        for c in range(min(closed_at[i], n_cyc)):
            e = earned[i, c]
            if e > 0:
                ledger.append([c, e])
                last_activity = c

            # Hard expiry: points older than the program's expiry window.
            # The earn cycle is recorded so breakage can be measured against
            # the vintage it actually belongs to, not the expiry event's own
            # date - the two differ by the program's whole expiry term.
            if hard_exp > 0:
                for lot in ledger:
                    if lot[1] > 0 and c - lot[0] >= hard_exp:
                        exp_rows.append((acct_ids[i], cycles[c], lot[1],
                                         "POINTS_EXPIRED_AGE", cycles[lot[0]]))
                        lot[1] = 0.0
            # Inactivity expiry: the whole balance lapses.
            if (inact_exp > 0 and last_activity >= 0
                    and c - last_activity >= inact_exp):
                for lot in ledger:
                    if lot[1] > 0.009:
                        exp_rows.append((acct_ids[i], cycles[c], lot[1],
                                         "POINTS_EXPIRED_INACTIVITY", cycles[lot[0]]))
                        lot[1] = 0.0

            balance = sum(l[1] for l in ledger)
            if balance > 0 and rng.random() < p_red:
                want = balance * share * rng.uniform(0.7, 1.0)
                ch = ch_names[rng.choice(len(ch_names), p=ch_p)]
                taken = 0.0
                for lot in ledger:  # FIFO
                    if taken >= want:
                        break
                    take = min(lot[1], want - taken)
                    lot[1] -= take
                    taken += take
                if taken > 0:
                    cost = round(taken * float(chan_cost[ch]) / 100.0, 2)
                    red_rows.append((acct_ids[i], cycles[c], round(taken, 2),
                                     ch, cost))
                    balance -= taken

            liab_rows.append((acct_ids[i], cycles[c], round(balance, 2)))
            ledger = [l for l in ledger if l[1] > 0.009]

    red = pd.DataFrame(red_rows, columns=[
        "Masked Account Number", "Cycle Month", "Points Redeemed",
        "Redemption Channel", "Redemption Cost USD"])
    exp = pd.DataFrame(exp_rows, columns=[
        "Masked Account Number", "Cycle Month", "Points Expired", "Expiry Reason",
        "Points Earned Cycle Month"])
    liab = pd.DataFrame(liab_rows, columns=[
        "Masked Account Number", "Cycle Month", "Outstanding Points Balance"])
    return red, exp, liab


def measure_breakage(tx: pd.DataFrame, exp: pd.DataFrame, cycles: list[str],
                     rules: pd.DataFrame | None = None) -> dict:
    """Breakage on MATURED vintages only.

    A vintage is matured only once its full expiry window has had a chance to
    elapse. Using a fixed lookback shorter than the program's own expiry term
    would count vintages that have not finished expiring yet, understating
    breakage and reporting zero even when the mechanism is working correctly.
    """
    if not len(tx):
        return {}
    longest_expiry = 24
    if rules is not None and len(rules):
        vals = rules["Points Expire After Months"].replace(0, np.nan).dropna()
        if len(vals):
            longest_expiry = int(vals.max())
    cutoff = cycles[max(len(cycles) - longest_expiry - 1, 0)]
    mat_tx = tx[tx["Cycle Month"] <= cutoff]
    earned_mat = float(mat_tx["Points Earned"].sum())
    # Filter by the VINTAGE the points were earned in, not the expiry event's
    # own date - those differ by the program's whole expiry term, so filtering
    # on expiry date alone would wrongly report zero breakage for vintages
    # that have, in fact, already run their full course.
    if len(exp) and "Points Earned Cycle Month" in exp.columns:
        expired_mat = float(
            exp[exp["Points Earned Cycle Month"] <= cutoff]["Points Expired"].sum())
    else:
        expired_mat = 0.0
    return {
        "points_earned_all": float(tx["Points Earned"].sum()),
        "points_expired_all": float(exp["Points Expired"].sum()) if len(exp) else 0.0,
        "matured_through_cycle": cutoff,
        "points_earned_matured": earned_mat,
        "points_expired_matured": expired_mat,
        "breakage_rate_matured_vintages":
            round(expired_mat / earned_mat, 6) if earned_mat else 0.0,
    }
