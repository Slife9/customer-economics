"""Waivers and entitled-vs-charged fee reconciliation.

Fee Events already records what cycles.py actually charged. This module adds
the waiver population (grants that suppress a fee, with a review date most of
the time) and reconciles Fee Events against the versioned Fee Schedule so
UNPOSTED_CONTRACTUAL_FEE is something the analytical engine can find from
evidence rather than a marker.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import policy as P


def grant_waivers(fee_events: pd.DataFrame, accounts: pd.DataFrame,
                  cycles: list[str], rng: np.random.Generator,
                  waiver_rate: float, review_discipline: float) -> pd.DataFrame:
    """Grant waivers against a sample of ANNUAL_FEE and LATE_FEE charges.

    A granted waiver suppresses that specific charge going forward for the
    account (annual fee: the next N cycles; late fee: this one instance).
    Whether an EXPIRED or NO-EXPIRY waiver keeps suppressing beyond its own
    terms is a defect, planted separately in defects.py.
    """
    eligible = fee_events[fee_events["Fee Code"].isin(
        ["ANNUAL_FEE", "LATE_FEE_FIRST", "LATE_FEE_SUBSEQUENT"])]
    n = len(eligible)
    if n == 0:
        return pd.DataFrame(columns=[
            "Waiver ID", "Masked Account Number", "Fee Code", "Grant Cycle Month",
            "Review Date Cycle Month", "Rationale Code", "Status",
            "Has Review Date"])
    granted_mask = rng.random(n) < waiver_rate
    granted = eligible[granted_mask].reset_index(drop=True)
    has_review = rng.random(len(granted)) < review_discipline
    cyc_index = {c: i for i, c in enumerate(cycles)}
    grant_idx = granted["Cycle Month"].map(cyc_index).to_numpy()
    review_span = rng.integers(6, 18, len(granted))
    review_idx = np.clip(grant_idx + review_span, 0, len(cycles) - 1)
    rationale = rng.choice(
        ["LOYALTY_RETENTION", "COMPETITIVE_MATCH", "GOODWILL_SERVICE_RECOVERY",
         "FIRST_YEAR_COURTESY"], len(granted))
    return pd.DataFrame({
        "Waiver ID": [f"WVR{i:07d}" for i in range(len(granted))],
        "Masked Account Number": granted["Masked Account Number"].to_numpy(),
        "Fee Code": granted["Fee Code"].to_numpy(),
        "Grant Cycle Month": granted["Cycle Month"].to_numpy(),
        "Review Date Cycle Month": np.where(
            has_review, np.array(cycles)[review_idx], ""),
        "Rationale Code": rationale,
        "Status": "active",
        "Has Review Date": has_review,
    })


def reconcile_entitled_vs_charged(fee_events: pd.DataFrame, accounts: pd.DataFrame,
                                  cyc: pd.DataFrame, schedule: pd.DataFrame,
                                  waivers: pd.DataFrame) -> pd.DataFrame:
    """What the schedule says is due vs what Fee Events shows was charged.

    This table is the evidence UNPOSTED_CONTRACTUAL_FEE is found from: it does
    not itself know which rows are defects.
    """
    ann = accounts[["Masked Account Number", "Product Tier", "Annual Fee"]].copy()
    charged = fee_events[fee_events["Fee Code"] == "ANNUAL_FEE"].groupby(
        "Masked Account Number").size().rename("times_charged")
    ann = ann.merge(charged, on="Masked Account Number", how="left")
    ann["times_charged"] = ann["times_charged"].fillna(0).astype(int)
    waived_accounts = set(waivers[waivers["Fee Code"] == "ANNUAL_FEE"]
                          ["Masked Account Number"]) if len(waivers) else set()
    ann["Waived"] = ann["Masked Account Number"].isin(waived_accounts)
    n_years = cyc["Cycle Month"].nunique() // 12 if len(cyc) else 0
    ann["Entitled Charges Over Window"] = np.where(ann["Annual Fee"] > 0, max(n_years, 1), 0)
    return ann.rename(columns={"times_charged": "Actual Charges Over Window"})
