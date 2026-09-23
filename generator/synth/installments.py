"""Installment plans: a purchase converted to a fixed-term plan. Table 5.

The Amex Plan It / Citi Flex Pay / Chase My Chase Plan model: no interest
accrues, but a flat monthly plan fee is charged instead - typically
1.0-1.7% of the principal per month depending on term, richer for longer
terms. Grain is plan (Table 5) and plan x cycle runoff (Table 5b).

Take-up is driven by ticket size and the SAME price_sensitivity and
relationship_propensity latents used elsewhere - a price-sensitive customer
with a large purchase is more likely to lock in a fixed plan than revolve it
at the card's variable APR. Nothing about completion or default is set: it is
read off the same true_default_hazard the card balance uses.

SCOPE NOTE: this table is generated as a standalone overlay on top of the
transactions that qualify for a plan. It is not currently netted out of the
Purchase Balance in Table4_Account_Cycle - a transaction that becomes a plan
still also contributes to the ordinary revolving balance there. Treat the two
as evidence of different things (what got converted vs. what is carried)
rather than a fully reconciled pair of tables. Closing that gap would mean
re-running the account cycle simulation with plan-eligible spend excluded,
which was not done in this pass.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .latents import true_default_hazard

MIN_TICKET = 200.0
TERM_OPTIONS = [3, 6, 12, 24]
TERM_WEIGHTS = [0.30, 0.34, 0.26, 0.10]
# Monthly plan fee rate by term - shorter plans carry a lower monthly rate,
# consistent with published Amex Plan It / Citi Flex Pay fee schedules.
FEE_RATE_BY_TERM = {3: 0.0110, 6: 0.0125, 12: 0.0140, 24: 0.0166}


def generate(tx: pd.DataFrame, accounts: pd.DataFrame, lat: pd.DataFrame,
            cycles: list[str], closed_at: np.ndarray, rng: np.random.Generator):
    n_cyc = len(cycles)
    eligible = tx[(tx["Transaction Amount"] >= MIN_TICKET)
                 & (~tx["Cash Advance Indicator"])].copy()
    if not len(eligible):
        empty_plan = pd.DataFrame(columns=[
            "Masked Plan Number", "Masked Account Number", "Origination Cycle Month",
            "Plan Principal", "Term Months", "Monthly Plan Fee Rate",
            "Fixed Plan Fee Total", "Purchase APR On Plan", "Status"])
        empty_cyc = pd.DataFrame(columns=[
            "Masked Plan Number", "Masked Account Number", "Cycle Month",
            "Remaining Installments", "Scheduled Principal Payment",
            "Plan Fee Charged", "Remaining Principal", "Status"])
        return empty_plan, empty_cyc

    acct_ix = pd.Series(np.arange(len(accounts)),
                        index=accounts["Masked Account Number"].to_numpy())
    idx = eligible["Masked Account Number"].map(acct_ix).to_numpy()
    price_sens = lat["price_sensitivity"].to_numpy()[idx]
    rel_prop = lat["relationship_propensity"].to_numpy()[idx]
    discipline = lat["payment_discipline"].to_numpy()[idx]
    appetite = lat["credit_appetite"].to_numpy()[idx]

    ticket_z = np.clip((eligible["Transaction Amount"].to_numpy() - MIN_TICKET) / 800.0, 0, 3)
    take_p = np.clip(0.015 + 0.05 * ticket_z + 0.04 * price_sens - 0.02 * rel_prop, 0.005, 0.35)
    takes_plan = rng.random(len(eligible)) < take_p
    plans_src = eligible[takes_plan].reset_index(drop=True)
    if not len(plans_src):
        return generate(tx.iloc[0:0], accounts, lat, cycles, closed_at, rng)

    p_idx = idx[takes_plan.to_numpy() if hasattr(takes_plan, "to_numpy") else takes_plan]
    p_discipline = lat["payment_discipline"].to_numpy()[p_idx]
    p_appetite = lat["credit_appetite"].to_numpy()[p_idx]

    n_plans = len(plans_src)
    term = rng.choice(TERM_OPTIONS, n_plans, p=TERM_WEIGHTS)
    fee_rate = np.array([FEE_RATE_BY_TERM[t] for t in term])
    principal = plans_src["Transaction Amount"].to_numpy()
    origin_cyc_month = plans_src["Cycle Month"].to_numpy()
    origin_cyc_idx = plans_src["_cycle_ix"].to_numpy() if "_cycle_ix" in plans_src.columns \
        else np.searchsorted(np.array(cycles), origin_cyc_month)
    acct_id = plans_src["Masked Account Number"].to_numpy()
    acct_close_lookup = pd.Series(closed_at, index=accounts["Masked Account Number"].to_numpy())
    plan_acct_close = acct_close_lookup.loc[acct_id].to_numpy()

    hazard = true_default_hazard(p_discipline, p_appetite)

    plan_rows, cyc_rows = [], []
    for j in range(n_plans):
        plan_id = f"PLN{j:07d}"
        t = int(term[j])
        principal_j = round(float(principal[j]), 2)
        fee_total = round(principal_j * fee_rate[j] * t, 2)
        monthly_principal = principal_j / t
        remaining = principal_j
        status = "active"
        start = int(origin_cyc_idx[j])
        end_window = min(start + t, n_cyc, int(plan_acct_close[j]))
        completed = True
        for k, c in enumerate(range(start, end_window)):
            missed = rng.random() < hazard[j]
            pay = 0.0 if missed else monthly_principal
            remaining = max(remaining - pay, 0.0)
            cyc_rows.append({
                "Masked Plan Number": plan_id,
                "Masked Account Number": acct_id[j],
                "Cycle Month": cycles[c],
                "Remaining Installments": t - k - 1,
                "Scheduled Principal Payment": round(monthly_principal, 2),
                "Plan Fee Charged": round(fee_total / t, 2),
                "Remaining Principal": round(remaining, 2),
                "Status": "active",
            })
            if missed and rng.random() < 0.25:
                status = "defaulted"
                completed = False
                break
        else:
            if end_window < start + t:
                status = "open_at_window_end"
                completed = False
        if completed and status == "active":
            status = "completed"
        if cyc_rows and cyc_rows[-1]["Masked Plan Number"] == plan_id:
            cyc_rows[-1]["Status"] = status

        plan_rows.append({
            "Masked Plan Number": plan_id,
            "Masked Account Number": acct_id[j],
            "Origination Cycle Month": origin_cyc_month[j],
            "Plan Principal": principal_j,
            "Term Months": t,
            "Monthly Plan Fee Rate": fee_rate[j],
            "Fixed Plan Fee Total": fee_total,
            "Purchase APR On Plan": 0.0,
            "Status": status,
        })

    return pd.DataFrame(plan_rows), pd.DataFrame(cyc_rows)
