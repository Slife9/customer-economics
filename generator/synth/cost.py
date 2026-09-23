"""Cost drivers and stepped cost pools.

Contact center calls emerge from problem_rate meeting digital_fluency, with a
bank-side digital deflection rate as the servicing-efficiency lever. Digital
sessions are ROUTINE ENGAGEMENT - driven by digital_fluency alone, not by
problems - because people check balances and pay bills with nothing wrong.

A call reason taxonomy is generated so the analytical engine can name a
fixable operational problem rather than only flagging expense.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

CALL_REASONS = ["billing_query", "dispute", "lost_card", "payment_problem",
                "rate_query", "closure_request", "hardship", "rewards_query"]

# Reason mix conditional on account state. Financially stressed accounts skew
# toward payment_problem and hardship; everyone else is billing/rewards noise.
REASON_MIX_NORMAL = [0.30, 0.06, 0.05, 0.04, 0.10, 0.03, 0.02, 0.40]
REASON_MIX_STRESSED = [0.16, 0.10, 0.04, 0.34, 0.06, 0.10, 0.16, 0.04]


def drivers(cyc: pd.DataFrame, lat: pd.DataFrame, accounts: pd.DataFrame,
           rng: np.random.Generator, profile: dict,
           card_events: pd.DataFrame | None = None) -> pd.DataFrame:
    n_rows = len(cyc)
    acct_to_latent_ix = pd.Series(
        np.arange(len(accounts)), index=accounts["Masked Account Number"].to_numpy())
    idx = cyc["Masked Account Number"].map(acct_to_latent_ix).to_numpy()
    problem_rate = lat["problem_rate"].to_numpy()[idx]
    digital_fluency = lat["digital_fluency"].to_numpy()[idx]

    deflection = profile.get("digital_deflection_rate", 0.42)
    monthly_problem = problem_rate / 12.0
    # Deflection absorbs a share of problems into self-service, but stress
    # (delinquency) breaks through deflection because it needs a human.
    stressed = (cyc["Days Past Due"].to_numpy() >= 30)
    effective_deflection = np.where(stressed, deflection * 0.35,
                                    deflection * (0.5 + 0.5 * digital_fluency))
    call_lambda = np.clip(monthly_problem * (1 - effective_deflection), 0, 6)
    calls = rng.poisson(call_lambda)

    reason = np.empty(n_rows, dtype=object)
    normal_mask = ~stressed
    for mask, mix in ((normal_mask, REASON_MIX_NORMAL), (stressed, REASON_MIX_STRESSED)):
        k = int(mask.sum())
        if k:
            reason[mask] = rng.choice(CALL_REASONS, k, p=mix)

    # Digital sessions: routine engagement, driven by fluency and product use.
    sess_lambda = np.clip(1.4 + 5.2 * digital_fluency
                          + 0.9 * (cyc["Purchases Authorized"].to_numpy() > 0), 0.2, 14)
    sessions = rng.poisson(sess_lambda)

    branch_lambda = np.clip(0.25 * (1 - digital_fluency), 0, 1.2)
    branch = rng.poisson(branch_lambda)

    collections = np.where(stressed, rng.poisson(np.clip(
        0.6 + 0.02 * cyc["Days Past Due"].to_numpy(), 0, 4)), 0)

    payments_processed = 1 + (rng.random(n_rows) < 0.15).astype(int)
    fraud_alerts = rng.poisson(np.clip(0.02 + 0.01 * (1 - digital_fluency), 0, 0.2))
    disputes = (reason == "dispute").astype(int)
    complaints = ((reason == "closure_request") & (rng.random(n_rows) < 0.30)).astype(int)
    # Read from the real Card table (a reissue event or the original card at
    # account open) instead of an independent draw, so the two tables agree
    # with each other by construction rather than by coincidence.
    if card_events is not None and len(card_events):
        key = cyc["Masked Account Number"].astype(str) + "|" + cyc["Cycle Index"].astype(str)
        ce_key = (card_events["Masked Account Number"].astype(str) + "|"
                 + card_events["Cycle Index"].astype(str))
        lookup = pd.Series(card_events["Cards Issued"].to_numpy(), index=ce_key)
        cards_issued = key.map(lookup).fillna(0).astype(int).to_numpy()
    else:
        cards_issued = np.zeros(n_rows, dtype=int)
    delivery_electronic = digital_fluency > 0.45
    statements_paper = (~delivery_electronic).astype(int)
    statements_electronic = delivery_electronic.astype(int)

    return pd.DataFrame({
        "Masked Customer Number": cyc["Masked Customer Number"].to_numpy(),
        "Masked Account Number": cyc["Masked Account Number"].to_numpy(),
        "Cycle Month": cyc["Cycle Month"].to_numpy(),
        "Product Tier": cyc["Product Tier"].to_numpy(),
        "Contact Center Calls": calls,
        "Primary Call Reason": np.where(calls > 0, reason, ""),
        "Digital Sessions": sessions,
        "Branch Visits": branch,
        "Collections Contacts": collections,
        "Payments Processed": payments_processed,
        "Fraud Alerts": fraud_alerts,
        "Disputes Raised": disputes,
        "Complaints Handled": complaints,
        "Cards Issued": cards_issued,
        "Paper Statements Produced": statements_paper,
        "Electronic Statements Produced": statements_electronic,
    })


def load_pools(cfg_dir) -> pd.DataFrame:
    return pd.read_csv(cfg_dir / "cost_pools.csv")


def _stepped_cost(volume: float, bands: pd.DataFrame) -> float:
    for _, b in bands.iterrows():
        if b["Volume Band From"] <= volume < b["Volume Band To"]:
            return float(b["Band Fixed Cost USD Monthly"]) + volume * float(b["Marginal Unit Cost USD"])
    last = bands.iloc[-1]
    return float(last["Band Fixed Cost USD Monthly"]) + volume * float(last["Marginal Unit Cost USD"])


def allocate_monthly_cost(drv: pd.DataFrame, pools: pd.DataFrame,
                          n_accounts: int) -> dict:
    """Portfolio-level monthly cost by activity, from total volume in the band.

    This is what makes the stepped structure matter: avoided calls do not
    remove cash until the portfolio's total call volume crosses a band
    boundary. Per-account allocation for reporting is a separate, later step
    (divide the crossed band's marginal cost across accounts that drove it);
    this function reports the portfolio total so that property is visible.
    """
    totals = {
        "contact_center_call": drv["Contact Center Calls"].sum(),
        "collections_contact": drv["Collections Contacts"].sum(),
        "branch_visit": drv["Branch Visits"].sum(),
        "fraud_alert": drv["Fraud Alerts"].sum(),
        "dispute_case": drv["Disputes Raised"].sum(),
        "complaint_case": drv["Complaints Handled"].sum(),
        "digital_session": drv["Digital Sessions"].sum(),
        "payment_processing": drv["Payments Processed"].sum(),
        "statement_paper": drv["Paper Statements Produced"].sum(),
        "statement_electronic": drv["Electronic Statements Produced"].sum(),
        "card_issuance": drv["Cards Issued"].sum(),
    }
    out = {}
    for act, vol in totals.items():
        bands = pools[pools["Activity"] == act]
        out[act] = round(_stepped_cost(float(vol), bands), 2) if len(bands) else 0.0
    overhead = pools[pools["Activity"] == "corporate_overhead"].iloc[0]
    out["corporate_overhead"] = round(
        float(overhead["Band Fixed Cost USD Monthly"]), 2)
    return out
