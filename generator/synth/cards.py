"""Card: plastic-level events. Table 3.

Grain: one row per physical card issued to an account, including the original
card at account open and every reissue afterward. A reissue happens because
something happened to the card - lost, stolen, damaged, a fraud compromise,
or the standard 48-month plastic expiry - never because a table needed a row.

The reissue hazard is driven by the SAME `problem_rate` and `digital_fluency`
latents that drive Cost Drivers' contact-center volume, so a customer who
generates a lot of servicing friction also generates more card reissues. Cost
Drivers' "Cards Issued" column is then read FROM this table (see run.py),
not drawn independently, so the two tables agree with each other by
construction rather than by coincidence.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

STANDARD_EXPIRY_MONTHS = 48
REISSUE_REASONS = ["LOST", "STOLEN", "DAMAGED", "FRAUD_COMPROMISE"]
REISSUE_REASON_WEIGHTS = [0.34, 0.14, 0.32, 0.20]


def generate(accounts: pd.DataFrame, lat: pd.DataFrame, cycles: list[str],
            closed_at: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    n_acct, n_cyc = len(accounts), len(cycles)
    open_idx = accounts["Account Open Cycle Index"].to_numpy()
    acct_ids = accounts["Masked Account Number"].to_numpy()
    problem_rate = lat["problem_rate"].to_numpy()
    digital_fluency = lat["digital_fluency"].to_numpy()

    rows = []
    for i in range(n_acct):
        end = min(int(closed_at[i]), n_cyc)
        issue_cycle = int(open_idx[i])
        reason = "NEW_ACCOUNT_ORIGINATION"
        seq = 1
        monthly_hazard = float(np.clip(
            0.11 * problem_rate[i] / 12.0 * (1.4 - 0.55 * digital_fluency[i]),
            0.0003, 0.025))
        while issue_cycle < end:
            expiry_cycle = issue_cycle + STANDARD_EXPIRY_MONTHS
            deactivate_cycle, deactivate_reason = None, None
            for c in range(issue_cycle, min(expiry_cycle, end)):
                if rng.random() < monthly_hazard:
                    deactivate_cycle = c
                    deactivate_reason = rng.choice(REISSUE_REASONS, p=REISSUE_REASON_WEIGHTS)
                    break
            if deactivate_cycle is None and expiry_cycle < end:
                deactivate_cycle, deactivate_reason = expiry_cycle, "EXPIRED_RENEWAL"

            rows.append({
                "Masked Card Number": f"CRD{i:07d}{seq:02d}",
                "Masked Account Number": acct_ids[i],
                "Card Sequence Number": seq,
                "Issue Cycle Index": issue_cycle,
                "Issue Cycle Month": cycles[issue_cycle] if 0 <= issue_cycle < n_cyc else "",
                "Issue Reason": reason,
                "Standard Expiry Cycle Index": expiry_cycle,
                "Deactivation Cycle Index": deactivate_cycle if deactivate_cycle is not None else -1,
                "Deactivation Cycle Month": cycles[deactivate_cycle]
                    if deactivate_cycle is not None and 0 <= deactivate_cycle < n_cyc else "",
                "Deactivation Reason": deactivate_reason or "",
                "Reissue Cost USD": 0.0 if reason == "NEW_ACCOUNT_ORIGINATION"
                    else round(float(rng.uniform(3.50, 9.00)), 2),
                "Card Status": "active" if deactivate_cycle is None else "deactivated",
            })
            if deactivate_cycle is None:
                break
            issue_cycle = deactivate_cycle
            reason = f"REISSUE_{deactivate_reason}"
            seq += 1

    return pd.DataFrame(rows)


def cards_issued_per_account_cycle(card_events: pd.DataFrame, accounts: pd.DataFrame,
                                   n_cyc: int) -> pd.DataFrame:
    """Long (account, cycle_index) -> count, for Cost Drivers to read instead
    of drawing its own independent number."""
    if not len(card_events):
        return pd.DataFrame(columns=["Masked Account Number", "Cycle Index", "Cards Issued"])
    g = card_events.groupby(["Masked Account Number", "Issue Cycle Index"]).size()
    out = g.reset_index(name="Cards Issued").rename(columns={"Issue Cycle Index": "Cycle Index"})
    return out[(out["Cycle Index"] >= 0) & (out["Cycle Index"] < n_cyc)]
