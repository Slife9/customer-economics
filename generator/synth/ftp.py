"""Funding Transfer Pricing curve, referencing SOFR.

Deposit revenue is the FTP CREDIT the bank earns on the balance, not a rate
the customer is paid. Card funding cost is the FTP CHARGE at the internal
transfer rate. Whether a card-losing, deposit-rich customer nets out
profitable is meant to emerge from this, never be asserted.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

BENCHMARK = "SOFR"
TENORS_MONTHS = [1, 3, 6, 12, 24, 36]


def build_curve(cycles: list[str], rng: np.random.Generator,
                base_rate: float = 4.85) -> pd.DataFrame:
    """A gently drifting short-rate path, term structure added by tenor."""
    n = len(cycles)
    path = np.zeros(n)
    path[0] = base_rate
    for i in range(1, n):
        path[i] = np.clip(path[i - 1] + rng.normal(-0.015, 0.07), 0.25, 8.0)
    tenor_spread = {1: -0.05, 3: 0.00, 6: 0.08, 12: 0.18, 24: 0.30, 36: 0.38}
    rows = []
    for i, c in enumerate(cycles):
        for t in TENORS_MONTHS:
            rows.append({
                "Cycle Month": c, "Tenor Months": t,
                "Benchmark": BENCHMARK,
                "Rate Percent": round(path[i] + tenor_spread[t], 4),
            })
    return pd.DataFrame(rows)
