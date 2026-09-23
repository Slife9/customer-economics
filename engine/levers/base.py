"""Shared lever contract (concept spec 5.5). Every lever implements the same
four methods so adding one cannot change how the others behave.

    population(suppressed)   who it applies to, after suppression
    size(population)         what it is worth, or None if it needs a test
    worklist(population)     one row per customer, one action, one reason
    driver(customers)        the portfolio quantity it claims to act on

INVARIANT: size() returns None, never 0, when the value cannot be
responsibly priced from historical data. Zero reads as "worth nothing".
None reads as "we will not invent this." A SizeResult always carries this
distinction explicitly rather than leaving a bare number or a bare None to
be misread downstream.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from ..core.suppression import SuppressedPopulation, require_suppressed


@dataclass
class SizeResult:
    priced_value_usd: Optional[float]
    basis: str
    caveat: str = ""
    unpriced_context_usd: Optional[float] = None

    @property
    def is_priced(self) -> bool:
        return self.priced_value_usd is not None


class Lever:
    code: str = ""
    name: str = ""
    gates: list[str] = []

    def population(self, pop) -> SuppressedPopulation:
        return require_suppressed(pop)

    def size(self, pop: SuppressedPopulation) -> SizeResult:
        raise NotImplementedError

    def worklist(self, pop: SuppressedPopulation) -> pd.DataFrame:
        raise NotImplementedError

    def driver(self, customer_view: pd.DataFrame) -> float:
        """The portfolio quantity this lever claims to move. Used only by
        the negative control gate (section 8) - never by sizing itself."""
        raise NotImplementedError
