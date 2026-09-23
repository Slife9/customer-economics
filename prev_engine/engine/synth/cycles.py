"""
Account-cycle behaviour, CECL, US standardized capital, cost drivers,
and the Type A planted defects.

Nothing here decides profitability. Balances come from credit appetite meeting
the granted limit; delinquency from payment discipline; servicing demand from
problem rate meeting digital fluency; cost from drivers meeting a stepped
cost pool. What each customer is worth falls out afterwards.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# 12 CFR 217 subpart D
CCF_UNCONDITIONALLY_CANCELLABLE = 0.00
RW_RETAIL = 1.00
RW_PAST_DUE = 1.50
PAST_DUE_DAYS = 90

ACTIVITIES = {
    "Contact Center Calls": 5.83, "Digital Sessions": 0.025, "Branch Visits": 1.71,
    "Payments Processed": 0.093, "Collections Contacts": 78.45, "Fraud Alerts": 12.30,
    "Disputes Raised": 4.26, "Complaints Handled": 16.57, "Cards Issued": 1.17,
    "Statements Produced": 0.63,
}

# Capacity tiers: cost only falls when a step is crossed. Answers the CFO
# objection that semi-fixed cost does not move with avoided volume.
COST_POOL_STEPS = {
    "Contact Center Calls": [(0, 20000, 92000, 3.10), (20000, 60000, 240000, 2.85),
                             (60000, 10**9, 520000, 2.60)],
    "Collections Contacts": [(0, 4000, 148000, 42.0), (4000, 12000, 380000, 39.0),
                             (12000, 10**9, 720000, 36.0)],
}

CALL_REASONS = ["billing_query", "dispute", "lost_card", "payment_problem",
                "rate_query", "closure_request", "hardship", "rewards_query"]


def simulate_cycles(accounts, latents, cycles, rng, promo_share=0.10):
    """One row per account per cycle."""
    rows = []
    for _, acc in accounts.iterrows():
        lat = latents.loc[acc["latent_idx"]]
        appetite = float(lat["credit_appetite"])
        discipline = float(lat["payment_discipline"])
        limit = float(acc["Credit Limit"])
        apr = float(acc["Purchase Rate (APR)"])

        # Target utilization is appetite, damped for secured/low limits.
        target_u = np.clip(appetite * rng.uniform(0.75, 1.25), 0.0, 0.98)
        util = target_u
        dpd = 0
        on_promo = rng.random() < promo_share
        promo_left = rng.integers(4, 13) if on_promo else 0
        promo_rate = float(rng.choice([0.0, 4.99, 9.99])) if on_promo else np.nan

        for cy in cycles:
            util = float(np.clip(util + rng.normal(0, 0.055), 0.0, 0.99))
            bal = limit * util
            adb = bal * rng.uniform(0.86, 1.02)

            # Revolve or settle: discipline drives it, appetite modulates.
            p_revolve = np.clip(0.94 - discipline * 0.88 + appetite * 0.30, 0.02, 0.96)
            revolves = rng.random() < p_revolve
            if bal < 25:
                acct_type = "Inactive"
            elif revolves:
                acct_type = "Revolver"
            else:
                acct_type = "Transactor"

            promo_bal = bal * rng.uniform(0.35, 0.8) if promo_left > 0 else 0.0
            std_bal = bal - promo_bal
            interest = (std_bal * apr / 100 / 12) if acct_type == "Revolver" else 0.0
            promo_int = (promo_bal * (promo_rate or 0) / 100 / 12) if promo_left > 0 else 0.0

            # Delinquency hazard from discipline and stress.
            p_late = np.clip((1 - discipline) ** 2.1 * 0.34, 0.0, 0.7)
            if rng.random() < p_late and acct_type != "Inactive":
                dpd = min(dpd + 30, 180)
            else:
                dpd = max(dpd - 30, 0)
            late_fee = 32.0 if (dpd >= 30 and rng.random() < 0.72) else 0.0

            status = ("Active" if promo_left > 0 else
                      ("Expired" if on_promo else None))
            rows.append((
                acc["Masked Customer Number"], acc["Masked Account Number"], cy,
                acc["Product"], acc["Reward Programme"], acct_type,
                round(limit, 2), round(util, 4), round(bal, 2), round(adb, 2),
                round(interest, 2), round(promo_int, 2), round(promo_bal, 2),
                apr, promo_rate if promo_left > 0 else np.nan, status,
                int(dpd), round(late_fee, 2), int(acc["Annual Fee"]),
                bool(acc["Hardship"]), bool(acc["SCRA"]),
            ))
            if promo_left > 0:
                promo_left -= 1

    return pd.DataFrame(rows, columns=[
        "Masked Customer Number", "Masked Account Number", "Cycle Month", "Product",
        "Reward Programme", "Account Type", "Credit Limit", "Utilization",
        "Ending Balance", "Average Daily Balance", "Purchase Interest",
        "Promotional Interest", "Promotional Balance", "Purchase Rate (APR)",
        "Promotional Rate In Force", "Promotional Status", "Days Past Due",
        "Late Fee Amount", "Card Annual Fee", "Hardship Status", "SCRA Flag"])


def risk_cecl(cyc: pd.DataFrame, accounts: pd.DataFrame,
              rng: np.random.Generator) -> pd.DataFrame:
    """ASC 326 lifetime ECL. No stages. No allowance on unfunded
    unconditionally cancellable commitments."""
    score = accounts.set_index("Masked Account Number")["Credit Score"]
    s = cyc["Masked Account Number"].map(score).values
    pd12 = np.clip(0.42 * np.exp(-(s - 500) / 105.0), 0.002, 0.45)
    dpd_mult = 1.0 + (cyc["Days Past Due"].values / 30.0) * 0.85
    pd12 = np.clip(pd12 * dpd_mult, 0.002, 0.95)
    # Card lifetime bounded by drawn-balance runoff (line is cancellable).
    life_yrs = np.clip(1.6 + (750 - np.clip(s, 500, 850)) / 260.0, 1.0, 3.2)
    pd_life = np.clip(1 - (1 - pd12) ** life_yrs, 0.002, 0.98)
    lgd = np.clip(rng.normal(0.82, 0.05, len(cyc)), 0.55, 0.96)
    ead = cyc["Ending Balance"].values  # unfunded excluded
    ecl = pd_life * lgd * ead
    return pd.DataFrame({
        "Masked Customer Number": cyc["Masked Customer Number"],
        "Masked Account Number": cyc["Masked Account Number"],
        "Cycle Month": cyc["Cycle Month"],
        "PD 12 Month": pd12.round(5), "PD Lifetime": pd_life.round(5),
        "LGD": lgd.round(4), "EAD": ead.round(2),
        "Lifetime ECL": ecl.round(2),
        "Expected Loss Monthly": (ecl / (life_yrs * 12)).round(4),
        "Measurement Basis": "CECL ASC 326",
    })


def capital_us(cyc: pd.DataFrame, target_ratio=0.135, coe=0.11) -> pd.DataFrame:
    drawn = cyc["Ending Balance"].values
    undrawn = (cyc["Credit Limit"] - cyc["Ending Balance"]).clip(lower=0).values
    ead = drawn + CCF_UNCONDITIONALLY_CANCELLABLE * undrawn
    rw = np.where(cyc["Days Past Due"].values >= PAST_DUE_DAYS, RW_PAST_DUE, RW_RETAIL)
    rwa = ead * rw
    cap = rwa * target_ratio
    # Separate, labelled economic track using a behavioural CCF.
    beh_ccf = 0.22
    eco_ead = drawn + beh_ccf * undrawn
    eco_cap = eco_ead * 0.85 * target_ratio
    return pd.DataFrame({
        "Masked Customer Number": cyc["Masked Customer Number"],
        "Masked Account Number": cyc["Masked Account Number"],
        "Cycle Month": cyc["Cycle Month"],
        "Drawn Balance": drawn.round(2), "Undrawn Commitment": undrawn.round(2),
        "Unconditionally Cancellable": True,
        "Regulatory CCF": CCF_UNCONDITIONALLY_CANCELLABLE,
        "Regulatory EAD": ead.round(2), "Regulatory Risk Weight": rw,
        "Regulatory RWA": rwa.round(2),
        "Target Capital Ratio": target_ratio,
        "Regulatory Attributed Capital": cap.round(2),
        "Regulatory Capital Charge Monthly": (cap * coe / 12).round(4),
        "Behavioural CCF": beh_ccf, "Economic EAD": eco_ead.round(2),
        "Economic Attributed Capital": eco_cap.round(2),
        "Economic Capital Charge Monthly": (eco_cap * coe / 12).round(4),
        "Capital Approach": "US Standardized (12 CFR 217 subpart D)",
    })


def cost_drivers(cyc: pd.DataFrame, accounts: pd.DataFrame, latents: pd.DataFrame,
                 rng: np.random.Generator) -> pd.DataFrame:
    li = accounts.set_index("Masked Account Number")["latent_idx"]
    idx = cyc["Masked Account Number"].map(li).values
    prob = latents["problem_rate"].values[idx]
    dig = latents["digital_fluency"].values[idx]
    hardship = cyc["Hardship Status"].values

    events = rng.poisson(prob / 12.0)
    # Where the event lands depends on channel preference, not on cost.
    p_self = np.clip(dig * 0.92, 0.02, 0.95)
    self_serve = rng.binomial(events, p_self)
    assisted = events - self_serve
    branch = rng.binomial(assisted, np.clip(0.42 - dig * 0.38, 0.01, 0.5))
    calls = assisted - branch
    # Hardship customers need more help. This is an obligation, not leakage.
    calls = calls + rng.poisson(np.where(hardship, 0.9, 0.0))

    coll = rng.poisson(np.where(cyc["Days Past Due"].values >= 30, 1.7, 0.02))
    reasons = np.where(calls > 0,
                       rng.choice(CALL_REASONS, len(cyc)), "")
    reasons = np.where(hardship & (calls > 0), "hardship", reasons)

    return pd.DataFrame({
        "Masked Customer Number": cyc["Masked Customer Number"],
        "Masked Account Number": cyc["Masked Account Number"],
        "Cycle Month": cyc["Cycle Month"], "Product Type": "CARD",
        "Contact Center Calls": calls, "Primary Call Reason": reasons,
        # Routine engagement, driven by fluency and by simply having an
        # active balance - not by something going wrong.
        "Digital Sessions": (rng.poisson(np.clip(dig * 5.2, 0.1, 6.0))
                             * np.where(cyc["Account Type"].values != "Inactive", 1, 0)
                             + self_serve),
        "Branch Visits": branch, "Collections Contacts": coll,
        "Payments Processed": np.where(cyc["Ending Balance"].values > 0, 1, 0),
        "Fraud Alerts": rng.poisson(0.018, len(cyc)),
        "Disputes Raised": rng.poisson(0.03, len(cyc)),
        "Complaints Handled": rng.poisson(0.008, len(cyc)),
        "Cards Issued": rng.poisson(0.02, len(cyc)),
        "Statements Produced": 1,
    })


def cost_pools() -> pd.DataFrame:
    rows = []
    for act, unit in ACTIVITIES.items():
        steps = COST_POOL_STEPS.get(act)
        if steps:
            for lo, hi, fixed, marg in steps:
                rows.append((act, "Tier 1" if act != "Digital Sessions" else "Tier 2",
                             act, lo, hi, fixed, marg, "stepped"))
        else:
            rows.append((act, "Tier 2", act, 0, 10**9, 0.0, unit, "variable"))
    return pd.DataFrame(rows, columns=[
        "Activity", "Allocation Tier", "Driver Name", "Volume Band From",
        "Volume Band To", "Band Fixed Cost", "Marginal Unit Cost", "Cost Behaviour"])


def plant_defects(accounts, cyc, tx, rng, prevalence=0.035):
    """Type A: discrete operational failures, recorded only in ground truth.

    Each is detectable from evidence (a rate that disagrees with the card, a
    fee due but not posted). No marker column is written to any engine table.
    """
    gt = []
    accts = accounts["Masked Account Number"].values
    n = len(accts)

    wrong_earn = set(rng.choice(accts, int(n * prevalence), replace=False))
    for a in wrong_earn:
        gt.append((a, "WRONG_EARN_RULE",
                   "Bonus category earning base rate", len(cyc), np.nan))

    ic_short = set(rng.choice(accts, int(n * prevalence * 0.8), replace=False))
    m = tx["Masked Account Number"].isin(ic_short)
    shortfall = tx.loc[m, "Interchange earned"] * 0.28
    tx.loc[m, "Interchange earned"] = (tx.loc[m, "Interchange earned"] - shortfall).round(4)
    for a, v in shortfall.groupby(tx.loc[m, "Masked Account Number"]).sum().items():
        gt.append((a, "INTERCHANGE_BELOW_EXPECTED",
                   "Booked below the published rate card", len(cyc), round(float(v), 2)))

    fee_unposted = set(rng.choice(
        accounts.loc[accounts["Annual Fee"] > 0, "Masked Account Number"].values,
        max(1, int((accounts["Annual Fee"] > 0).sum() * prevalence * 2)), replace=False))
    for a in fee_unposted:
        amt = float(accounts.loc[accounts["Masked Account Number"] == a, "Annual Fee"].iat[0])
        gt.append((a, "UNPOSTED_CONTRACTUAL_FEE",
                   "Annual fee agreed but never billed", len(cyc) // 12, amt * (len(cyc) / 12)))

    price_below = set(rng.choice(accts, int(n * prevalence * 0.7), replace=False))
    mm = cyc["Masked Account Number"].isin(price_below)
    cyc.loc[mm, "Purchase Rate (APR)"] = (cyc.loc[mm, "Purchase Rate (APR)"] - 4.25).round(2)
    for a in price_below:
        gt.append((a, "PRICE_BELOW_CONTRACT",
                   "Charged rate below the contractual rate", len(cyc), np.nan))

    gtdf = pd.DataFrame(gt, columns=[
        "Masked Account Number", "Defect Type", "Description",
        "Cycles Affected", "Estimated Total Impact"])
    return tx, cyc, gtdf, wrong_earn
