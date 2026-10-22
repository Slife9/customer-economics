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

Valuation (specs/lever_valuation_rebuild/SPEC_lever_valuation_rebuild.md):
every lever's size() reports three scenarios (low/base/high) driven only by
engine/config/lever_assumptions.json. Each component carries a value_type
and an evidence basis. Each lever module splits its valuation into
`valuation_inputs(...)` (computed from the data, JSON-safe, stored in a
results bundle) and `value_scenarios(inputs, a)` (pure - the same function
the app's what-if explorer calls, so the explorer can never drift from the
engine's own formulas).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from ..core.suppression import SuppressedPopulation, require_suppressed
from . import assumptions as ASSUME


@dataclass
class SizeResult:
    priced_value_usd: Optional[float]
    basis: str
    caveat: str = ""
    unpriced_context_usd: Optional[float] = None
    # {"low"|"base"|"high": {"components": {name: {"value_usd", "value_type",
    #  "basis"}}, "total_usd": float, "extras": {...}}}
    scenarios: dict = field(default_factory=dict)
    assumptions_used: dict = field(default_factory=dict)
    method_note: str = ""
    # JSON-safe inputs value_scenarios() was computed from - lets the app
    # recompute scenarios (what-if) without the raw tables.
    inputs: dict = field(default_factory=dict)
    # The base-scenario value of only the components this lever's driver()
    # actually measures - what the negative-control gate compares against
    # the driver (see governance/negative_control.py).
    gate_value_usd: Optional[float] = None

    @property
    def is_priced(self) -> bool:
        return self.priced_value_usd is not None

    @property
    def has_scenarios(self) -> bool:
        """False for a SizeResult loaded from a pre-rebuild (schema v1)
        results bundle, which carries only the old single-figure fields."""
        return bool(self.scenarios)


def component(value_usd: float, value_type: str, basis: str) -> dict:
    if value_type not in ASSUME.VALUE_TYPES:
        raise ValueError(f"unknown value_type {value_type!r}")
    if basis not in ASSUME.BASES:
        raise ValueError(f"unknown basis {basis!r}")
    return {"value_usd": float(value_usd), "value_type": value_type, "basis": basis}


def scenario(components: dict, extras: dict | None = None,
             total_usd: float | None = None) -> dict:
    """total_usd defaults to the sum of components; pass it explicitly only
    where the spec defines the headline differently (L5's conditional net)."""
    total = sum(c["value_usd"] for c in components.values()) if total_usd is None else total_usd
    return {"components": components, "total_usd": float(total), "extras": extras or {}}


class Lever:
    code: str = ""
    name: str = ""
    gates: list[str] = []
    # Set by the orchestrator (engine/run.py) to this lever's block of
    # lever_assumptions.json; falls back to the configured file if unset.
    assumptions: dict | None = None

    def lever_assumptions(self) -> dict:
        if self.assumptions is None:
            self.assumptions = ASSUME.load()[0][self.code]
        return self.assumptions

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
