"""Suppression runs before routing, never after (concept spec 5.4).

Enforced structurally, not by convention: a lever's `population()` takes a
`SuppressedPopulation`, never a raw customer-view DataFrame. There is no way
to hand a lever an unsuppressed frame and have it type-check - Python will
happily let you pass the wrong object, so `SuppressedPopulation.__init__`
itself asserts every row has already cleared suppression, and every lever
asserts it received this wrapper type, not a bare DataFrame.

Customers in hardship, on an accommodation plan, or covered by SCRA are
removed BEFORE any lever sees the population. High servicing cost driven by
vulnerability is an obligation, not leakage.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


class SuppressionNotRunError(Exception):
    """A lever received something other than a SuppressedPopulation."""


class SuppressedPopulation:
    """The only type a lever's population() method may accept.

    Constructing one IS running suppression - there is no other way to get
    an instance. `frame` is guaranteed to contain no hardship, accommodation,
    or SCRA customer.
    """

    def __init__(self, frame: pd.DataFrame, suppressed: pd.DataFrame):
        bad = frame[frame["Hardship Status"].astype(bool)
                   | frame["Accommodation Plan"].astype(bool)
                   | frame["SCRA Flag"].astype(bool)]
        if len(bad):
            raise SuppressionNotRunError(
                f"{len(bad)} rows in the frame handed to SuppressedPopulation "
                f"are hardship/accommodation/SCRA. Suppression must remove "
                f"these before construction, not after.")
        self.frame = frame.reset_index(drop=True)
        self.suppressed = suppressed.reset_index(drop=True)

    def __len__(self):
        return len(self.frame)


def require_suppressed(pop) -> SuppressedPopulation:
    """Every lever's population() calls this on its input first. Raises if
    handed anything other than a SuppressedPopulation - including a raw
    customer-view DataFrame that skipped suppression entirely."""
    if not isinstance(pop, SuppressedPopulation):
        raise SuppressionNotRunError(
            f"expected a SuppressedPopulation, got {type(pop).__name__}. "
            f"Run suppression.run() before calling a lever.")
    return pop


def run(customer_view: pd.DataFrame) -> SuppressedPopulation:
    mask = (customer_view["Hardship Status"].astype(bool)
           | customer_view["Accommodation Plan"].astype(bool)
           | customer_view["SCRA Flag"].astype(bool))
    clean = customer_view[~mask].copy()
    suppressed = customer_view[mask].copy()
    suppressed["suppression_reason"] = np.select(
        [customer_view.loc[mask, "SCRA Flag"].astype(bool),
        customer_view.loc[mask, "Accommodation Plan"].astype(bool),
        customer_view.loc[mask, "Hardship Status"].astype(bool)],
        ["SCRA", "ACCOMMODATION_PLAN", "HARDSHIP"], default="UNKNOWN")
    return SuppressedPopulation(clean, suppressed)
