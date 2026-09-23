"""L4 - Cost-to-serve migration. No customer contact, no gate, usually the
largest pool and the fastest to prove.

The one thing that makes this lever honest rather than optimistic: cost
pools have capacity steps (concept spec section 6). Avoided volume only
becomes cash if it crosses a step boundary; otherwise only the marginal
per-unit component is real savings. This lever computes both and reports
them separately rather than pretending the fixed component is always
recoverable.
"""
from __future__ import annotations
import pandas as pd

from .base import Lever, SizeResult

AVOIDABLE_CALL_REASONS = {"billing_query", "rewards_query", "rate_query"}


class L4CostToServe(Lever):
    code = "L4"
    name = "Cost-to-serve migration"
    gates = []

    def __init__(self, drivers: pd.DataFrame, pools: pd.DataFrame):
        self.drivers = drivers
        self.pools = pools[pools["Allocation Tier"] != "Tier 3"]

    def population(self, pop) -> pd.DataFrame:
        pop = super().population(pop)
        cv = pop.frame
        routed = cv["routed_lever"] == "L4"
        # Broader migration candidates: high avoidable-call volume or paper
        # statement delivery, independent of whether they are yet a loss.
        # Drivers are keyed by account; roll to customer via the SAME
        # customer number the driver table already carries (one join, not
        # a coincidental key match on today's 1:1 card cardinality).
        cust_drv = self.drivers.groupby("Masked Customer Number").agg(
            avoidable_calls=("Primary Call Reason",
                            lambda s: s.isin(AVOIDABLE_CALL_REASONS).sum()),
            paper_statements=("Paper Statements Produced", "sum"),
        ).reset_index()
        cv = cv.merge(cust_drv, on="Masked Customer Number", how="left")
        cv["avoidable_calls"] = cv["avoidable_calls"].fillna(0)
        cv["paper_statements"] = cv["paper_statements"].fillna(0)
        migratable = (cv["avoidable_calls"] >= 3) | (cv["paper_statements"] >= 6)
        return cv[routed | migratable].copy()

    def size(self, population: pd.DataFrame) -> SizeResult:
        cust_ids = set(population["Masked Customer Number"].dropna())
        drv = self.drivers[self.drivers["Masked Customer Number"].isin(cust_ids)]
        if not len(drv):
            return SizeResult(0.0, basis="no eligible volume in population")

        savings, band_crossed_savings, notes = 0.0, 0.0, []
        for activity, col in [("contact_center_call", "Contact Center Calls"),
                              ("statement_paper", "Paper Statements Produced")]:
            bands = self.pools[self.pools["Activity"] == activity]
            if not len(bands):
                continue
            total_all = self.drivers[col].sum() if col in self.drivers.columns else 0
            avoidable = drv[col].sum() if col in drv.columns else 0
            if avoidable <= 0:
                continue
            fixed_before, marginal = _band(total_all, bands)
            fixed_after, _ = _band(max(total_all - avoidable, 0), bands)
            marginal_savings = avoidable * marginal
            savings += marginal_savings
            if fixed_after < fixed_before:
                step_savings = fixed_before - fixed_after
                band_crossed_savings += step_savings
                notes.append(f"{activity}: crosses a capacity step, "
                            f"+${step_savings:,.0f} fixed cost also avoidable")
            else:
                notes.append(f"{activity}: marginal-only (${marginal_savings:,.0f}) "
                            f"- avoided volume does not cross a capacity step")

        total = savings + band_crossed_savings
        return SizeResult(
            priced_value_usd=round(total, 2),
            basis="marginal unit cost x avoidable volume, plus any fixed "
                 "capacity cost freed ONLY where avoided volume crosses a "
                 "band boundary",
            caveat="; ".join(notes) if notes else "")

    def worklist(self, population: pd.DataFrame) -> pd.DataFrame:
        wl = population.copy()
        wl["action"] = "REVIEW"
        wl.loc[wl["paper_statements"] >= 6, "action"] = "MIGRATE_TO_DIGITAL_STATEMENTS"
        wl.loc[wl["avoidable_calls"] >= 3, "action"] = "ENABLE_SELF_SERVICE"
        wl["reason"] = wl.apply(
            lambda r: (r["routing_reason"] if r.get("routed_lever") == "L4"
                      else f"{int(r['avoidable_calls'])} avoidable calls, "
                          f"{int(r['paper_statements'])} paper statements "
                          f"in trailing window"), axis=1)
        return wl[["Masked Customer Number", "action", "reason",
                  "avoidable_calls", "paper_statements"]]

    def driver(self, customer_view: pd.DataFrame) -> float:
        """Total avoidable driver volume portfolio-wide - should shrink under
        higher digital deflection and better collections efficiency."""
        d = self.drivers
        avoidable = d["Primary Call Reason"].isin(AVOIDABLE_CALL_REASONS).sum()
        paper = d["Paper Statements Produced"].sum() if "Paper Statements Produced" in d.columns else 0
        return float(avoidable + paper)


def _band(volume: float, bands: pd.DataFrame) -> tuple[float, float]:
    for _, b in bands.iterrows():
        if b["Volume Band From"] <= volume < b["Volume Band To"]:
            return float(b["Band Fixed Cost USD Monthly"]), float(b["Marginal Unit Cost USD"])
    last = bands.iloc[-1]
    return float(last["Band Fixed Cost USD Monthly"]), float(last["Marginal Unit Cost USD"])
